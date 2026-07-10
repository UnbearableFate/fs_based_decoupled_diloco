from __future__ import annotations

from fs_diloco.log.model import ReferenceProposal, SystemState, commit_prepared, prepare_transition


def proposal_for(
    state: SystemState,
    *,
    learner: int,
    sequence: int,
    fragment_id: int = 0,
    values: tuple[float, ...] = (1.0, -1.0),
    tokens: int = 10,
) -> ReferenceProposal:
    fragment = state.fragments[fragment_id]
    return ReferenceProposal.create(
        learner_id=f"learner-{learner:03d}",
        session_id=f"session-{learner:03d}",
        sequence=sequence,
        fragment_id=fragment_id,
        base_commit_id=state.head_commit_id,
        base_commit_seq=state.head_commit_seq,
        base_fragment_version=fragment.version,
        target_tokens=tokens,
        values=values,
    )


def state_with_one_commit() -> SystemState:
    state = SystemState.genesis()
    proposal = proposal_for(state, learner=0, sequence=0)
    state = state.publish(proposal)
    prepared = prepare_transition(
        state, fragment_id=0, selected_proposal_ids=(proposal.proposal_id,)
    )
    return commit_prepared(state, prepared)
