from __future__ import annotations

import pytest

from fs_diloco.log import CRASH_POINTS, InjectedLogCrash, inspect_orphans, replay_log
from fs_diloco.storage import InMemoryStorageBackend

from .helpers import initialize, proposal


@pytest.mark.parametrize("crash_point", CRASH_POINTS)
def test_every_crash_point_recovers_to_the_old_or_new_complete_prefix(crash_point):
    backend = InMemoryStorageBackend()
    log = initialize(backend, f"crash-{crash_point.replace('_', '-')}")
    item = proposal(log, learner="learner-a", sequence=1)
    with pytest.raises(InjectedLogCrash):
        log.commit_transition(
            fragment_id=0,
            selected_proposal_ids=(item.proposal_id,),
            crash_at=crash_point,
        )
    replay = replay_log(log)
    expected_seq = 1 if crash_point == "after_head_cas" else 0
    assert replay.head_frontier.commit_seq == expected_seq
    assert len(replay.prefix_digests) == expected_seq + 1
    fragment = replay.head_frontier.fragments[0]
    assert fragment.params_ref is not None
    assert fragment.outer_state_ref is not None


def test_complete_pre_cas_prepare_is_an_orphan_not_a_commit():
    backend = InMemoryStorageBackend()
    log = initialize(backend, "prepared-orphan")
    item = proposal(log, learner="learner-a", sequence=1)
    prepared = log.prepare_transition(
        fragment_id=0, selected_proposal_ids=(item.proposal_id,)
    )
    assert replay_log(log).head_frontier.commit_seq == 0
    report = inspect_orphans(log)
    assert prepared.commit_ref.key in report.prepared_orphans
    assert prepared.frontier_ref.key in report.prepared_orphans
