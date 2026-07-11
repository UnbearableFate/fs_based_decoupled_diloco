from __future__ import annotations

import pytest

from fs_diloco.learner_protocol.adoption import (
    AdoptionKernel,
    AdoptionPhase,
    OptimizerAdoptionPolicy,
    optimizer_reset_targets,
)
from fs_diloco.learner_protocol.data_cursor import DataCursor
from fs_diloco.learner_protocol.interval import AuthorityFrontier, ContributionInterval
from fs_diloco.learner_protocol.rng_state import RngCursor
from fs_diloco.learner_protocol.session import LearnerSession


def _frontier(seq: int, *, version: int | None = None) -> AuthorityFrontier:
    return AuthorityFrontier(
        commit_id=f"commit-{seq}",
        commit_seq=seq,
        frontier_sha256=f"{seq:064x}",
        fragment_versions={0: seq if version is None else version, 1: seq},
        fencing_epoch=1,
        owner_id="syncer-a",
        owner_session_id="owner-a",
    )


def test_interval_base_is_frozen_and_steps_are_non_overlapping():
    session = LearnerSession.new("run-a", 0, "learner_000", session_id="session-a")
    interval = ContributionInterval.start(
        session=session,
        sequence=1,
        fragment_id=0,
        base=_frontier(3),
        start_step=10,
        start_cursor=DataCursor(batch_index=20, token_offset=0),
        rng_cursor=RngCursor(seed=7, draws=20),
        transport_dtype="bfloat16",
    )
    progressed = interval.record_step(tokens=32, examples=2)
    closed = progressed.close(end_cursor=DataCursor(batch_index=21, token_offset=0))
    assert interval.base == progressed.base == closed.base
    assert closed.local_step_range == (10, 11)
    assert closed.target_tokens == 32
    assert closed.interval_digest == closed.interval_digest
    with pytest.raises(ValueError, match="closed"):
        closed.record_step(tokens=1, examples=1)
    with pytest.raises(ValueError, match="sequence"):
        ContributionInterval.start(
            session=session,
            sequence=1,
            fragment_id=0,
            base=_frontier(3),
            start_step=11,
            start_cursor=DataCursor(batch_index=21, token_offset=0),
            rng_cursor=RngCursor(seed=7, draws=21),
            transport_dtype="bfloat16",
            previous=closed,
        )


def test_session_restart_is_unique_and_sequence_recovery_is_monotonic():
    first = LearnerSession.new("run-a", 0, "learner_000", session_id="session-a")
    restarted = LearnerSession.new("run-a", 0, "learner_000", session_id="session-b")
    assert first.identity != restarted.identity
    assert first.next_sequence([3, 1, 2]) == 4
    assert restarted.next_sequence([]) == 1
    with pytest.raises(ValueError, match="positive"):
        first.next_sequence([0])


def test_adoption_is_deferred_until_boundary_and_digest_is_order_independent():
    kernel = AdoptionKernel.bootstrap(_frontier(1))
    opened = kernel.begin_interval("interval-a")
    observed = opened.observe_successor(_frontier(2))
    assert observed.phase is AdoptionPhase.INTERVAL_OPEN
    assert observed.adopted == _frontier(1)
    assert observed.pending == _frontier(2)
    published = observed.mark_published("proposal-a")
    adopted = published.adopt_successor()
    assert adopted.phase is AdoptionPhase.READY
    assert adopted.adopted == _frontier(2)
    assert adopted.pending is None

    alternate = (
        AdoptionKernel.bootstrap(_frontier(1))
        .begin_interval("interval-a")
        .observe_successor(_frontier(2))
        .mark_published("proposal-a")
        .adopt_successor()
    )
    assert adopted.state_digest == alternate.state_digest


def test_stop_and_no_progress_are_terminal_and_have_priority():
    kernel = AdoptionKernel.bootstrap(_frontier(1)).begin_interval("interval-a")
    stopped = kernel.observe_stop("stop-after-outer-steps", commit_seq=3)
    assert stopped.phase is AdoptionPhase.STOPPED
    with pytest.raises(ValueError, match="terminal"):
        stopped.begin_interval("interval-b")
    no_progress = (
        AdoptionKernel.bootstrap(_frontier(1))
        .begin_interval("interval-a")
        .mark_published("proposal-a")
        .declare_no_progress("deadline")
    )
    assert no_progress.phase is AdoptionPhase.NO_PROGRESS


def test_three_optimizer_policies_have_explicit_reset_targets():
    mapping = {"p0": 0, "p1": 1, "p2": 1}
    assert optimizer_reset_targets(
        OptimizerAdoptionPolicy.RESET_ALL, {1}, mapping
    ) == frozenset(mapping)
    assert optimizer_reset_targets(
        OptimizerAdoptionPolicy.RESET_UPDATED_FRAGMENT, {1}, mapping
    ) == frozenset({"p1", "p2"})
    assert optimizer_reset_targets(
        OptimizerAdoptionPolicy.PRESERVE, {1}, mapping
    ) == frozenset()


def test_cross_session_predecessor_fails_closed():
    first = LearnerSession.new("run-a", 0, "learner_000", session_id="session-a")
    second = LearnerSession.new("run-a", 0, "learner_000", session_id="session-b")
    prior = ContributionInterval.start(
        session=first,
        sequence=1,
        fragment_id=0,
        base=_frontier(1),
        start_step=0,
        start_cursor=DataCursor(0, 0),
        rng_cursor=RngCursor(7, 0),
        transport_dtype="bfloat16",
    ).record_step(tokens=8, examples=1).close(end_cursor=DataCursor(1, 0))
    with pytest.raises(ValueError, match="session"):
        ContributionInterval.start(
            session=second,
            sequence=2,
            fragment_id=0,
            base=_frontier(2),
            start_step=1,
            start_cursor=DataCursor(1, 0),
            rng_cursor=RngCursor(7, 1),
            transport_dtype="bfloat16",
            previous=prior,
        )
