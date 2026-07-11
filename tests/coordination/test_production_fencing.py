from __future__ import annotations

import hashlib

import pytest
import torch
from safetensors.torch import save as save_safetensors_bytes

from fs_diloco.coordination import OwnerToken
from fs_diloco.log import (
    CRASH_POINTS,
    CommitConflict,
    InjectedLogCrash,
    ProductionTransactionalLog,
    RunSpec,
)
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


def _initialize(run_id: str):
    backend = InMemoryStorageBackend()
    spec = RunSpec(
        run_id=run_id,
        run_generation=0,
        model_revision="production-fenced-test",
        parameter_index_digest=_digest("params"),
        fragment_layout_digest=_digest("layout"),
        outer_optimizer_schema_digest=_digest("outer"),
        payload_codec=PRODUCTION_CODEC,
        coordination_protocol="head-fenced-v1",
    )
    params = torch.tensor([0.0, 0.0])
    log = ProductionTransactionalLog.initialize(
        backend,
        spec,
        {
            0: (
                encode_production_params(params),
                encode_production_outer_state(
                    init_outer_state(params, spec.optimizer_config)
                ),
            )
        },
    )
    return backend, log


def _proposal(log: ProductionTransactionalLog, learner: str = "learner-a"):
    view = build_runtime_view(log)
    payload = save_safetensors_bytes(
        {"local_params": torch.tensor([1.0, 2.0], dtype=torch.float32)}
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
            "payload_size": len(payload),
            "payload_sha256": digest,
            "parameter_index_digest": log.spec.parameter_index_digest,
            "fragment_layout_digest": log.spec.fragment_layout_digest,
            "outer_optimizer_schema_digest": log.spec.outer_optimizer_schema_digest,
        }
    )
    log.publish_proposal(manifest, payload)
    return manifest


def _prepare(log: ProductionTransactionalLog, proposal: ProposalManifest, request_id: str):
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
        request_id=request_id,
    )


def test_epoch_bump_is_control_only_and_optimizer_count_is_separate():
    _backend, log = _initialize("fenced-control-count")
    genesis = build_runtime_view(log)
    token = OwnerToken("syncer-a", "session-a", 1)
    log.activate_owner(token=token, request_id="fence-a")
    fenced = build_runtime_view(log)

    assert fenced.commit_seq == 1
    assert fenced.optimizer_transition_count == 0
    assert fenced.fragments == genesis.fragments
    assert fenced.owner_id == token.owner_id
    assert fenced.owner_session_id == token.owner_session_id
    assert fenced.fencing_epoch == token.fencing_epoch

    proposal = _proposal(log)
    log.commit_prepared(_prepare(log, proposal, "optimizer-a"))
    committed = build_runtime_view(log)
    assert committed.commit_seq == 2
    assert committed.optimizer_transition_count == 1


def test_stale_prepared_optimizer_is_fenced_after_takeover():
    backend, active = _initialize("fenced-stale-prepared")
    active.activate_owner(
        token=OwnerToken("syncer-a", "session-a", 1), request_id="fence-a"
    )
    proposal = _proposal(active)
    stale = _prepare(active, proposal, "optimizer-stale")

    standby = ProductionTransactionalLog.open(backend, active.spec.run_id, 0)
    standby.activate_owner(
        token=OwnerToken("syncer-b", "session-b", 2), request_id="fence-b"
    )
    with pytest.raises(CommitConflict):
        active.commit_prepared(stale)
    assert active._owner_token is None
    view = build_runtime_view(standby)
    assert view.owner_id == "syncer-b"
    assert view.optimizer_transition_count == 0


def test_takeover_uses_empty_cache_strict_replay():
    backend, active = _initialize("fenced-empty-cache")
    active.activate_owner(
        token=OwnerToken("syncer-a", "session-a", 1), request_id="fence-a"
    )
    active.replay()
    history_start = len(backend.history)

    standby = ProductionTransactionalLog.open(backend, active.spec.run_id, 0)
    standby.activate_owner(
        token=OwnerToken("syncer-b", "session-b", 2), request_id="fence-b"
    )
    takeover_reads = backend.history[history_start:]
    genesis_refs = {
        ref.key
        for fragment in build_runtime_view(standby).fragments.values()
        for ref in (fragment.params_ref, fragment.outer_state_ref)
    }
    assert all(key in {record.key for record in takeover_reads if record.operation == "get"} for key in genesis_refs)


def test_authoritative_stop_replays_and_forbids_more_optimizer_work():
    backend, log = _initialize("fenced-stop")
    log.activate_owner(
        token=OwnerToken("syncer-a", "session-a", 1), request_id="fence-a"
    )
    log.commit_stop(reason="operator_requested", request_id="stop-a")
    stopped = build_runtime_view(log)
    assert stopped.commit_seq == 2
    assert stopped.optimizer_transition_count == 0
    assert stopped.authoritative_stop is not None
    assert stopped.authoritative_stop.reason == "operator_requested"

    reopened = ProductionTransactionalLog.open(backend, log.spec.run_id, 0)
    assert build_runtime_view(reopened) == stopped
    proposal = _proposal(log)
    with pytest.raises(CommitConflict):
        _prepare(log, proposal, "optimizer-after-stop")


def test_control_response_loss_resolves_from_ancestry_after_successor():
    backend, log = _initialize("fenced-control-response-loss")
    token_a = OwnerToken("syncer-a", "session-a", 1)
    prepared = log.prepare_control_transition(
        control_kind="epoch_bump",
        token=token_a,
        request_id="fence-a",
    )
    with pytest.raises(InjectedLogCrash):
        log.commit_prepared(prepared, crash_at="after_head_cas")

    standby = ProductionTransactionalLog.open(backend, log.spec.run_id, 0)
    standby.activate_owner(
        token=OwnerToken("syncer-b", "session-b", 2), request_id="fence-b"
    )
    resolved = standby.resolve_mutation(
        request_id=prepared.commit.request_id,
        request_digest=prepared.commit.request_digest,
    )
    assert resolved is not None
    assert resolved.commit_id == prepared.commit.commit_id
    assert build_runtime_view(standby).commit_seq == 2


def test_optimizer_response_loss_resolves_after_takeover_successor():
    backend, log = _initialize("fenced-optimizer-response-loss")
    log.activate_owner(
        token=OwnerToken("syncer-a", "session-a", 1), request_id="fence-a"
    )
    proposal = _proposal(log)
    prepared = _prepare(log, proposal, "optimizer-a")
    with pytest.raises(InjectedLogCrash):
        log.commit_prepared(prepared, crash_at="after_head_cas")

    standby = ProductionTransactionalLog.open(backend, log.spec.run_id, 0)
    standby.activate_owner(
        token=OwnerToken("syncer-b", "session-b", 2), request_id="fence-b"
    )
    resolved = standby.resolve_mutation(
        request_id=prepared.commit.request_id,
        request_digest=prepared.commit.request_digest,
    )
    assert resolved is not None
    assert resolved.commit_id == prepared.commit.commit_id
    assert build_runtime_view(standby).optimizer_transition_count == 1


def test_stop_response_loss_replays_from_authority():
    backend, log = _initialize("fenced-stop-response-loss")
    log.activate_owner(
        token=OwnerToken("syncer-a", "session-a", 1), request_id="fence-a"
    )
    prepared = log.prepare_control_transition(
        control_kind="stop",
        token=OwnerToken("syncer-a", "session-a", 1),
        request_id="stop-a",
        stop_reason="operator_requested",
    )
    with pytest.raises(InjectedLogCrash):
        log.commit_prepared(prepared, crash_at="after_head_cas")

    reopened = ProductionTransactionalLog.open(backend, log.spec.run_id, 0)
    resolved = reopened.resolve_mutation(
        request_id=prepared.commit.request_id,
        request_digest=prepared.commit.request_digest,
    )
    assert resolved is not None
    assert resolved.commit_id == prepared.commit.commit_id
    assert build_runtime_view(reopened).authoritative_stop.reason == "operator_requested"


def test_reused_optimizer_request_id_with_distinct_content_fails_before_output_puts():
    backend, log = _initialize("fenced-optimizer-request-conflict")
    log.activate_owner(
        token=OwnerToken("syncer-a", "session-a", 1), request_id="fence-a"
    )
    first = _proposal(log, learner="learner-a")
    log.commit_prepared(_prepare(log, first, "optimizer-shared"))
    second = _proposal(log, learner="learner-b")
    history_start = len(backend.history)
    with pytest.raises(CommitConflict, match="request identity conflicts"):
        _prepare(log, second, "optimizer-shared")
    assert not any(
        record.operation == "put_immutable"
        for record in backend.history[history_start:]
    )


@pytest.mark.parametrize("crash_at", CRASH_POINTS)
def test_fenced_optimizer_crash_matrix_has_no_stuck_selection_and_can_continue(crash_at):
    backend, active = _initialize(f"fenced-optimizer-crash-{crash_at}")
    active.activate_owner(
        token=OwnerToken("syncer-a", "session-a", 1), request_id="fence-a"
    )
    proposal = _proposal(active, learner="learner-before-crash")
    with pytest.raises(InjectedLogCrash):
        active.commit_transition(
            fragment_id=0,
            selected_proposal_ids=[proposal.proposal_id],
            new_params=encode_production_params(torch.tensor([0.5, 1.0])),
            new_outer_state=encode_production_outer_state(
                init_outer_state(torch.tensor([0.5, 1.0]), active.spec.optimizer_config)
            ),
            aggregate_digest=canonical_digest({"proposal": proposal.proposal_id}),
            outer_optimizer_impl_digest=production_optimizer_digest(
                active.spec.optimizer_config.identity()
            ),
            request_id="optimizer-before-crash",
            crash_at=crash_at,
        )
    expected = 1 if crash_at == "after_head_cas" else 0
    assert build_runtime_view(active, force_full=True).optimizer_transition_count == expected

    standby = ProductionTransactionalLog.open(backend, active.spec.run_id, 0)
    standby.activate_owner(
        token=OwnerToken("syncer-b", "session-b", 2), request_id="fence-b"
    )
    fresh = _proposal(standby, learner="learner-after-crash")
    standby.commit_prepared(_prepare(standby, fresh, "optimizer-after-crash"))
    final = build_runtime_view(standby, force_full=True)
    assert final.optimizer_transition_count == expected + 1
    assert fresh.proposal_id in final.consumed_proposal_ids


@pytest.mark.parametrize(
    "crash_at",
    [
        "before_commit_put",
        "after_commit_put",
        "before_frontier_put",
        "after_frontier_put",
        "before_head_cas",
        "after_head_cas",
    ],
)
def test_authoritative_stop_crash_matrix_retries_or_resolves(crash_at):
    backend, log = _initialize(f"fenced-stop-crash-{crash_at}")
    token = OwnerToken("syncer-a", "session-a", 1)
    log.activate_owner(token=token, request_id="fence-a")
    with pytest.raises(InjectedLogCrash):
        log.commit_stop(
            reason="operator_requested", request_id="stop-a", crash_at=crash_at
        )
    reopened = ProductionTransactionalLog.open(backend, log.spec.run_id, 0)
    view = build_runtime_view(reopened, force_full=True)
    if crash_at == "after_head_cas":
        assert view.authoritative_stop is not None
    else:
        assert view.authoritative_stop is None
        log.commit_stop(reason="operator_requested", request_id="stop-a")
        view = build_runtime_view(log, force_full=True)
    assert view.authoritative_stop.reason == "operator_requested"
    assert view.optimizer_transition_count == 0
