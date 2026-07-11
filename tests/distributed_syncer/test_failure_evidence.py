from __future__ import annotations

import copy

import pytest

from fs_diloco.distributed_syncer.failure_evidence import FailureEvidenceV1
from fs_diloco.distributed_syncer.membership import (
    DistributedMemberV1,
    MembershipRevisionV1,
)
from fs_diloco.distributed_syncer.ownership import derive_ownership
from fs_diloco.distributed_syncer.reconfiguration import ReconfigurationRequestV1
from fs_diloco.protocol.canonical_json import canonical_digest


def _members() -> MembershipRevisionV1:
    return MembershipRevisionV1.create(
        0,
        tuple(
            DistributedMemberV1(
                member_id=f"member-{index}",
                learner_id=f"learner-{index}",
                learner_session_id=f"learner-session-{index}",
                executor_id=f"executor-{index}",
                executor_session_id=f"executor-session-{index}",
                node_id=f"node-{index}",
                capability_digest=f"{index + 1:064x}",
                committer_eligible=True,
            )
            for index in range(3)
        ),
    )


def _evidence() -> FailureEvidenceV1:
    return FailureEvidenceV1.create(
        {
            "run_id": "failure-evidence-run",
            "run_generation": 1,
            "membership_revision": 0,
            "suspected_member_id": "member-0",
            "reason": "manual_test_injection",
            "reporter_member_ids": ["member-2", "member-1", "member-1"],
            "observation_digest": canonical_digest({"heartbeat_age_ms": 4000}),
        }
    )


def test_false_suspicion_evidence_does_not_change_committed_ownership():
    membership = _members()
    before = derive_ownership(membership, fragment_ids=(0, 1), replication_factor=2)
    evidence = FailureEvidenceV1.from_dict(copy.deepcopy(_evidence().to_dict()))
    assert evidence.suspected_member_id in {item.member_id for item in membership.members}
    assert derive_ownership(membership, fragment_ids=(0, 1), replication_factor=2) == before


def test_reconfiguration_request_binds_exact_epoch_member_and_evidence():
    membership = _members()
    request = ReconfigurationRequestV1.create(
        {
            "expected_membership_revision": membership.revision,
            "expected_membership_digest": membership.membership_digest,
            "remove_member_id": "member-0",
            "evidence": _evidence(),
        }
    )
    assert ReconfigurationRequestV1.from_dict(copy.deepcopy(request.to_dict())) == request
    for field, value in (
        ("remove_member_id", "member-1"),
        ("expected_membership_revision", 1),
    ):
        mutant = copy.deepcopy(request.to_dict())
        mutant[field] = value
        with pytest.raises(ValueError):
            ReconfigurationRequestV1.from_dict(mutant)


def test_legacy_unbound_removal_request_fails_closed():
    with pytest.raises(ValueError, match="fields"):
        ReconfigurationRequestV1.from_dict(
            {"remove_member_id": "member-0", "evidence_digest": "1" * 64}
        )
