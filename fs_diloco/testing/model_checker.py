"""Seeded model checker and deliberate safety mutants."""

from __future__ import annotations

from dataclasses import replace

from fs_diloco.log.model import (
    CommitEvent,
    FragmentState,
    ReferenceProposal,
    SystemState,
    check_invariants,
    commit_prepared,
    prepare_transition,
    recover_prefix,
)
from fs_diloco.testing.trace import generate_trace, replay_trace


def run_seeded_traces(*, count: int, start_seed: int = 0, steps: int = 12) -> dict[str, object]:
    if count < 1:
        raise ValueError("count must be positive")
    digests: list[str] = []
    action_counts: dict[str, int] = {}
    for seed in range(start_seed, start_seed + count):
        trace = generate_trace(seed, steps=steps)
        for event in trace.events:
            action_counts[event.action] = action_counts.get(event.action, 0) + 1
        first = replay_trace(trace)
        second = replay_trace(trace)
        if first.state_digest() != second.state_digest():
            raise AssertionError(f"trace {seed} is nondeterministic")
        violations = check_invariants(first)
        if violations:
            raise AssertionError(f"trace {seed} violates invariants: {violations}")
        digests.append(first.state_digest())
    return {
        "count": count,
        "start_seed": start_seed,
        "unique_state_digests": len(set(digests)),
        "suite_digest": _suite_digest(digests),
        "action_counts": dict(sorted(action_counts.items())),
    }


def _suite_digest(digests: list[str]) -> str:
    from fs_diloco.protocol.canonical_json import canonical_digest

    return canonical_digest(digests)


def mutate_double_inclusion(state: SystemState) -> SystemState:
    if not state.commits:
        raise ValueError("double-inclusion mutant needs one commit")
    source = state.commits[-1]
    current = state.fragments[source.fragment_id]
    event = CommitEvent(
        commit_seq=state.head_commit_seq + 1,
        commit_id="mutant-double-inclusion",
        parent_commit_id=state.head_commit_id,
        fragment_id=source.fragment_id,
        previous_fragment_version=current.version,
        new_fragment_version=current.version + 1,
        selected_proposal_ids=source.selected_proposal_ids,
        weights_hex=source.weights_hex,
        new_params=current.params,
        new_outer_state=current.outer_state,
        transition_digest=source.transition_digest,
    )
    fragments = dict(state.fragments)
    fragments[source.fragment_id] = FragmentState(
        version=current.version + 1,
        params=current.params,
        outer_state=current.outer_state,
        params_commit_id=event.commit_id,
        outer_state_commit_id=event.commit_id,
    )
    return replace(
        state,
        head_commit_id=event.commit_id,
        head_commit_seq=event.commit_seq,
        fragments=fragments,
        commits=state.commits + (event,),
    )


def mutate_wrong_parent(state: SystemState) -> SystemState:
    if not state.commits:
        raise ValueError("wrong-parent mutant needs one commit")
    commits = list(state.commits)
    commits[-1] = replace(commits[-1], parent_commit_id="not-the-real-parent")
    return replace(state, commits=tuple(commits))


def mutate_state_pairing(state: SystemState) -> SystemState:
    fragment_id = next(key for key, value in state.fragments.items() if value.version > 0)
    fragments = dict(state.fragments)
    fragments[fragment_id] = replace(
        fragments[fragment_id], outer_state_commit_id="unpaired-outer-state"
    )
    return replace(state, fragments=fragments)


def mutate_numeric_transition(state: SystemState) -> SystemState:
    if len(state.commits) != 1:
        raise ValueError("numeric mutant currently expects one commit")
    from fs_diloco.protocol.canonical_json import canonical_digest
    from fs_diloco.testing.deterministic_reference import optimizer_state_digest

    source = state.commits[0]
    corrupted_params = (source.new_params[0] + 0.5, *source.new_params[1:])
    corrupted_digest = optimizer_state_digest(
        corrupted_params,
        source.new_outer_state,
        state.optimizer_config,
    )
    event = replace(
        source,
        commit_id="pending",
        new_params=corrupted_params,
        transition_digest=corrupted_digest,
    )
    event = replace(event, commit_id="rc-" + canonical_digest(event.identity_body()))
    fragment = state.fragments[event.fragment_id]
    fragments = dict(state.fragments)
    fragments[event.fragment_id] = replace(
        fragment,
        params=corrupted_params,
        params_commit_id=event.commit_id,
        outer_state_commit_id=event.commit_id,
    )
    return replace(
        state,
        head_commit_id=event.commit_id,
        fragments=fragments,
        commits=(event,),
    )


def mutate_sequence_rollback(state: SystemState) -> SystemState:
    if len(state.commits) != 1 or not isinstance(state.commits[0], CommitEvent):
        raise ValueError("sequence rollback mutant expects one commit")
    first_id = state.commits[0].selected_proposal_ids[0]
    first = state.proposals[first_id]
    genesis = recover_prefix(state, 0)
    high = ReferenceProposal.create(
        learner_id=first.learner_id,
        session_id=first.session_id,
        sequence=2,
        fragment_id=first.fragment_id,
        base_commit_id=genesis.head_commit_id,
        base_commit_seq=genesis.head_commit_seq,
        base_fragment_version=genesis.fragments[first.fragment_id].version,
        target_tokens=first.target_tokens,
        values=first.values,
    )
    high_state = genesis.publish(high)
    high_state = commit_prepared(
        high_state,
        prepare_transition(
            high_state,
            fragment_id=high.fragment_id,
            selected_proposal_ids=(high.proposal_id,),
        ),
    )
    rollback = ReferenceProposal.create(
        learner_id=first.learner_id,
        session_id=first.session_id,
        sequence=1,
        fragment_id=first.fragment_id,
        base_commit_id=high_state.head_commit_id,
        base_commit_seq=high_state.head_commit_seq,
        base_fragment_version=high_state.fragments[first.fragment_id].version,
        target_tokens=first.target_tokens,
        values=first.values,
    )
    published = high_state.publish(rollback)
    validation_shadow = replace(published, consumed_proposal_ids=frozenset())
    prepared = prepare_transition(
        validation_shadow,
        fragment_id=rollback.fragment_id,
        selected_proposal_ids=(rollback.proposal_id,),
    )
    event = prepared.event
    fragments = dict(published.fragments)
    fragments[rollback.fragment_id] = FragmentState(
        version=event.new_fragment_version,
        params=event.new_params,
        outer_state=event.new_outer_state,
        params_commit_id=event.commit_id,
        outer_state_commit_id=event.commit_id,
    )
    return replace(
        published,
        head_commit_id=event.commit_id,
        head_commit_seq=event.commit_seq,
        fragments=fragments,
        consumed_proposal_ids=published.consumed_proposal_ids | {rollback.proposal_id},
        commits=published.commits + (event,),
    )


def mutant_violations(state: SystemState, mutant: str) -> tuple[str, ...]:
    functions = {
        "double_apply": mutate_double_inclusion,
        "wrong_parent": mutate_wrong_parent,
        "state_pairing": mutate_state_pairing,
        "numeric_transition": mutate_numeric_transition,
        "sequence_rollback": mutate_sequence_rollback,
    }
    if mutant not in functions:
        raise ValueError(mutant)
    return check_invariants(functions[mutant](state))
