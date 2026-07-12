from __future__ import annotations

import multiprocessing
import os

from fs_diloco.storage import PosixStorageBackend, PreconditionFailed


def _cas_worker(
    root: str,
    expected: str,
    value: bytes,
    request_id: str,
    start,
    results,
) -> None:
    backend = PosixStorageBackend(root)
    start.wait(10)
    try:
        result = backend.conditional_replace(
            "control/head",
            expected_version=expected,
            data=value,
            request_id=request_id,
        )
    except PreconditionFailed:
        results.put(("conflict", value, None))
    else:
        results.put(("winner", value, result.version))


def _lock_and_exit(root: str, ready) -> None:
    backend = PosixStorageBackend(root)
    with backend._locked("control/head"):
        ready.set()
        os._exit(37)


def _kill_at_stage(root: str, key: str, stage: str) -> None:
    def hook(observed: str) -> None:
        if observed == stage:
            os._exit(41)

    backend = PosixStorageBackend(root, stage_hook=hook)
    backend.put_immutable(key, b"value")


def test_competing_processes_with_one_expected_version_have_one_winner(tmp_path):
    root = str(tmp_path / "store")
    backend = PosixStorageBackend(root)
    initial = backend.put_if_absent("control/head", b"zero")
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    results = context.Queue()
    workers = [
        context.Process(
            target=_cas_worker,
            args=(root, initial.version, f"w{i}".encode(), f"distinct-{i}", start, results),
        )
        for i in range(8)
    ]
    for worker in workers:
        worker.start()
    start.set()
    observed = [results.get(timeout=20) for _ in workers]
    for worker in workers:
        worker.join(20)
        assert worker.exitcode == 0
    winners = [item for item in observed if item[0] == "winner"]
    assert len(winners) == 1
    assert backend.get("control/head") == winners[0][1]


def test_independent_identical_cas_requests_still_have_one_winner(tmp_path):
    root = str(tmp_path / "store-identical")
    backend = PosixStorageBackend(root)
    initial = backend.put_if_absent("control/head", b"zero")
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    results = context.Queue()
    workers = [
        context.Process(
            target=_cas_worker,
            args=(root, initial.version, b"identical", f"independent-{i}", start, results),
        )
        for i in range(8)
    ]
    for worker in workers:
        worker.start()
    start.set()
    observed = [results.get(timeout=20) for _ in workers]
    for worker in workers:
        worker.join(20)
        assert worker.exitcode == 0
    assert sum(item[0] == "winner" for item in observed) == 1
    assert backend.get("control/head") == b"identical"


def test_process_exit_releases_advisory_lock_for_takeover(tmp_path):
    root = str(tmp_path / "store")
    backend = PosixStorageBackend(root)
    initial = backend.put_if_absent("control/head", b"zero")
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    worker = context.Process(target=_lock_and_exit, args=(root, ready))
    worker.start()
    assert ready.wait(10)
    worker.join(10)
    assert worker.exitcode == 37
    updated = backend.conditional_replace(
        "control/head",
        expected_version=initial.version,
        data=b"takeover",
    )
    assert backend.get("control/head", expected_version=updated.version) == b"takeover"
    assert backend.stale_lock_file_count() >= 1


def test_process_kill_at_each_publication_stage_yields_old_or_new_object(tmp_path):
    context = multiprocessing.get_context("spawn")
    before_visible = {"after_temp_write", "after_file_fsync", "before_publish"}
    stages = before_visible | {
        "after_publish",
        "before_parent_fsync",
        "after_parent_fsync",
    }
    for index, stage in enumerate(sorted(stages)):
        root = str(tmp_path / f"store-{index}")
        key = "objects/a"
        worker = context.Process(target=_kill_at_stage, args=(root, key, stage))
        worker.start()
        worker.join(20)
        assert worker.exitcode == 41
        backend = PosixStorageBackend(root)
        if stage in before_visible:
            assert key not in backend.list_prefix("objects/")
        else:
            assert backend.get(key) == b"value"
