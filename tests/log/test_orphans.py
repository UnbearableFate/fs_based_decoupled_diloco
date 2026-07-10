from __future__ import annotations

from fs_diloco.log import inspect_orphans, replay_log
from fs_diloco.storage import InMemoryStorageBackend

from .helpers import initialize, proposal


def test_orphan_and_uncommitted_proposal_discovery_never_changes_authority():
    backend = InMemoryStorageBackend()
    log = initialize(backend, "orphan-view")
    candidate = proposal(log, learner="candidate", sequence=1)
    prepared_item = proposal(log, learner="prepared", sequence=1, values=(2.0, 3.0))
    prepared = log.prepare_transition(
        fragment_id=0, selected_proposal_ids=(prepared_item.proposal_id,)
    )
    before = replay_log(log).committed_state_digest
    report = inspect_orphans(log)
    assert log.layout.proposal_key(candidate.proposal_id) in report.uncommitted_proposals
    assert prepared.commit_ref.key in report.prepared_orphans
    assert prepared.frontier_ref.key in report.prepared_orphans
    after = replay_log(log)
    assert after.committed_state_digest == before
    assert after.head_frontier.commit_seq == 0
