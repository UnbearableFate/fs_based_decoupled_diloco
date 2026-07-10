from __future__ import annotations

import pytest

from fs_diloco.storage import CapabilityError, InMemoryStorageBackend, PosixStorageBackend
from fs_diloco.storage.capability_probe import probe_backend, require_capabilities


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


def test_required_capability_check_fails_closed():
    report = probe_backend(InMemoryStorageBackend(), prefix="runs/probe")
    with pytest.raises(CapabilityError, match="directory_fsync"):
        require_capabilities(report, ("directory_fsync",))


def test_legacy_runtime_has_no_posix_backend_default_switch():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for relative in ("fs_diloco/learner.py", "fs_diloco/syncer.py", "fs_diloco/config.py"):
        source = (root / relative).read_text(encoding="utf-8")
        assert "PosixStorageBackend" not in source

