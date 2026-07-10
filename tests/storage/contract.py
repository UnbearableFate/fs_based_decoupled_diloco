from __future__ import annotations

import hashlib

import pytest

from fs_diloco.storage import (
    ImmutableConflict,
    NotFound,
    PreconditionFailed,
    StorageBackend,
)


def exercise_backend_contract(backend: StorageBackend) -> None:
    source = bytearray(b"immutable")
    first = backend.put_immutable("objects/a", source)
    source[:] = b"corrupted-caller-buffer"
    same = backend.put_immutable("objects/a", b"immutable")
    assert first == same
    assert first.sha256 == hashlib.sha256(b"immutable").hexdigest()
    assert backend.get("objects/a", expected_version=first.version) == b"immutable"
    assert backend.head("objects/a") == first
    assert backend.range_get("objects/a", 1, 4) == b"mmu"
    with pytest.raises(ImmutableConflict):
        backend.put_immutable("objects/a", b"different")
    with pytest.raises(ImmutableConflict):
        backend.put_immutable("objects/b", b"x", sha256="0" * 64)

    initial = backend.put_if_absent("control/head", b"zero")
    replacement = bytearray(b"one")
    winner = backend.conditional_replace(
        "control/head",
        expected_version=initial.version,
        data=replacement,
    )
    replacement[:] = b"bad"
    assert winner.version != initial.version
    assert backend.get("control/head") == b"one"
    with pytest.raises(PreconditionFailed):
        backend.conditional_replace(
            "control/head",
            expected_version=initial.version,
            data=b"two",
        )
    with pytest.raises(PreconditionFailed):
        backend.get("control/head", expected_version=initial.version)

    listed = backend.list_prefix("")
    assert "objects/a" in listed and "control/head" in listed
    assert backend.delete_batch([first.to_ref(), "missing/object"]) == {
        "objects/a": "deleted",
        "missing/object": "missing",
    }
    with pytest.raises(NotFound):
        backend.get("objects/a")
    assert backend.history

