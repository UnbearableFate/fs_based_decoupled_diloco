from __future__ import annotations

import pytest
from dataclasses import replace

from fs_diloco.log.model import (
    FragmentState,
    SystemState,
    TransitionConflict,
    assert_invariants,
    check_invariants,
    commit_prepared,
    decide_proposal,
    fold_commits,
    prepare_transition,
    recover_prefix,
    select_quorum,
)
from fs_diloco.protocol.canonical_json import canonical_digest

from .helpers import proposal_for


def test_transition_is_deterministic_under_input_order_and_pairs_state():
    state = SystemState.genesis()
    p0 = proposal_for(state, learner=0, sequence=0, values=(1.0, -1.0), tokens=10)
    p1 = proposal_for(state, learner=1, sequence=0, values=(3.0, 1.0), tokens=30)
    state = state.publish(p0).publish(p1)
    first = prepare_transition(
        state, fragment_id=0, selected_proposal_ids=(p1.proposal_id, p0.proposal_id)
    )
    second = prepare_transition(
        state, fragment_id=0, selected_proposal_ids=(p0.proposal_id, p1.proposal_id)
    )
    assert first == second
    committed = commit_prepared(state, first)
    fragment = committed.fragments[0]
    assert fragment.params_commit_id == fragment.outer_state_commit_id == committed.head_commit_id
    assert committed.consumed_proposal_ids == {p0.proposal_id, p1.proposal_id}
    assert_invariants(committed)


def test_competing_prepared_transitions_have_one_parent_winner():
    state = SystemState.genesis()
    p0 = proposal_for(state, learner=0, sequence=0)
    p1 = proposal_for(state, learner=1, sequence=0, values=(2.0, 2.0))
    state = state.publish(p0).publish(p1)
    first = prepare_transition(state, fragment_id=0, selected_proposal_ids=(p0.proposal_id,))
    second = prepare_transition(state, fragment_id=0, selected_proposal_ids=(p1.proposal_id,))
    committed = commit_prepared(state, first)
    with pytest.raises(TransitionConflict, match="parent"):
        commit_prepared(committed, second)


def test_every_committed_prefix_replays_to_the_same_digest():
    state = SystemState.genesis(fragment_count=2)
    genesis = state
    historical_digests = [state.committed_digest()]
    for sequence in range(6):
        fragment_id = sequence % 2
        proposal = proposal_for(
            state,
            learner=sequence,
            sequence=sequence,
            fragment_id=fragment_id,
            values=(float(sequence + 1), float(-sequence)),
        )
        state = state.publish(proposal)
        state = commit_prepared(
            state,
            prepare_transition(
                state,
                fragment_id=fragment_id,
                selected_proposal_ids=(proposal.proposal_id,),
            ),
        )
        historical_digests.append(state.committed_digest())
    independent_genesis = replace(genesis, proposals=dict(state.proposals))
    for prefix in range(state.head_commit_seq + 1):
        recovered = recover_prefix(state, prefix)
        independently_folded = fold_commits(independent_genesis, state.commits[:prefix])
        assert recovered.head_commit_seq == prefix
        assert recovered.committed_digest() == historical_digests[prefix]
        assert independently_folded.committed_digest() == historical_digests[prefix]


def test_quorum_selection_and_explicit_supersession_are_deterministic():
    state = SystemState.genesis()
    proposals = [
        proposal_for(state, learner=learner, sequence=0, values=(learner + 1.0, 0.0))
        for learner in range(3)
    ]
    for proposal in reversed(proposals):
        state = state.publish(proposal)
    selected = select_quorum(state, fragment_id=0, quorum_min=2, quorum_max=2)
    assert selected == tuple(sorted(item.proposal_id for item in proposals)[:2])
    unselected = next(item.proposal_id for item in proposals if item.proposal_id not in selected)
    decided = decide_proposal(
        state,
        proposal_id=unselected,
        decision="superseded",
        reason="explicit_nonoverlap_successor",
    )
    assert unselected in decided.dropped_proposal_ids
    assert not decided.eligible(decided.proposals[unselected])


def test_quorum_returns_empty_until_minimum_distinct_learners_exist():
    state = SystemState.genesis()
    proposal = proposal_for(state, learner=0, sequence=0)
    state = state.publish(proposal)
    assert select_quorum(state, fragment_id=0, quorum_min=2, quorum_max=3) == ()


def test_quorum_uses_oldest_sequence_for_each_learner_before_canonical_order():
    state = SystemState.genesis()
    older = proposal_for(state, learner=0, sequence=1, values=(5.0, 0.0))
    newer = proposal_for(state, learner=0, sequence=2, values=(-5.0, 0.0))
    state = state.publish(newer).publish(older)
    assert select_quorum(state, fragment_id=0, quorum_min=1, quorum_max=1) == (
        older.proposal_id,
    )


def test_same_base_overlapping_successor_requires_explicit_supersession():
    state = SystemState.genesis()
    older = proposal_for(state, learner=0, sequence=0, values=(1.0, 0.0))
    overlapping = proposal_for(state, learner=0, sequence=1, values=(2.0, 0.0))
    state = state.publish(overlapping).publish(older)
    state = commit_prepared(
        state,
        prepare_transition(
            state,
            fragment_id=0,
            selected_proposal_ids=(older.proposal_id,),
        ),
    )
    assert not state.eligible(overlapping)
    with pytest.raises(Exception, match="ineligible"):
        prepare_transition(
            state,
            fragment_id=0,
            selected_proposal_ids=(overlapping.proposal_id,),
        )
    state = decide_proposal(
        state,
        proposal_id=overlapping.proposal_id,
        decision="superseded",
        reason="overlaps_committed_same_base_interval",
    )
    assert_invariants(state)


def test_duplicate_publication_is_idempotent():
    state = SystemState.genesis()
    proposal = proposal_for(state, learner=0, sequence=0)
    once = state.publish(proposal)
    assert once.publish(proposal) == once
    assert once.state_digest() != state.state_digest()


def test_rational_staleness_decay_is_committed_in_canonical_weights():
    state = SystemState.genesis()
    stale = proposal_for(state, learner=0, sequence=0, tokens=10)
    state = state.publish(stale)

    advance = proposal_for(state, learner=1, sequence=0, tokens=10)
    state = state.publish(advance)
    state = commit_prepared(
        state,
        prepare_transition(
            state,
            fragment_id=0,
            selected_proposal_ids=(advance.proposal_id,),
        ),
    )
    fresh = proposal_for(state, learner=2, sequence=0, tokens=10)
    state = state.publish(fresh)
    prepared = prepare_transition(
        state,
        fragment_id=0,
        selected_proposal_ids=(stale.proposal_id, fresh.proposal_id),
    )
    weights = dict(prepared.event.weights_hex)
    assert float.fromhex(weights[fresh.proposal_id]) > float.fromhex(
        weights[stale.proposal_id]
    )
    assert sum(float.fromhex(value) for value in weights.values()) == pytest.approx(1.0)


def test_state_digest_binds_optimizer_and_weighting_contracts():
    from fs_diloco.testing.deterministic_reference import (
        ReferenceOptimizerConfig,
        ReferenceWeightingConfig,
    )
    from fs_diloco.log.model import ReferenceProtocolConfig

    baseline = SystemState.genesis()
    different_optimizer = SystemState.genesis(
        optimizer_config=ReferenceOptimizerConfig(lr=0.8)
    )
    different_weighting = SystemState.genesis(
        weighting_config=ReferenceWeightingConfig(staleness_lambda=0.3)
    )
    different_protocol = SystemState.genesis(
        protocol_config=ReferenceProtocolConfig(max_global_staleness=2)
    )
    assert len(
        {
            baseline.state_digest(),
            different_optimizer.state_digest(),
            different_weighting.state_digest(),
            different_protocol.state_digest(),
        }
    ) == 4


def test_reference_state_nested_authority_is_immutable():
    state = SystemState.genesis()
    with pytest.raises(TypeError):
        state.fragments[0] = state.fragments[0]
    with pytest.raises(TypeError):
        state.proposals["p"] = proposal_for(state, learner=0, sequence=0)


def test_eligibility_requires_exact_commit_sequence_and_fragment_version_pairing():
    state = SystemState.genesis()
    advance = proposal_for(state, learner=9, sequence=0)
    state = state.publish(advance)
    state = commit_prepared(
        state,
        prepare_transition(
            state,
            fragment_id=0,
            selected_proposal_ids=(advance.proposal_id,),
        ),
    )
    wrong_sequence = proposal_for(state, learner=0, sequence=0)
    wrong_sequence = type(wrong_sequence).create(
        learner_id=wrong_sequence.learner_id,
        session_id=wrong_sequence.session_id,
        sequence=wrong_sequence.sequence,
        fragment_id=wrong_sequence.fragment_id,
        base_commit_id="genesis",
        base_commit_seq=1,
        base_fragment_version=0,
        target_tokens=wrong_sequence.target_tokens,
        values=wrong_sequence.values,
    )
    wrong_fragment = type(wrong_sequence).create(
        learner_id="learner-001",
        session_id="session-001",
        sequence=0,
        fragment_id=0,
        base_commit_id="genesis",
        base_commit_seq=0,
        base_fragment_version=1,
        target_tokens=10,
        values=(1.0, -1.0),
    )
    assert not state.eligible(wrong_sequence)
    assert not state.eligible(wrong_fragment)


def test_commit_revalidates_prepared_event_and_rejects_forged_causal_base():
    state = SystemState.genesis()
    valid = proposal_for(state, learner=0, sequence=0)
    impossible = type(valid).create(
        learner_id="learner-001",
        session_id="session-001",
        sequence=0,
        fragment_id=0,
        base_commit_id="genesis",
        base_commit_seq=0,
        base_fragment_version=1,
        target_tokens=10,
        values=(1.0, -1.0),
    )
    state = state.publish(valid).publish(impossible)
    prepared = prepare_transition(
        state,
        fragment_id=0,
        selected_proposal_ids=(valid.proposal_id,),
    )
    forged = replace(
        prepared,
        selected_proposal_ids=(impossible.proposal_id,),
        event=replace(
            prepared.event,
            selected_proposal_ids=(impossible.proposal_id,),
        ),
    )
    with pytest.raises(TransitionConflict, match="no longer validates"):
        commit_prepared(state, forged)

    forged_event = replace(forged.event, commit_id="pending")
    forged_event = replace(
        forged_event,
        commit_id="rc-" + canonical_digest(forged_event.identity_body()),
    )
    forged_fragment = FragmentState(
        version=1,
        params=forged_event.new_params,
        outer_state=forged_event.new_outer_state,
        params_commit_id=forged_event.commit_id,
        outer_state_commit_id=forged_event.commit_id,
    )
    forged_state = replace(
        state,
        head_commit_id=forged_event.commit_id,
        head_commit_seq=1,
        fragments={0: forged_fragment},
        consumed_proposal_ids=frozenset({impossible.proposal_id}),
        commits=(forged_event,),
    )
    assert any("I-004" in item for item in check_invariants(forged_state))


def test_recovery_preserves_nonzero_genesis_parameters():
    state = SystemState.genesis(initial_value=3.5)
    proposal = proposal_for(state, learner=0, sequence=0)
    state = state.publish(proposal)
    state = commit_prepared(
        state,
        prepare_transition(
            state,
            fragment_id=0,
            selected_proposal_ids=(proposal.proposal_id,),
        ),
    )
    recovered_genesis = recover_prefix(state, 0)
    assert recovered_genesis.fragments[0].params == (3.5, 3.5)


def test_recovery_preserves_only_drop_decisions_reachable_at_prefix():
    state = SystemState.genesis()
    committed = proposal_for(state, learner=0, sequence=0)
    state = state.publish(committed)
    state = commit_prepared(
        state,
        prepare_transition(
            state,
            fragment_id=0,
            selected_proposal_ids=(committed.proposal_id,),
        ),
    )
    dropped = proposal_for(state, learner=1, sequence=0)
    state = state.publish(dropped)
    state = decide_proposal(
        state,
        proposal_id=dropped.proposal_id,
        decision="expired",
        reason="test_prefix",
    )
    assert state.head_commit_seq == 2
    assert dropped.proposal_id not in recover_prefix(state, 0).dropped_proposal_ids
    assert dropped.proposal_id not in recover_prefix(state, 1).dropped_proposal_ids
    assert dropped.proposal_id in recover_prefix(state, 2).dropped_proposal_ids
