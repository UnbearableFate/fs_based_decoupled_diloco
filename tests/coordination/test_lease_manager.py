from __future__ import annotations

import pytest

from fs_diloco.coordination import (
    CoordinationConflict,
    LeaseManager,
    LeaseMutation,
    MutationRequestConflict,
)
from fs_diloco.log.layout import LogLayout
from fs_diloco.storage import FailureRule, InMemoryStorageBackend


def _manager():
    backend = InMemoryStorageBackend()
    return backend, LeaseManager(
        backend,
        LogLayout("run-lease", 0),
        max_clock_skew_ns=5,
    )


def _mutation(
    operation: str,
    request_id: str,
    *,
    owner: str = "syncer-a",
    session: str = "session-a",
    epoch: int = 0,
    now: int = 100,
    ttl: int = 50,
) -> LeaseMutation:
    return LeaseMutation(
        operation=operation,
        request_id=request_id,
        owner_id=owner,
        owner_session_id=session,
        observed_fencing_epoch=epoch,
        requested_at_utc_ns=now,
        ttl_ns=ttl,
    )


def test_acquire_response_loss_reconciles_by_request_identity():
    backend, manager = _manager()
    backend.inject_failure(FailureRule("put_immutable", "after"))
    mutation = _mutation("acquire", "acquire-a")
    first = manager.acquire(mutation)
    retried = manager.acquire(mutation)
    assert first.record == retried.record
    assert first.record.owner_token.fencing_epoch == 1


def test_same_id_conflict_and_independent_same_content_are_distinct():
    _backend, manager = _manager()
    manager.acquire(_mutation("acquire", "acquire-a"))
    with pytest.raises(MutationRequestConflict):
        manager.acquire(
            _mutation(
                "acquire",
                "acquire-a",
                owner="syncer-b",
                session="session-b",
            )
        )
    with pytest.raises(CoordinationConflict):
        manager.acquire(_mutation("acquire", "independent-same-content"))


def test_takeover_waits_for_expiry_plus_skew_and_advances_epoch():
    _backend, manager = _manager()
    manager.acquire(_mutation("acquire", "acquire-a"))
    with pytest.raises(CoordinationConflict):
        manager.acquire(
            _mutation(
                "acquire",
                "acquire-b-early",
                owner="syncer-b",
                session="session-b",
                epoch=1,
                now=154,
            )
        )
    takeover = manager.acquire(
        _mutation(
            "acquire",
            "acquire-b",
            owner="syncer-b",
            session="session-b",
            epoch=1,
            now=155,
        )
    )
    assert takeover.record.proposed_fencing_epoch == 2
    assert takeover.record.lease_sequence == 2


def test_renew_after_effect_timeout_is_idempotent_and_release_expires():
    backend, manager = _manager()
    acquired = manager.acquire(_mutation("acquire", "acquire-a"))
    backend.inject_failure(FailureRule("conditional_replace", "after"))
    renew = _mutation("renew", "renew-a", epoch=1, now=120, ttl=50)
    renewed = manager.renew(renew)
    assert renewed.record.expires_at_utc_ns == 170
    assert manager.renew(renew).record == renewed.record

    released = manager.release(
        _mutation("release", "release-a", epoch=1, now=130, ttl=1)
    )
    assert released.record.expires_at_utc_ns == 130
    assert released.record.mutation_operation == "release"


def test_wrong_owner_or_epoch_cannot_renew_or_release():
    _backend, manager = _manager()
    manager.acquire(_mutation("acquire", "acquire-a"))
    with pytest.raises(CoordinationConflict):
        manager.renew(
            _mutation(
                "renew",
                "renew-b",
                owner="syncer-b",
                session="session-b",
                epoch=1,
                now=120,
            )
        )
    with pytest.raises(CoordinationConflict):
        manager.release(_mutation("release", "release-stale", epoch=2, now=120))
