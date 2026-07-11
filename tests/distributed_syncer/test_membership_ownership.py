from __future__ import annotations

import copy

import pytest

from fs_diloco.distributed_syncer.membership import DistributedMemberV1, MembershipRevisionV1
from fs_diloco.distributed_syncer.ownership import derive_ownership


def _member(index: int) -> DistributedMemberV1:
    return DistributedMemberV1(
        member_id=f"member-{index}",
        learner_id=f"learner_{index:03d}",
        learner_session_id=f"learner-session-{index}",
        executor_id=f"executor-{index}",
        executor_session_id=f"executor-session-{index}",
        node_id=f"node-{index}",
        capability_digest=f"{index + 1:064x}",
        committer_eligible=True,
    )


def test_membership_and_factor_one_ownership_are_canonical_and_deterministic():
    membership = MembershipRevisionV1.create(0, tuple(_member(index) for index in range(3)))
    restored = MembershipRevisionV1.from_dict(copy.deepcopy(membership.to_dict()))
    first = derive_ownership(restored, fragment_ids=(0, 1), replication_factor=1)
    second = derive_ownership(membership, fragment_ids=(0, 1), replication_factor=1)
    assert first == second
    assert all(len(owners) == 1 for _, owners in first.owners)
    assert first.ownership_digest == second.ownership_digest


def test_heartbeat_or_listing_content_is_not_a_membership_input():
    membership = MembershipRevisionV1.create(0, (_member(0), _member(1)))
    expected = derive_ownership(membership, fragment_ids=(0,))
    arbitrary_heartbeat = {"member-0": "dead", "attacker": "alive"}
    assert arbitrary_heartbeat
    assert derive_ownership(membership, fragment_ids=(0,)) == expected


def test_duplicate_session_and_insufficient_factor_fail_closed():
    left = _member(0)
    right = DistributedMemberV1(
        **{**_member(1).__dict__, "learner_session_id": left.learner_session_id}
    )
    with pytest.raises(ValueError, match="duplicate learner_session_id"):
        MembershipRevisionV1.create(0, (left, right))
    membership = MembershipRevisionV1.create(0, (left,))
    with pytest.raises(ValueError, match="replication factor"):
        derive_ownership(membership, fragment_ids=(0,), replication_factor=2)
