from __future__ import annotations

import pytest

from fs_diloco.log import RunInitializationError, TransactionalLog, replay_log
from fs_diloco.storage import InMemoryStorageBackend

from .helpers import initialize, proposal, spec


def test_genesis_is_idempotent_and_different_configuration_conflicts():
    backend = InMemoryStorageBackend()
    log = initialize(backend, "genesis-run")
    first = replay_log(log)
    reopened = initialize(backend, "genesis-run")
    assert replay_log(reopened).committed_state_digest == first.committed_state_digest
    conflicting = spec("genesis-run")
    conflicting = type(conflicting)(
        **{**conflicting.__dict__, "model_revision": "different-revision"}
    )
    with pytest.raises(RunInitializationError):
        TransactionalLog.initialize(
            backend,
            conflicting,
            {0: (0.0, 0.0), 1: (0.0, 0.0)},
        )


def test_prepare_is_invisible_until_the_single_head_cas():
    backend = InMemoryStorageBackend()
    log = initialize(backend, "happy-run")
    left = proposal(log, learner="learner-a", sequence=1)
    right = proposal(log, learner="learner-b", sequence=1, values=(0.5, 0.25))
    prepared = log.prepare_transition(
        fragment_id=0,
        selected_proposal_ids=(right.proposal_id, left.proposal_id),
    )
    before = replay_log(log)
    assert before.head_frontier.commit_seq == 0
    assert before.consumption == {}
    outcome = log.commit_prepared(prepared)
    assert outcome.status == "committed"
    after = replay_log(log)
    assert after.head_frontier.commit_seq == 1
    assert set(after.consumption) == {left.proposal_id, right.proposal_id}
    fragment = after.head_frontier.fragments[0]
    assert fragment.params_ref == prepared.commit.new_params_ref
    assert fragment.outer_state_ref == prepared.commit.new_outer_state_ref
    assert fragment.producing_commit_id == prepared.commit.commit_id
