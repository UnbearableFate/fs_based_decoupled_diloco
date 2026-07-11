from __future__ import annotations

import hashlib

import pytest
import torch
from safetensors.torch import save as save_safetensors_bytes

from fs_diloco.coordination.state_machine import OwnerToken
from fs_diloco.distributed_syncer.membership import (
    DistributedMemberV1,
    MembershipRevisionV1,
)
from fs_diloco.log import CommitConflict, ProductionTransactionalLog, RunSpec
from fs_diloco.log.production_codec import (
    PRODUCTION_CODEC,
    encode_production_outer_state,
    encode_production_params,
    production_optimizer_digest,
)
from fs_diloco.outer_optim import init_outer_state
from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.protocol.schemas import ProposalManifest
from fs_diloco.runtime_view import build_runtime_view
from fs_diloco.storage import InMemoryStorageBackend


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _member(index: int) -> DistributedMemberV1:
    return DistributedMemberV1(
        member_id=f"member-{index}",
        learner_id=f"learner-{index}",
        learner_session_id=f"learner-session-{index}",
        executor_id=f"executor-{index}",
        executor_session_id=f"executor-session-{index}",
        node_id=f"node-{index}",
        capability_digest=f"{index + 1:064x}",
        committer_eligible=True,
    )


def _initialize(*, distributed: bool):
    membership = MembershipRevisionV1.create(0, (_member(0), _member(1)))
    spec = RunSpec(
        run_id="distributed-result-binding" if distributed else "central-result-binding",
        run_generation=1,
        model_revision="model",
        parameter_index_digest=_digest("params"),
        fragment_layout_digest=_digest("layout"),
        outer_optimizer_schema_digest=_digest("outer"),
        payload_codec=PRODUCTION_CODEC,
        coordination_protocol=("distributed-head-fenced-v1" if distributed else "none"),
        distributed_membership=membership if distributed else None,
        ownership_replication_factor=2 if distributed else None,
        execution_backend_digest=_digest("backend") if distributed else None,
        prepare_capability_digest=_digest("capability") if distributed else None,
    )
    params = torch.tensor([0.0, 0.0])
    log = ProductionTransactionalLog.initialize(
        InMemoryStorageBackend(),
        spec,
        {
            0: (
                encode_production_params(params),
                encode_production_outer_state(init_outer_state(params, spec.optimizer_config)),
            )
        },
    )
    if distributed:
        log.activate_owner(
            token=OwnerToken("member-0", "committer-session", 1),
            request_id="activate-member-0",
        )
    return log


def _proposal(log: ProductionTransactionalLog) -> ProposalManifest:
    view = build_runtime_view(log)
    data = save_safetensors_bytes(
        {"local_params": torch.tensor([1.0, 2.0], dtype=torch.float32)}
    )
    digest = hashlib.sha256(data).hexdigest()
    proposal = ProposalManifest.with_computed_id(
        {
            "manifest_type": "proposal",
            "protocol_version": 2,
            "run_id": view.run_id,
            "run_generation": view.run_generation,
            "model_revision": log.spec.model_revision,
            "learner_id": "learner-0",
            "learner_session_id": "learner-session-0",
            "sequence": 1,
            "fragment_id": 0,
            "base_commit_id": view.commit_id,
            "base_commit_seq": view.commit_seq,
            "base_fragment_version": view.fragments[0].version,
            "base_frontier_digest": view.frontier_sha256,
            "local_steps_since_base": 1,
            "target_tokens_since_base": 10,
            "payload_kind": "local_end_weight",
            "payload_key": log.layout.proposal_payload_key(digest),
            "tensor_key": "local_params",
            "shape": [2],
            "dtype": "float32",
            "payload_size": len(data),
            "payload_sha256": digest,
            "parameter_index_digest": log.spec.parameter_index_digest,
            "fragment_layout_digest": log.spec.fragment_layout_digest,
            "outer_optimizer_schema_digest": log.spec.outer_optimizer_schema_digest,
        }
    )
    log.publish_proposal(proposal, data)
    return proposal


def _prepare(log, proposal, *, work_order_id="fwo2-one", result_id="pfr-one"):
    params = torch.tensor([0.5, 1.0])
    return log.prepare_transition(
        fragment_id=0,
        selected_proposal_ids=[proposal.proposal_id],
        new_params=encode_production_params(params),
        new_outer_state=encode_production_outer_state(
            init_outer_state(params, log.spec.optimizer_config)
        ),
        aggregate_digest=canonical_digest({"proposal": proposal.proposal_id}),
        outer_optimizer_impl_digest=production_optimizer_digest(
            log.spec.optimizer_config.identity()
        ),
        request_id="optimizer-request-one",
        distributed_work_order_id=work_order_id,
        prepared_result_id=result_id,
    )


def test_final_transition_binds_exact_work_order_and_prepared_result():
    log = _initialize(distributed=True)
    proposal = _proposal(log)
    prepared = _prepare(log, proposal)
    assert prepared.commit.distributed_work_order_id == "fwo2-one"
    assert prepared.commit.prepared_result_id == "pfr-one"
    log.commit_prepared(prepared)
    replay = log.replay(force_full=True)
    commit = replay.commits[-1]
    assert commit.commit_id == prepared.commit.commit_id
    assert commit.distributed_work_order_id == "fwo2-one"
    assert commit.prepared_result_id == "pfr-one"


def test_distributed_binding_is_paired_and_rejected_for_central_generation():
    distributed = _initialize(distributed=True)
    proposal = _proposal(distributed)
    with pytest.raises(CommitConflict, match="paired"):
        _prepare(distributed, proposal, result_id=None)

    central = _initialize(distributed=False)
    proposal = _proposal(central)
    with pytest.raises(CommitConflict, match="only distributed"):
        _prepare(central, proposal)
