from __future__ import annotations

import os

import pytest

from fs_diloco.storage import (
    CapabilityError,
    IntegrityError,
    InvalidKey,
    PosixStorageBackend,
    PreconditionFailed,
    StorageIOError,
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


def test_posix_listing_and_head_are_header_only_but_get_still_verifies_payload(tmp_path):
    root = tmp_path / "store"
    backend = PosixStorageBackend(root)
    metadata = backend.put_immutable("objects/a", b"verified")
    path = root / "objects/a"
    payload = path.read_bytes()
    path.write_bytes(payload[:-1])
    with pytest.raises(IntegrityError):
        backend.get("objects/a")
    assert backend.head("objects/a") == metadata
    assert backend.list_prefix("objects/") == ("objects/a",)
    with pytest.raises(IntegrityError):
        backend.range_get("objects/a", 0, 1)


def test_posix_prefix_listing_and_head_read_no_payload_bytes(tmp_path):
    backend = PosixStorageBackend(tmp_path / "store")
    payload = b"x" * (2 * 1024 * 1024)
    metadata = backend.put_immutable("objects/target/large", payload)
    backend.put_immutable("objects/unrelated/large", payload)
    before = backend.read_counters

    assert backend.list_prefix("objects/target/") == ("objects/target/large",)
    assert backend.head("objects/target/large") == metadata

    after = backend.read_counters
    assert after["payload_bytes"] == before["payload_bytes"]
    assert after["header_bytes"] - before["header_bytes"] < 2 * 64 * 1024


def test_posix_range_get_reads_and_verifies_only_intersecting_v2_chunks(tmp_path):
    import fs_diloco.storage.posix as posix_module

    backend = PosixStorageBackend(tmp_path / "store")
    chunk = posix_module._RANGE_CHUNK_BYTES
    payload = b"a" * chunk + b"b" * 1024
    backend.put_immutable("objects/range", payload)
    before = backend.read_counters
    assert backend.range_get("objects/range", chunk + 10, chunk + 20) == b"b" * 10
    after = backend.read_counters
    assert after["payload_bytes"] - before["payload_bytes"] == 1024

    path = backend.root / "objects/range"
    with path.open("r+b") as handle:
        header = backend._read_header_from_handle(handle, "objects/range")
        payload_offset = handle.tell()
        assert header.chunk_size == chunk
        handle.seek(payload_offset)
        handle.write(b"z")
    # Corruption outside the requested chunk does not force full-object I/O.
    assert backend.range_get("objects/range", chunk + 10, chunk + 20) == b"b" * 10
    with pytest.raises(IntegrityError):
        backend.get("objects/range")


def test_posix_idempotent_immutable_put_compares_header_identity_only(tmp_path):
    backend = PosixStorageBackend(tmp_path / "store")
    payload = b"payload" * 100_000
    first = backend.put_immutable("objects/a", payload)
    before = backend.read_counters
    second = backend.put_immutable("objects/a", payload)
    after = backend.read_counters
    assert second == first
    assert after["payload_bytes"] == before["payload_bytes"]


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


def test_posix_idempotent_retry_requires_the_same_explicit_request_id(tmp_path):
    backend = PosixStorageBackend(tmp_path / "store-idempotency")
    initial = backend.put_if_absent("control/head", b"zero")
    winner = backend.conditional_replace(
        "control/head",
        expected_version=initial.version,
        data=b"same",
        request_id="request-a",
    )
    retry = backend.conditional_replace(
        "control/head",
        expected_version=initial.version,
        data=b"same",
        request_id="request-a",
    )
    assert retry == winner
    with pytest.raises(PreconditionFailed):
        backend.conditional_replace(
            "control/head",
            expected_version=initial.version,
            data=b"same",
            request_id="independent-request-b",
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
    assert backend.capabilities.cross_node_advisory_lock
    assert backend.capabilities.advisory_lock_evidence
    assert backend.capabilities.atomic_replace
    assert os.path.samefile(backend.root, tmp_path / "store")


def test_shared_authority_root_fails_closed_without_cross_node_lock(monkeypatch, tmp_path):
    import fs_diloco.storage.posix as posix_module

    monkeypatch.setattr(
        posix_module,
        "_mount_details",
        lambda _path: ("lustre", frozenset({"rw", "localflock"})),
    )
    with pytest.raises(CapabilityError, match="cross-node advisory locking"):
        PosixStorageBackend(tmp_path / "authority")
    backend = PosixStorageBackend(
        tmp_path / "authority-observational",
        require_cross_node_lock=False,
    )
    assert backend.capabilities.cross_node_advisory_lock is False


def test_posix_temp_creation_and_lock_errors_are_translated(tmp_path, monkeypatch):
    import errno
    import fs_diloco.storage.posix as posix_module

    backend = PosixStorageBackend(tmp_path / "store-errors")

    def fail_temp(*args, **kwargs):
        raise OSError(errno.ENOSPC, "injected no space")

    monkeypatch.setattr(posix_module.tempfile, "mkstemp", fail_temp)
    with pytest.raises(StorageIOError) as temp_error:
        backend.put_immutable("objects/temp", b"x")
    assert temp_error.value.errno == errno.ENOSPC
    assert not temp_error.value.retryable

    monkeypatch.undo()

    def fail_lock(*args, **kwargs):
        raise OSError(errno.ESTALE, "injected stale handle")

    monkeypatch.setattr(posix_module.fcntl, "flock", fail_lock)
    with pytest.raises(StorageIOError) as lock_error:
        backend.put_immutable("objects/lock", b"x")
    assert lock_error.value.errno == errno.ESTALE
    assert lock_error.value.retryable
