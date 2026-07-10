from __future__ import annotations

import pytest

from fs_diloco.storage import InMemoryStorageBackend, PosixStorageBackend

from .contract import exercise_backend_contract


@pytest.mark.parametrize("backend_kind", ["memory", "posix"])
def test_memory_and_posix_share_one_semantic_contract(tmp_path, backend_kind):
    if backend_kind == "memory":
        backend = InMemoryStorageBackend()
    else:
        backend = PosixStorageBackend(tmp_path / "store")
    exercise_backend_contract(backend)


def test_storage_protocol_is_backend_neutral_at_runtime(tmp_path):
    from fs_diloco.storage import StorageBackend

    assert isinstance(InMemoryStorageBackend(), StorageBackend)
    assert isinstance(PosixStorageBackend(tmp_path / "store"), StorageBackend)

