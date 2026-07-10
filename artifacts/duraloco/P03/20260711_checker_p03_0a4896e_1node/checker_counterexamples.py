from __future__ import annotations

import errno
import json
import multiprocessing
import os
from pathlib import Path
import sys

from fs_diloco.storage import (
    CapabilityError,
    FaultEvent,
    FaultInjectingBackend,
    FaultSchedule,
    ImmutableConflict,
    IntegrityError,
    InvalidKey,
    PosixStorageBackend,
    StorageIOError,
)
from fs_diloco.storage.capability_probe import probe_backend, require_capabilities


def cas_worker(
    root: str,
    expected: str,
    value: bytes,
    request_id: str,
    start,
    results,
) -> None:
    backend = PosixStorageBackend(root)
    start.wait(20)
    try:
        result = backend.conditional_replace(
            "control/head",
            expected_version=expected,
            data=value,
            request_id=request_id,
        )
    except Exception as exc:
        results.put(("error", type(exc).__name__, str(exc)))
    else:
        results.put(("success", result.version, backend.get("control/head").decode()))


def lock_owner(root: str, ready) -> None:
    backend = PosixStorageBackend(root)
    with backend._locked("control/head"):
        ready.set()
        os._exit(73)


def kill_cas_at_stage(root: str, expected: str, stage: str) -> None:
    def hook(observed: str) -> None:
        if observed == stage:
            os._exit(41)

    backend = PosixStorageBackend(root, stage_hook=hook)
    backend.conditional_replace(
        "control/head",
        expected_version=expected,
        data=b"new",
        request_id=f"kill-window-{stage}",
    )


class DowngradedBackend(PosixStorageBackend):
    def _probe_directory_fsync(self) -> bool:
        return False


def main() -> int:
    work = Path(sys.argv[1])
    output = Path(sys.argv[2])
    target_commit = (
        sys.argv[3]
        if len(sys.argv) > 3
        else "0a4896e38748cbe33aaefe0d51451df1496b0db7"
    )
    work.mkdir(parents=True, exist_ok=True)
    results: dict[str, object] = {
        "target_commit": target_commit,
        "hostname": os.uname().nodename,
        "checks": {},
        "required_failures": [],
        "followups": [],
    }
    checks = results["checks"]
    assert isinstance(checks, dict)

    # Required A03 adversarial case: independent contenders use the same
    # expected token and identical target bytes. Only one CAS may report a win.
    race_root = work / "same-payload-race"
    race_backend = PosixStorageBackend(race_root)
    initial = race_backend.put_if_absent("control/head", b"zero")
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    queue = context.Queue()
    workers = [
        context.Process(
            target=cas_worker,
            args=(
                str(race_root),
                initial.version,
                b"identical",
                f"independent-request-{index}",
                start,
                queue,
            ),
        )
        for index in range(8)
    ]
    for worker in workers:
        worker.start()
    start.set()
    observations = [queue.get(timeout=30) for _ in workers]
    for worker in workers:
        worker.join(30)
        assert worker.exitcode == 0
    successes = [item for item in observations if item[0] == "success"]
    same_payload_ok = len(successes) <= 1
    checks["same_expected_same_payload_cas_at_most_one_success"] = {
        "pass": same_payload_ok,
        "success_count": len(successes),
        "contender_count": len(workers),
        "distinct_returned_versions": sorted({item[1] for item in successes}),
        "observations": observations,
    }
    if not same_payload_ok:
        results["required_failures"].append(
            "P03-A03/A08: identical-input competing CAS calls all report success"
        )

    retry_root = work / "request-id-retry"
    retry_backend = PosixStorageBackend(retry_root)
    retry_initial = retry_backend.put_if_absent("control/head", b"zero")
    retry_winner = retry_backend.conditional_replace(
        "control/head",
        expected_version=retry_initial.version,
        data=b"one",
        request_id="same-lost-response-request",
    )
    retry_result = retry_backend.conditional_replace(
        "control/head",
        expected_version=retry_initial.version,
        data=b"one",
        request_id="same-lost-response-request",
    )
    assert retry_result == retry_winner
    distinct_failed = False
    try:
        retry_backend.conditional_replace(
            "control/head",
            expected_version=retry_initial.version,
            data=b"one",
            request_id="independent-request",
        )
    except Exception as exc:
        distinct_failed = type(exc).__name__ == "PreconditionFailed"
    no_id_failed = False
    try:
        retry_backend.conditional_replace(
            "control/head",
            expected_version=retry_initial.version,
            data=b"one",
        )
    except Exception as exc:
        no_id_failed = type(exc).__name__ == "PreconditionFailed"
    assert distinct_failed and no_id_failed
    checks["request_id_disambiguates_retry_from_independent_call"] = {
        "pass": True,
        "same_id_retry_version": retry_result.version,
        "distinct_id_rejected": distinct_failed,
        "missing_id_rejected": no_id_failed,
    }

    # Audit the CAS publication window itself: after a hard process exit,
    # every verified read is either the old complete envelope or the new one.
    stages = (
        "after_temp_write",
        "after_file_fsync",
        "before_publish",
        "after_publish",
        "before_parent_fsync",
        "after_parent_fsync",
    )
    stage_results: dict[str, str] = {}
    for index, stage in enumerate(stages):
        stage_root = work / f"cas-kill-{index}"
        parent = PosixStorageBackend(stage_root)
        before = parent.put_if_absent("control/head", b"old")
        child = context.Process(
            target=kill_cas_at_stage,
            args=(str(stage_root), before.version, stage),
        )
        child.start()
        child.join(30)
        assert child.exitcode == 41
        observed = PosixStorageBackend(stage_root).get("control/head")
        expected = b"old" if stage in {
            "after_temp_write",
            "after_file_fsync",
            "before_publish",
        } else b"new"
        assert observed == expected
        stage_results[stage] = observed.decode()
    checks["cas_process_kill_old_or_new_verified"] = {
        "pass": True,
        "stages": stage_results,
    }

    lock_root = work / "lock-takeover"
    lock_backend = PosixStorageBackend(lock_root)
    lock_initial = lock_backend.put_if_absent("control/head", b"old")
    ready = context.Event()
    owner = context.Process(target=lock_owner, args=(str(lock_root), ready))
    owner.start()
    assert ready.wait(20)
    owner.join(20)
    assert owner.exitcode == 73
    takeover = lock_backend.conditional_replace(
        "control/head",
        expected_version=lock_initial.version,
        data=b"takeover",
        request_id="checker-lock-takeover",
    )
    assert lock_backend.get("control/head", expected_version=takeover.version) == b"takeover"
    checks["dead_lock_owner_takeover"] = {"pass": True}

    listing_root = work / "listing"
    listing_base = PosixStorageBackend(listing_root)
    listing_initial = listing_base.put_if_absent("control/head", b"zero")
    listing = FaultInjectingBackend(
        listing_base,
        FaultSchedule(7, (FaultEvent("list_prefix", "after", 1, "omit_list"),)),
    )
    assert listing.list_prefix("control/") == ()
    assert listing.head("control/head") == listing_initial
    listing_new = listing.conditional_replace(
        "control/head",
        expected_version=listing_initial.version,
        data=b"one",
        request_id="checker-listing-independent",
    )
    assert listing.get("control/head", expected_version=listing_new.version) == b"one"
    checks["listing_omission_independent_head_and_cas"] = {"pass": True}

    integrity_root = work / "integrity"
    integrity = PosixStorageBackend(integrity_root)
    integrity.put_immutable("objects/get", b"verified")
    integrity.put_immutable("objects/head", b"verified")
    integrity.put_immutable("objects/range", b"verified")
    detected: list[str] = []
    for key, operation in (
        ("objects/get", "get"),
        ("objects/head", "head"),
        ("objects/range", "range_get"),
    ):
        path = integrity_root / key
        path.write_bytes(path.read_bytes()[:-1])
        try:
            if operation == "get":
                integrity.get(key)
            elif operation == "head":
                integrity.head(key)
            else:
                integrity.range_get(key, 0, 1)
        except IntegrityError:
            detected.append(operation)
    assert set(detected) == {"get", "head", "range_get"}
    checks["all_read_forms_detect_integrity_failure"] = {
        "pass": True,
        "detected": detected,
    }

    path_root = work / "paths"
    outside = work / "outside"
    path_root.mkdir()
    outside.mkdir()
    (path_root / "escape").symlink_to(outside, target_is_directory=True)
    path_backend = PosixStorageBackend(path_root)
    try:
        path_backend.put_immutable("escape/object", b"bad")
    except InvalidKey:
        pass
    else:
        raise AssertionError("pre-existing symlink traversal was accepted")
    assert not (outside / "object").exists()
    checks["preexisting_symlink_traversal_rejected"] = {"pass": True}

    downgrade_root = work / "capability"
    try:
        DowngradedBackend(downgrade_root / "required", require_directory_fsync=True)
    except CapabilityError:
        required_closed = True
    else:
        required_closed = False
    audit = DowngradedBackend(downgrade_root / "audit", require_directory_fsync=False)
    report = probe_backend(audit, prefix="checker/probe", filesystem_path=audit.root)
    try:
        require_capabilities(report, ("directory_fsync",))
    except CapabilityError:
        startup_closed = True
    else:
        startup_closed = False
    assert required_closed and startup_closed and not audit.capabilities.directory_fsync
    checks["directory_fsync_downgrade_fail_closed_and_reported"] = {
        "pass": True,
        "required_constructor_failed": required_closed,
        "required_probe_failed": startup_closed,
        "audit_capability": audit.capabilities.directory_fsync,
    }

    classifications = {}
    for code in (errno.EIO, errno.ESTALE, errno.EACCES, errno.ENOSPC, errno.EDQUOT):
        translated = StorageIOError.from_oserror(
            OSError(code, os.strerror(code)), operation="checker", key="object"
        )
        classifications[str(code)] = translated.retryable
    assert classifications[str(errno.EIO)]
    assert classifications[str(errno.ESTALE)]
    assert not classifications[str(errno.EACCES)]
    assert not classifications[str(errno.ENOSPC)]
    assert not classifications[str(errno.EDQUOT)]
    checks["errno_retry_classification"] = {
        "pass": True,
        "retryable_by_errno": classifications,
    }

    conflict_root = work / "immutable-race"
    conflict = PosixStorageBackend(conflict_root)
    conflict.put_immutable("objects/a", b"one")
    try:
        conflict.put_immutable("objects/a", b"two")
    except ImmutableConflict:
        conflict_detected = True
    else:
        conflict_detected = False
    assert conflict_detected
    checks["immutable_conflict_detected"] = {"pass": True}

    schedule = FaultSchedule.seeded(
        20260711,
        operations=("get", "conditional_replace", "list_prefix", "put_immutable"),
        probability=1.0,
    )
    replay = FaultSchedule.from_json(schedule.to_json())
    assert replay == schedule and replay.digest == schedule.digest
    checks["fault_schedule_seed_replay"] = {
        "pass": True,
        "digest": schedule.digest,
        "schedule": schedule.to_dict(),
    }

    output.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    print(json.dumps(results, sort_keys=True))
    return 1 if results["required_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
