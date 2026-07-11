from __future__ import annotations

import pytest

from fs_diloco.coordination.state_machine import (
    CoordinationConflict,
    CoordinationState,
    LeaseBook,
    LeaseRequest,
    MutationRequestConflict,
    OwnerToken,
    StopRequest,
    assert_bounded_safety,
)


def _request(
    request_id: str,
    *,
    owner: str = "syncer-a",
    session: str = "session-a",
    now_ns: int = 100,
    observed_fencing_epoch: int = 0,
) -> LeaseRequest:
    return LeaseRequest(
        request_id=request_id,
        owner_id=owner,
        owner_session_id=session,
        observed_fencing_epoch=observed_fencing_epoch,
        now_ns=now_ns,
        ttl_ns=50,
    )


def test_lease_is_observational_until_epoch_bump_commits():
    state = CoordinationState.genesis()
    lease_book = LeaseBook.empty()
    lease_book, lease = lease_book.acquire(_request("acquire-a"))

    proposed = OwnerToken(
        owner_id=lease.owner_id,
        owner_session_id=lease.owner_session_id,
        fencing_epoch=lease.proposed_fencing_epoch,
    )
    assert not state.can_commit(proposed)

    state = state.commit_epoch_bump(
        token=proposed,
        request_id="fence-a",
        expected_commit_id=state.commit_id,
    )
    assert state.can_commit(proposed)
    assert state.commit_seq == 1
    assert state.optimizer_transition_count == 0


def test_two_contenders_from_one_lease_version_have_one_winner():
    lease_book = LeaseBook.empty()
    stale_version = lease_book.version
    won, lease = lease_book.acquire(_request("acquire-a"), expected_version=stale_version)
    assert lease.owner_id == "syncer-a"

    with pytest.raises(CoordinationConflict):
        won.acquire(
            _request(
                "acquire-b",
                owner="syncer-b",
                session="session-b",
                now_ns=200,
            ),
            expected_version=stale_version,
        )


def test_request_identity_distinguishes_retry_independent_and_conflict():
    lease_book = LeaseBook.empty()
    request = _request("acquire-a")
    first, lease = lease_book.acquire(request)
    retried, same = first.acquire(request)
    assert retried == first
    assert same == lease

    with pytest.raises(MutationRequestConflict):
        first.acquire(
            _request("acquire-a", owner="syncer-b", session="session-b")
        )

    with pytest.raises(CoordinationConflict):
        first.acquire(_request("independent-same-content"))


def test_clock_only_affects_takeover_liveness_not_fencing_safety():
    state = CoordinationState.genesis()
    lease_book, lease_a = LeaseBook.empty().acquire(_request("acquire-a"))
    token_a = OwnerToken.from_lease(lease_a)
    state = state.commit_epoch_bump(
        token=token_a,
        request_id="fence-a",
        expected_commit_id=state.commit_id,
    )

    lease_book, lease_b = lease_book.acquire(
        _request(
            "acquire-b",
            owner="syncer-b",
            session="session-b",
            now_ns=10_000,
            observed_fencing_epoch=state.fencing_epoch,
        )
    )
    token_b = OwnerToken.from_lease(lease_b)
    state = state.commit_epoch_bump(
        token=token_b,
        request_id="fence-b",
        expected_commit_id=state.commit_id,
    )

    with pytest.raises(CoordinationConflict):
        state.commit_optimizer(
            token=token_a,
            request_id="stale-optimizer",
            expected_commit_id=state.commit_id,
        )
    state = state.commit_optimizer(
        token=token_b,
        request_id="current-optimizer",
        expected_commit_id=state.commit_id,
    )
    assert state.optimizer_transition_count == 1


def test_control_stop_is_authoritative_and_not_an_optimizer_transition():
    state = CoordinationState.genesis()
    _, lease = LeaseBook.empty().acquire(_request("acquire-a"))
    token = OwnerToken.from_lease(lease)
    state = state.commit_epoch_bump(
        token=token,
        request_id="fence-a",
        expected_commit_id=state.commit_id,
    )
    state = state.commit_optimizer(
        token=token,
        request_id="optimizer-a",
        expected_commit_id=state.commit_id,
    )
    state = state.commit_stop(
        token=token,
        request=StopRequest(request_id="stop-a", reason="operator_requested"),
        expected_commit_id=state.commit_id,
    )

    assert state.commit_seq == 3
    assert state.optimizer_transition_count == 1
    assert state.stop is not None
    assert state.stop.reason == "operator_requested"
    with pytest.raises(CoordinationConflict):
        state.commit_optimizer(
            token=token,
            request_id="after-stop",
            expected_commit_id=state.commit_id,
        )


@pytest.mark.parametrize(
    "mutant",
    ["wall_clock_only", "lease_file_only", "stale_epoch_allowed"],
)
def test_bounded_interleavings_kill_coordination_mutants(mutant):
    with pytest.raises(AssertionError):
        assert_bounded_safety(max_depth=6, mutant=mutant)


def test_bounded_interleavings_preserve_single_fenced_writer():
    report = assert_bounded_safety(max_depth=6)
    assert report.trace_count >= 100
    assert report.split_brain_count == 0
    assert report.stale_commit_count == 0
