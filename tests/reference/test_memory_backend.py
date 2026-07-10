from __future__ import annotations

import hashlib

import pytest

from fs_diloco.storage.memory import (
    FailureRule,
    ImmutableConflict,
    InMemoryStorageBackend,
    InjectedTimeout,
    NotFound,
    PreconditionFailed,
)


def test_immutable_put_is_idempotent_and_conflicting_bytes_fail():
    backend = InMemoryStorageBackend()
    first = backend.put_immutable("objects/a", b"one")
    same = backend.put_immutable("objects/a", b"one")
    assert first == same
    assert backend.get("objects/a") == b"one"
    with pytest.raises(ImmutableConflict):
        backend.put_immutable("objects/a", b"two")
    with pytest.raises(ImmutableConflict):
        backend.put_immutable("objects/b", b"x", sha256="0" * 64)


def test_write_boundaries_snapshot_mutable_bytes_like_inputs():
    backend = InMemoryStorageBackend()
    source = bytearray(b"one")
    metadata = backend.put_immutable("objects/a", source)
    source[:] = b"two"
    assert backend.get("objects/a") == b"one"
    assert metadata.sha256 == hashlib.sha256(b"one").hexdigest()

    replacement = bytearray(b"new")
    updated = backend.conditional_replace(
        "objects/a",
        expected_version=metadata.version,
        data=replacement,
    )
    replacement[:] = b"bad"
    assert backend.get("objects/a") == b"new"
    assert updated.sha256 == hashlib.sha256(b"new").hexdigest()


def test_conditional_replace_has_one_winner_and_stale_token_fails():
    backend = InMemoryStorageBackend()
    initial = backend.put_if_absent("control/head", b"zero")
    winner = backend.conditional_replace(
        "control/head", expected_version=initial.version, data=b"one"
    )
    assert winner.version != initial.version
    with pytest.raises(PreconditionFailed):
        backend.conditional_replace("control/head", expected_version=initial.version, data=b"two")
    assert backend.get("control/head") == b"one"


def test_before_effect_timeout_has_no_effect_and_after_effect_retry_is_idempotent():
    backend = InMemoryStorageBackend()
    backend.inject_failure(FailureRule("put_immutable", "before"))
    with pytest.raises(InjectedTimeout):
        backend.put_immutable("objects/a", b"one")
    with pytest.raises(NotFound):
        backend.get("objects/a")

    backend = InMemoryStorageBackend()
    initial = backend.put_immutable("control/head", b"zero")
    backend.inject_failure(FailureRule("conditional_replace", "after"))
    with pytest.raises(InjectedTimeout):
        backend.conditional_replace(
            "control/head", expected_version=initial.version, data=b"one"
        )
    backend.clear_failures()
    retry = backend.conditional_replace(
        "control/head", expected_version=initial.version, data=b"one"
    )
    assert retry.sha256 == hashlib.sha256(b"one").hexdigest()
    assert backend.get("control/head") == b"one"


def test_range_delete_and_listing_are_observable_but_not_authority():
    backend = InMemoryStorageBackend()
    backend.put_immutable("a/1", b"012345")
    backend.put_immutable("a/2", b"other")
    assert backend.range_get("a/1", 2, 5) == b"234"
    assert backend.list_prefix("a/") == ("a/1", "a/2")
    assert backend.delete_batch(["a/1", "missing"]) == {
        "a/1": "deleted",
        "missing": "missing",
    }
    assert isinstance(backend.history, tuple)
