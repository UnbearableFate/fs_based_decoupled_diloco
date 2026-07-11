from __future__ import annotations

import copy

import pytest

from fs_diloco.distributed_syncer.membership import DistributedMemberV1, MembershipRevisionV1
from fs_diloco.log.run import RunSpec
from fs_diloco.testing.deterministic_reference import ReferenceOptimizerConfig


def _membership() -> MembershipRevisionV1:
    return MembershipRevisionV1.create(
        0,
        (
            DistributedMemberV1(
                member_id="member-0",
                learner_id="learner-0",
                learner_session_id="learner-session-0",
                executor_id="executor-0",
                executor_session_id="executor-session-0",
                node_id="node-0",
                capability_digest="1" * 64,
                committer_eligible=True,
            ),
        ),
    )


def _spec() -> RunSpec:
    return RunSpec(
        run_id="distributed-run",
        run_generation=1,
        model_revision="model",
        parameter_index_digest="2" * 64,
        fragment_layout_digest="3" * 64,
        outer_optimizer_schema_digest="4" * 64,
        optimizer_config=ReferenceOptimizerConfig(),
        coordination_protocol="distributed-head-fenced-v1",
        distributed_membership=_membership(),
        ownership_replication_factor=1,
        execution_backend_digest="5" * 64,
        prepare_capability_digest="6" * 64,
    )


def test_distributed_run_spec_round_trips_revision_zero_bootstrap():
    spec = _spec()
    assert RunSpec.from_dict(copy.deepcopy(spec.to_dict())) == spec
    assert spec.to_dict()["generation_origin"]["exact_continuation"] is False


def test_distributed_fields_fail_closed_under_central_protocol():
    payload = _spec().to_dict()
    payload["coordination_protocol"] = "head-fenced-v1"
    with pytest.raises(ValueError, match="central run"):
        RunSpec.from_dict(payload)


def test_unknown_distributed_bootstrap_field_fails_closed():
    payload = _spec().to_dict()
    payload["distributed_execution"]["heartbeat_members"] = []
    with pytest.raises(ValueError, match="distributed execution"):
        RunSpec.from_dict(payload)


def test_factor_two_run_spec_is_fresh_and_fails_if_membership_is_insufficient():
    membership = MembershipRevisionV1.create(
        0,
        (
            _membership().members[0],
            DistributedMemberV1(
                member_id="member-1",
                learner_id="learner-1",
                learner_session_id="learner-session-1",
                executor_id="executor-1",
                executor_session_id="executor-session-1",
                node_id="node-1",
                capability_digest="2" * 64,
                committer_eligible=True,
            ),
        ),
    )
    factor_two = RunSpec(
        **{
            **_spec().__dict__,
            "distributed_membership": membership,
            "ownership_replication_factor": 2,
        }
    )
    assert RunSpec.from_dict(factor_two.to_dict()) == factor_two
    with pytest.raises(ValueError, match="insufficient"):
        RunSpec(**{**_spec().__dict__, "ownership_replication_factor": 2})
