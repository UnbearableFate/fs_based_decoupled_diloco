from __future__ import annotations

import pytest

from fs_diloco.log import CommitConflict, replay_log
from fs_diloco.storage import FailureRule, InMemoryStorageBackend

from .helpers import initialize, proposal


def test_two_writers_from_one_parent_have_one_committed_transition():
    backend = InMemoryStorageBackend()
    log = initialize(backend, "two-writers")
    left = proposal(log, learner="learner-a", sequence=1)
    right = proposal(log, learner="learner-b", sequence=1)
    prepared_left = log.prepare_transition(
        fragment_id=0, selected_proposal_ids=(left.proposal_id,)
    )
    prepared_right = log.prepare_transition(
        fragment_id=0, selected_proposal_ids=(right.proposal_id,)
    )
    assert log.commit_prepared(prepared_left).status == "committed"
    with pytest.raises(CommitConflict):
        log.commit_prepared(prepared_right)
    replay = replay_log(log)
    assert replay.head_frontier.commit_seq == 1
    assert tuple(replay.consumption) == (left.proposal_id,)


def test_same_logical_prepare_and_response_loss_are_idempotent():
    backend = InMemoryStorageBackend()
    log = initialize(backend, "response-loss")
    item = proposal(log, learner="learner-a", sequence=1)
    first = log.prepare_transition(
        fragment_id=0, selected_proposal_ids=(item.proposal_id,)
    )
    duplicate = log.prepare_transition(
        fragment_id=0, selected_proposal_ids=(item.proposal_id,)
    )
    assert first.commit == duplicate.commit
    backend.inject_failure(FailureRule("conditional_replace", "after"))
    recovered = log.commit_prepared(first)
    assert recovered.status == "already_committed"
    again = log.commit_prepared(duplicate)
    assert again.status == "already_committed"
    replay = replay_log(log)
    assert replay.head_frontier.commit_seq == 1
    assert list(replay.consumption) == [item.proposal_id]


def test_committed_proposal_cannot_be_logically_included_twice():
    backend = InMemoryStorageBackend()
    log = initialize(backend, "double-inclusion")
    item = proposal(log, learner="learner-a", sequence=1)
    log.commit_transition(fragment_id=0, selected_proposal_ids=(item.proposal_id,))
    with pytest.raises(CommitConflict):
        log.prepare_transition(fragment_id=0, selected_proposal_ids=(item.proposal_id,))
