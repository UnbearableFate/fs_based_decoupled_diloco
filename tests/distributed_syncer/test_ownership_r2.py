from __future__ import annotations

from fs_diloco.distributed_syncer.membership import DistributedMemberV1, MembershipRevisionV1
from fs_diloco.distributed_syncer.ownership import derive_ownership


def _member(index: int) -> DistributedMemberV1:
    return DistributedMemberV1(
        member_id=f"member-{index:03d}",
        learner_id=f"learner-{index:03d}",
        learner_session_id=f"learner-session-{index}",
        executor_id=f"executor-{index:03d}",
        executor_session_id=f"executor-session-{index}",
        node_id=f"node-{index}",
        capability_digest=f"{index + 1:064x}",
        committer_eligible=True,
    )


def test_factor_two_primary_backup_order_is_canonical():
    membership = MembershipRevisionV1.create(0, tuple(_member(i) for i in range(4)))
    first = derive_ownership(membership, fragment_ids=(0, 1, 2), replication_factor=2)
    second = derive_ownership(
        MembershipRevisionV1.from_dict(membership.to_dict()),
        fragment_ids=(0, 1, 2),
        replication_factor=2,
    )
    assert first == second
    assert all(len(owners) == 2 and owners[0] != owners[1] for _, owners in first.owners)
    assert first.to_dict()["replication_factor"] == 2
