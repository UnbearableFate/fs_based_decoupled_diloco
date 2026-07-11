from __future__ import annotations

import torch

from fs_diloco.coordination.state_machine import OwnerToken
from fs_diloco.distributed_syncer.membership import DistributedMemberV1, MembershipRevisionV1
from fs_diloco.log.production import ProductionTransactionalLog
from fs_diloco.log.production_codec import (
    PRODUCTION_CODEC,
    encode_production_outer_state,
    encode_production_params,
)
from fs_diloco.log.run import RunSpec
from fs_diloco.outer_optim import init_outer_state
from fs_diloco.runtime_view import build_runtime_view
from fs_diloco.storage import InMemoryStorageBackend
from fs_diloco.testing.deterministic_reference import ReferenceOptimizerConfig


def _member(revision: int) -> DistributedMemberV1:
    return DistributedMemberV1(
        member_id=f"member-{revision}",
        learner_id="learner-0",
        learner_session_id=f"learner-session-{revision}",
        executor_id="executor-0",
        executor_session_id=f"executor-session-{revision}",
        node_id="node-0",
        capability_digest="1" * 64,
        committer_eligible=True,
    )


def test_membership_reconfiguration_is_one_global_head_control_transition():
    membership0 = MembershipRevisionV1.create(0, (_member(0),))
    optimizer = ReferenceOptimizerConfig(name="nesterov", lr=0.1, momentum=0.9)
    spec = RunSpec(
        run_id="membership-control",
        run_generation=1,
        model_revision="model",
        parameter_index_digest="2" * 64,
        fragment_layout_digest="3" * 64,
        outer_optimizer_schema_digest="4" * 64,
        optimizer_config=optimizer,
        payload_codec=PRODUCTION_CODEC,
        coordination_protocol="distributed-head-fenced-v1",
        distributed_membership=membership0,
        ownership_replication_factor=1,
        execution_backend_digest="5" * 64,
        prepare_capability_digest="6" * 64,
    )
    params = torch.tensor([1.0, 2.0])
    backend = InMemoryStorageBackend()
    log = ProductionTransactionalLog.initialize(
        backend,
        spec,
        {0: (encode_production_params(params), encode_production_outer_state(init_outer_state(params, optimizer)))},
    )
    token = OwnerToken("member-0", "committer-session", 1)
    log.activate_owner(token=token, request_id="activate-member-0")
    before = build_runtime_view(log)
    assert before.membership is not None and before.membership.revision == 0
    membership1 = MembershipRevisionV1.create(1, (_member(1),))
    log.commit_membership(membership=membership1, request_id="membership-revision-1")
    after = build_runtime_view(log)
    assert after.commit_seq == before.commit_seq + 1
    assert after.membership is not None and after.membership.revision == 1
    assert after.fragments == before.fragments
    assert after.optimizer_transition_count == before.optimizer_transition_count
    assert after.fencing_epoch == before.fencing_epoch
    assert after.owner_id == before.owner_id
