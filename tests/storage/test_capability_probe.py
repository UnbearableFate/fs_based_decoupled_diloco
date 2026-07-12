from __future__ import annotations

import multiprocessing
from pathlib import Path

import pytest

from fs_diloco.storage import CapabilityError, InMemoryStorageBackend, PosixStorageBackend
from fs_diloco.storage.capability_probe import (
    probe_backend,
    probe_cross_node_advisory_lock,
    require_capabilities,
)


def _lock_scope_worker(root: str, rank: int, results) -> None:
    report = probe_cross_node_advisory_lock(
        Path(root),
        prefix="unit-lock-scope",
        rank=rank,
        world_size=2,
        require_distinct_hosts=False,
    )
    results.put(report)


def test_posix_capability_probe_records_observed_contract(tmp_path):
    backend = PosixStorageBackend(tmp_path / "store")
    report = probe_backend(
        backend,
        prefix="runs/probe",
        filesystem_path=backend.root,
    )
    assert report.passed
    require_capabilities(
        report,
        ("immutable_create", "conditional_replace", "verified_reads", "directory_fsync"),
    )
    assert report.hostname
    assert report.filesystem_block_size
    assert report.capabilities["cross_node_advisory_lock"] is True


def test_required_capability_check_fails_closed():
    report = probe_backend(InMemoryStorageBackend(), prefix="runs/probe")
    with pytest.raises(CapabilityError, match="directory_fsync"):
        require_capabilities(report, ("directory_fsync",))


def test_multiprocess_advisory_lock_scope_probe(tmp_path):
    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    workers = [
        context.Process(
            target=_lock_scope_worker,
            args=(str(tmp_path / "scope"), rank, results),
        )
        for rank in range(2)
    ]
    for worker in workers:
        worker.start()
    reports = [results.get(timeout=20) for _ in workers]
    for worker in workers:
        worker.join(20)
        assert worker.exitcode == 0
    assert all(report["passed"] for report in reports)
    assert all(report["blocked_while_held"] for report in reports)
    assert all(report["acquired_after_release"] for report in reports)


def test_m00_runtime_uses_the_verified_posix_backend_for_authority():
    root = Path(__file__).resolve().parents[2]
    syncer = (root / "fs_diloco/syncer.py").read_text(encoding="utf-8")
    learner = (root / "fs_diloco/learner.py").read_text(encoding="utf-8")
    assert "PosixStorageBackend(paths.authority)" in syncer
    assert "LearnerPublisher" in learner
    assert "PosixStorageBackend(paths.authority)" in learner
    assert "conditional_replace" not in learner
    assert "head_key" not in learner
    assert "ProductionTransactionalLog" in syncer
