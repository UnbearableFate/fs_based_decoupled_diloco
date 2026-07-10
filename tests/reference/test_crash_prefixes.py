from __future__ import annotations

from fs_diloco.testing.crash_matrix import (
    enumerate_decision_crashes,
    enumerate_single_commit_crashes,
)
from fs_diloco.testing.reference_simulator import CRASH_POINTS
from fs_diloco.testing.reference_simulator import DECISION_CRASH_POINTS
from fs_diloco.testing.reference_simulator import ReferenceSimulator

import pytest

from .helpers import proposal_for
from fs_diloco.log.model import SystemState, TransitionError, prepare_transition


def test_every_crash_point_recovers_old_or_new_legal_prefix():
    results = enumerate_single_commit_crashes()
    assert len(results) == len(CRASH_POINTS)
    for result in results:
        assert result.recovered_digest in {result.old_digest, result.new_digest}
        if result.crash_point == "after_head_cas":
            assert result.recovered_digest == result.new_digest
        else:
            assert result.recovered_digest == result.old_digest


def test_pre_cas_crashes_create_only_non_authoritative_orphans():
    for result in enumerate_single_commit_crashes():
        if result.crash_point in {
            "after_params_put",
            "after_outer_state_put",
            "after_commit_record_put",
            "after_frontier_put",
            "before_head_cas",
        }:
            assert result.orphan_objects > 0
            assert result.recovered_digest == result.old_digest


def test_every_decision_crash_point_recovers_old_or_new_legal_prefix():
    results = enumerate_decision_crashes()
    assert len(results) == len(DECISION_CRASH_POINTS)
    for result in results:
        assert result.recovered_digest in {result.old_digest, result.new_digest}
        if result.crash_point == "after_decision_head_cas":
            assert result.recovered_digest == result.new_digest
        else:
            assert result.recovered_digest == result.old_digest


def test_publication_crash_before_or_after_has_old_or_published_state():
    state = SystemState.genesis()
    proposal = proposal_for(state, learner=0, sequence=0)
    before = ReferenceSimulator(state)
    assert before.attempt_publish(proposal, crash_at="before_publish") == "crashed_before_publish"
    assert proposal.proposal_id not in before.restart().proposals

    after = ReferenceSimulator(state)
    assert after.attempt_publish(proposal, crash_at="after_publish") == "crashed_after_publish"
    assert proposal.proposal_id in after.restart().proposals


def test_lost_response_after_head_cas_cannot_logically_include_proposal_twice():
    state = SystemState.genesis()
    proposal = proposal_for(state, learner=0, sequence=0)
    simulator = ReferenceSimulator(state.publish(proposal))
    result = simulator.attempt_commit(
        fragment_id=0,
        selected_proposal_ids=(proposal.proposal_id,),
        crash_at="after_head_cas",
    )
    assert result.recovered_digest == result.new_digest
    recovered = simulator.restart()
    assert proposal.proposal_id in recovered.consumed_proposal_ids
    with pytest.raises(TransitionError, match="ineligible"):
        prepare_transition(
            recovered,
            fragment_id=0,
            selected_proposal_ids=(proposal.proposal_id,),
        )
