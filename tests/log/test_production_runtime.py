from __future__ import annotations

from dataclasses import replace
import hashlib
import inspect

import pytest
import torch
from safetensors.torch import save as save_safetensors_bytes

import fs_diloco.log.replay as replay_module
from fs_diloco.log import (
    CRASH_POINTS,
    CommitConflict,
    InjectedLogCrash,
    ProductionTransactionalLog,
    RunSpec,
    VerificationError,
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


def _initialize(run_id: str, *, num_fragments: int = 1):
    backend = InMemoryStorageBackend()
    spec = _spec(run_id)
    params = torch.tensor([0.0, 0.0])
    outer = init_outer_state(params, spec.optimizer_config)
    log = ProductionTransactionalLog.initialize(
        backend,
        spec,
        {
            fragment_id: (
                encode_production_params(params),
                encode_production_outer_state(outer),
            )
            for fragment_id in range(num_fragments)
        },
    )
    return backend, log


def _proposal(
    log: ProductionTransactionalLog,
    *,
    learner: str,
    sequence: int,
    values,
    fragment_id: int = 0,
):
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
            "fragment_id": fragment_id,
            "base_commit_id": view.commit_id,
            "base_commit_seq": view.commit_seq,
            "base_fragment_version": view.fragments[fragment_id].version,
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


def _prepare(log, manifest, values, *, outer_step: int = 0):
    params = torch.tensor(values, dtype=torch.float32)
    outer = init_outer_state(params, log.spec.optimizer_config)
    if outer_step:
        outer["step"] = outer["step"].new_tensor(outer_step)
    return log.prepare_transition(
        fragment_id=manifest.fragment_id,
        selected_proposal_ids=[manifest.proposal_id],
        new_params=encode_production_params(params),
        new_outer_state=encode_production_outer_state(outer),
        aggregate_digest=canonical_digest({"proposal": manifest.proposal_id}),
        outer_optimizer_impl_digest=production_optimizer_digest(
            log.spec.optimizer_config.identity()
        ),
    )


def _corrupt_object(backend, key: str):
    original = backend._objects[key]
    corrupted = bytearray(original.data)
    corrupted[-1] ^= 1
    backend._objects[key] = replace(original, data=bytes(corrupted))
    return original


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


@pytest.mark.parametrize("crash_at", CRASH_POINTS)
def test_production_crash_matrix_recovers_from_durable_head_only(crash_at):
    _, log = _initialize(f"production-crash-{crash_at}")
    manifest = _proposal(log, learner="learner-0", sequence=1, values=[1.0, 2.0])

    with pytest.raises(InjectedLogCrash):
        log.commit_transition(
            fragment_id=manifest.fragment_id,
            selected_proposal_ids=[manifest.proposal_id],
            new_params=encode_production_params(torch.tensor([0.5, 1.0])),
            new_outer_state=encode_production_outer_state(
                init_outer_state(
                    torch.tensor([0.5, 1.0]),
                    log.spec.optimizer_config,
                )
            ),
            aggregate_digest=canonical_digest({"proposal": manifest.proposal_id}),
            outer_optimizer_impl_digest=production_optimizer_digest(
                log.spec.optimizer_config.identity()
            ),
            crash_at=crash_at,
        )

    expected_seq = 1 if crash_at == "after_head_cas" else 0
    recovered = log.replay(force_full=True)
    assert recovered.head_frontier.commit_seq == expected_seq
    assert (manifest.proposal_id in recovered.consumption) is (
        expected_seq == 1
    )
    reopened = ProductionTransactionalLog.open(
        log.backend,
        log.spec.run_id,
        log.spec.run_generation,
    )
    assert reopened.replay(force_full=True) == recovered


def test_fresh_process_recovers_identical_runtime_view_without_local_state():
    backend, log = _initialize("production-restart")
    manifest = _proposal(log, learner="learner-0", sequence=1, values=[1.0, 2.0])
    log.commit_prepared(_prepare(log, manifest, [0.5, 1.0]))
    first = build_runtime_view(log)
    reopened = ProductionTransactionalLog.open(
        backend,
        log.spec.run_id,
        log.spec.run_generation,
    )
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


def test_production_cas_conflict_requires_replay_and_fresh_prepare():
    _, log = _initialize("production-cas-reprepare")
    left = _proposal(log, learner="learner-left", sequence=1, values=[1.0, 2.0])
    right = _proposal(log, learner="learner-right", sequence=1, values=[2.0, 3.0])
    prepared_left = _prepare(log, left, [0.5, 1.0])
    stale_right = _prepare(log, right, [1.0, 1.5])

    log.commit_prepared(prepared_left)
    with pytest.raises(CommitConflict):
        log.commit_prepared(stale_right)

    refreshed = log.replay(force_full=True)
    assert refreshed.head_frontier.commit_seq == 1
    assert right.proposal_id not in refreshed.consumption
    prepared_right = _prepare(log, right, [1.0, 1.5])
    assert prepared_right.parent_head != stale_right.parent_head
    log.commit_prepared(prepared_right)
    final = log.replay(force_full=True)
    assert final.head_frontier.commit_seq == 2
    assert set(final.consumption) == {left.proposal_id, right.proposal_id}


def test_production_replay_routes_around_scalar_protocol_validator():
    source = inspect.getsource(replay_module._replay_production_log)
    assert "validate_production_tensor_payload(" in source
    assert "validate_tensor_payload(" not in source


@pytest.mark.parametrize("num_fragments", [1, 2])
def test_cached_and_forced_full_replay_are_equal_at_every_prefix(num_fragments):
    _, log = _initialize(f"production-prefix-{num_fragments}", num_fragments=num_fragments)
    assert log.replay() == log.replay(force_full=True)
    for index in range(10):
        fragment_id = index % num_fragments
        values = [float(index + 1), float(index + 2)]
        manifest = _proposal(
            log,
            learner=f"learner-{index}",
            sequence=1,
            values=values,
            fragment_id=fragment_id,
        )
        log.commit_prepared(_prepare(log, manifest, values))
        cached = log.replay()
        strict = log.replay(force_full=True)
        assert cached == strict


def test_verified_immutable_tensor_cache_is_process_local_and_discardable():
    backend, log = _initialize("production-cache")
    manifest = _proposal(log, learner="learner-0", sequence=1, values=[1.0, 2.0])
    log.commit_prepared(_prepare(log, manifest, [0.5, 1.0]))
    first = log.replay(force_full=True)

    history_start = len(backend.history)
    assert log.replay() == first
    cached_reads = backend.history[history_start:]
    large_keys = {
        manifest.payload_key,
        *(
            fragment.params_ref.key
            for frontier in first.frontiers
            for fragment in frontier.fragments.values()
        ),
        *(
            fragment.outer_state_ref.key
            for frontier in first.frontiers
            for fragment in frontier.fragments.values()
        ),
    }
    assert not any(
        record.operation == "get" and record.key in large_keys for record in cached_reads
    )

    reopened = ProductionTransactionalLog.open(
        backend,
        log.spec.run_id,
        log.spec.run_generation,
    )
    history_start = len(backend.history)
    assert reopened.replay(force_full=True) == first
    strict_reads = backend.history[history_start:]
    assert any(
        record.operation == "get" and record.key == manifest.payload_key
        for record in strict_reads
    )


@pytest.mark.parametrize(
    "object_kind",
    ["proposal", "params", "outer_state", "commit", "frontier"],
)
def test_corrupt_new_object_fails_before_replay_cache_replacement(object_kind):
    backend, log = _initialize(f"production-corrupt-new-{object_kind}")
    manifest = _proposal(log, learner="learner-0", sequence=1, values=[1.0, 2.0])
    prepared = _prepare(log, manifest, [0.5, 1.0], outer_step=1)
    log.commit_prepared(prepared)
    key = {
        "proposal": manifest.payload_key,
        "params": prepared.commit.new_params_ref.key,
        "outer_state": prepared.commit.new_outer_state_ref.key,
        "commit": prepared.commit_ref.key,
        "frontier": prepared.frontier_ref.key,
    }[object_kind]
    original = _corrupt_object(backend, key)
    cache_before = (
        set(log._replay_cache.proposal_payloads),
        dict(log._replay_cache.params_numels),
        dict(log._replay_cache.outer_numels),
    )

    with pytest.raises(VerificationError):
        log.replay()
    assert cache_before == (
        log._replay_cache.proposal_payloads,
        log._replay_cache.params_numels,
        log._replay_cache.outer_numels,
    )

    backend._objects[key] = original
    assert log.replay().head_frontier.commit_seq == 1


def test_forced_full_replay_detects_historical_object_corruption():
    backend, log = _initialize("production-corrupt-historical")
    manifest = _proposal(log, learner="learner-0", sequence=1, values=[1.0, 2.0])
    log.commit_prepared(_prepare(log, manifest, [0.5, 1.0]))
    assert log.replay().head_frontier.commit_seq == 1
    original = _corrupt_object(backend, manifest.payload_key)

    # Cached replay relies on the backend's immutable-create contract.
    assert log.replay().head_frontier.commit_seq == 1
    with pytest.raises(VerificationError):
        log.replay(force_full=True)

    backend._objects[manifest.payload_key] = original
