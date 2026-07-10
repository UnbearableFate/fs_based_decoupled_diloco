from __future__ import annotations

import hashlib

import pytest
import torch
from safetensors.torch import save as save_safetensors_bytes

from fs_diloco.log import InjectedLogCrash, ProductionTransactionalLog, RunSpec
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


def _spec(run_id: str) -> RunSpec:
    return RunSpec(
        run_id=run_id,
        run_generation=0,
        model_revision="production-test",
        parameter_index_digest=_digest("params"),
        fragment_layout_digest=_digest("layout"),
        outer_optimizer_schema_digest=_digest("outer"),
        payload_codec=PRODUCTION_CODEC,
    )


def _initialize(run_id: str):
    backend = InMemoryStorageBackend()
    spec = _spec(run_id)
    params = torch.tensor([0.0, 0.0])
    outer = init_outer_state(params, spec.optimizer_config)
    log = ProductionTransactionalLog.initialize(
        backend,
        spec,
        {0: (encode_production_params(params), encode_production_outer_state(outer))},
    )
    return backend, log


def _proposal(log: ProductionTransactionalLog, *, learner: str, sequence: int, values):
    view = build_runtime_view(log)
    payload = save_safetensors_bytes(
        {"local_params": torch.tensor(values, dtype=torch.float32)}
    )
    digest = hashlib.sha256(payload).hexdigest()
    manifest = ProposalManifest.with_computed_id(
        {
            "manifest_type": "proposal",
            "protocol_version": 2,
            "run_id": view.run_id,
            "run_generation": view.run_generation,
            "model_revision": log.spec.model_revision,
            "learner_id": learner,
            "learner_session_id": f"session-{learner}",
            "sequence": sequence,
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
            "payload_size": len(payload),
            "payload_sha256": digest,
            "parameter_index_digest": log.spec.parameter_index_digest,
            "fragment_layout_digest": log.spec.fragment_layout_digest,
            "outer_optimizer_schema_digest": log.spec.outer_optimizer_schema_digest,
        }
    )
    log.publish_proposal(manifest, payload)
    return manifest


def _prepare(log, manifest, values):
    params = torch.tensor(values, dtype=torch.float32)
    outer = init_outer_state(params, log.spec.optimizer_config)
    return log.prepare_transition(
        fragment_id=0,
        selected_proposal_ids=[manifest.proposal_id],
        new_params=encode_production_params(params),
        new_outer_state=encode_production_outer_state(outer),
        aggregate_digest=canonical_digest({"proposal": manifest.proposal_id}),
        outer_optimizer_impl_digest=production_optimizer_digest(
            log.spec.optimizer_config.identity()
        ),
    )


def test_prepared_production_outputs_are_invisible_until_head_cas():
    _, log = _initialize("production-partial")
    manifest = _proposal(log, learner="learner-0", sequence=1, values=[1.0, 2.0])
    prepared = _prepare(log, manifest, [0.5, 1.0])
    before = build_runtime_view(log)
    assert before.commit_seq == 0
    assert manifest.proposal_id not in before.consumed_proposal_ids
    log.commit_prepared(prepared)
    after = build_runtime_view(log)
    assert after.commit_seq == 1
    assert manifest.proposal_id in after.consumed_proposal_ids
    assert after.fragments[0].params_ref == prepared.commit.new_params_ref
    assert after.fragments[0].outer_state_ref == prepared.commit.new_outer_state_ref


def test_fresh_process_recovers_identical_runtime_view_without_local_state():
    backend, log = _initialize("production-restart")
    manifest = _proposal(log, learner="learner-0", sequence=1, values=[1.0, 2.0])
    log.commit_prepared(_prepare(log, manifest, [0.5, 1.0]))
    first = build_runtime_view(log)
    reopened = ProductionTransactionalLog.open(backend, first.run_id, first.run_generation)
    second = build_runtime_view(reopened)
    assert second == first


def test_response_loss_is_resolved_from_ancestry_after_successor():
    _, log = _initialize("production-response-loss")
    first = _proposal(log, learner="learner-0", sequence=1, values=[1.0, 2.0])
    delayed = _prepare(log, first, [0.5, 1.0])
    with pytest.raises(InjectedLogCrash):
        log.commit_prepared(delayed, crash_at="after_head_cas")
    second = _proposal(log, learner="learner-1", sequence=1, values=[2.0, 3.0])
    log.commit_prepared(_prepare(log, second, [1.0, 2.0]))
    resolved = log.resolve_prepared(delayed)
    assert resolved is not None
    assert resolved.status == "already_committed"
    assert build_runtime_view(log).consumed_proposal_ids == {
        first.proposal_id,
        second.proposal_id,
    }
