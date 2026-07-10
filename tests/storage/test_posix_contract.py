from __future__ import annotations

import os
from pathlib import Path

import pytest

from fs_diloco.storage import (
    IntegrityError,
    InvalidKey,
    PosixStorageBackend,
    PreconditionFailed,
)


@pytest.mark.parametrize(
    "key",
    ["", "/absolute", "../escape", "a/../b", "a//b", "a\\b", ".duraloco-locks/x", "a\x00b"],
)
def test_posix_rejects_noncanonical_or_reserved_keys(tmp_path, key):
    backend = PosixStorageBackend(tmp_path / "store")
    with pytest.raises(InvalidKey):
        backend.put_immutable(key, b"x")


def test_posix_rejects_symlink_traversal(tmp_path):
    root = tmp_path / "store"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)
    backend = PosixStorageBackend(root)
    with pytest.raises(InvalidKey):
        backend.put_immutable("escape/object", b"x")
    assert not (outside / "object").exists()


def test_posix_detects_short_or_corrupt_envelopes_on_every_read(tmp_path):
    root = tmp_path / "store"
    backend = PosixStorageBackend(root)
    metadata = backend.put_immutable("objects/a", b"verified")
    path = root / "objects/a"
    payload = path.read_bytes()
    path.write_bytes(payload[:-1])
    with pytest.raises(IntegrityError):
        backend.get("objects/a")
    with pytest.raises(IntegrityError):
        backend.head("objects/a")
    with pytest.raises(IntegrityError):
        backend.range_get("objects/a", 0, 1)
    assert metadata.sha256


def test_posix_detects_header_corruption(tmp_path):
    root = tmp_path / "store"
    backend = PosixStorageBackend(root)
    backend.put_immutable("objects/a", b"verified")
    path = root / "objects/a"
    payload = bytearray(path.read_bytes())
    header_offset = len(b"FSDILOCO-STORAGE-V1\n") + 8 + 32
    payload[header_offset + 5] ^= 1
    path.write_bytes(payload)
    with pytest.raises(IntegrityError, match="header checksum"):
        backend.head("objects/a")


def test_posix_opaque_versions_detect_aba_and_do_not_use_mtime(tmp_path):
    backend = PosixStorageBackend(tmp_path / "store")
    first = backend.put_if_absent("control/head", b"a")
    second = backend.conditional_replace(
        "control/head", expected_version=first.version, data=b"b"
    )
    third = backend.conditional_replace(
        "control/head", expected_version=second.version, data=b"a"
    )
    assert len({first.version, second.version, third.version}) == 3
    with pytest.raises(PreconditionFailed):
        backend.conditional_replace(
            "control/head", expected_version=first.version, data=b"stale"
        )


def test_posix_object_ref_delete_fails_closed_on_wrong_version(tmp_path):
    from dataclasses import replace

    backend = PosixStorageBackend(tmp_path / "store")
    metadata = backend.put_immutable("objects/a", b"x")
    wrong = replace(metadata.to_ref(), version="pv1-not-current")
    assert backend.delete_batch([wrong]) == {"objects/a": "precondition_failed"}
    assert backend.get("objects/a") == b"x"


def test_posix_temp_files_are_not_semantic_listing_entries(tmp_path):
    root = tmp_path / "store"
    backend = PosixStorageBackend(root)
    backend.put_immutable("objects/a", b"x")
    (root / "objects/.a.orphan.duraloco-tmp").write_bytes(b"orphan")
    assert backend.list_prefix("objects/") == ("objects/a",)


def test_posix_capability_records_parent_fsync_and_locking(tmp_path):
    backend = PosixStorageBackend(tmp_path / "store")
    assert backend.capabilities.directory_fsync
    assert backend.capabilities.advisory_lock
    assert backend.capabilities.atomic_replace
    assert os.path.samefile(backend.root, tmp_path / "store")
