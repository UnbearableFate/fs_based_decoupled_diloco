from __future__ import annotations

import pytest

from fs_diloco.log.model import TransitionError, commit_prepared, prepare_transition

from .helpers import proposal_for
from fs_diloco.log.model import SystemState


def test_committed_proposal_cannot_be_prepared_or_committed_again():
    state = SystemState.genesis()
    proposal = proposal_for(state, learner=0, sequence=0)
    state = state.publish(proposal)
    prepared = prepare_transition(
        state, fragment_id=0, selected_proposal_ids=(proposal.proposal_id,)
    )
    committed = commit_prepared(state, prepared)
    with pytest.raises(TransitionError, match="ineligible"):
        prepare_transition(
            committed, fragment_id=0, selected_proposal_ids=(proposal.proposal_id,)
        )


def test_duplicate_selection_inside_one_commit_is_rejected():
    state = SystemState.genesis()
    proposal = proposal_for(state, learner=0, sequence=0)
    state = state.publish(proposal)
    with pytest.raises(TransitionError, match="unique"):
        prepare_transition(
            state,
            fragment_id=0,
            selected_proposal_ids=(proposal.proposal_id, proposal.proposal_id),
        )
