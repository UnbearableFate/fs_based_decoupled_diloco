"""SQLite-free DuraLoCo syncer driven by one committed transition log."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import socket
import time
from typing import Any
import uuid

import torch
from safetensors.torch import load as load_safetensors_bytes

from .atomic_io import atomic_write_json, safe_read_json
from .config import Config, resolve_config, write_resolved_config
from .coordination import CoordinationConflict, LeaseManager, LeaseMutation, OwnerToken
from .constants import FORMAT_VERSION, LEARNER_STATUS_STOPPED, learner_id_from_index
from .fragment_codec import extract_fragment, materialize_full_from_fragments, save_fragment_weight
from .fragment_index import build_fragment_index, fragment_layout_digest, load_fragment_index, save_fragment_index
from .hf_model import choose_device, load_causal_lm_and_tokenizer
from .logging_utils import JsonlLogger, log_uncaught_exception
from .metrics import SYNCER_METRIC_FIELDS, append_csv_row
from .outer_optim import init_outer_state
from .param_index import build_param_index, flatten_trainable_params, load_param_index, param_index_digest
from .paths import RunPaths, prepare_run_dirs
from .proposal_catalog import CatalogEntry, ProposalCatalog
from .protocol.canonical_json import canonical_digest
from .retention import cleanup_all_learner_update_artifacts, cleanup_syncer_model_artifacts
from .runtime_view import RuntimeView, build_runtime_view
from .syncer_core import (
    PlanningCandidate,
    apply_outer_transition,
    build_fragment_plan,
    build_transition_attempt,
    reduce_fragment,
)
from .storage import InjectedTimeout, NotFound, PosixStorageBackend
from .tensor_codec import save_global_weights, save_outer_state
from .testing.deterministic_reference import ReferenceOptimizerConfig, ReferenceWeightingConfig
from .wandb_logging import (
    syncer_wandb_project_name,
    syncer_wandb_run_name,
    syncer_wandb_tags,
    wandb_config,
    wandb_is_disabled,
)
from .log.codec import verified_get
from .log.errors import CommitConflict, RunInitializationError
from .log.production import ProductionTransactionalLog
from .log.production_codec import (
    PRODUCTION_CODEC,
    decode_production_outer_state,
    decode_production_params,
    encode_production_outer_state,
    encode_production_params,
    production_optimizer_digest,
)
from .log.run import RunSpec


_SUCCESSFUL_STOP_REASONS = {"completed", "stop_after_outer_steps", "stop_after_global_tokens"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--shared-root")
    parser.add_argument("--num-learners", type=int)
    parser.add_argument("--owner-id")
    parser.add_argument("--owner-session-id")
    parser.add_argument("--standby", action="store_true")
    return parser.parse_args(argv)


def _optimizer_config(config: Config) -> ReferenceOptimizerConfig:
    return ReferenceOptimizerConfig(
        name=config.outer_optimizer.name,
        lr=config.outer_optimizer.lr,
        momentum=config.outer_optimizer.momentum,
        weight_decay=config.outer_optimizer.weight_decay,
        betas=config.outer_optimizer.betas,
        eps=config.outer_optimizer.eps,
    )


def _outer_schema_digest(config: Config) -> str:
    return canonical_digest(_optimizer_config(config).identity())


def _run_spec(
    config: Config,
    *,
    parameter_digest: str,
    layout_digest: str,
) -> RunSpec:
    return RunSpec(
        run_id=config.run.run_id or "",
        run_generation=config.init.run_generation,
        model_revision=config.model.name_or_path,
        parameter_index_digest=parameter_digest,
        fragment_layout_digest=layout_digest,
        outer_optimizer_schema_digest=_outer_schema_digest(config),
        optimizer_config=_optimizer_config(config),
        weighting_config=ReferenceWeightingConfig(staleness_lambda=0.2),
        max_global_staleness=config.sync.max_staleness_versions,
        max_fragment_staleness=config.sync.max_staleness_versions,
        payload_codec=PRODUCTION_CODEC,
        coordination_protocol="head-fenced-v1",
    )


def _latest_common(config: Config, view: RuntimeView) -> dict[str, Any]:
    return {
        "format_version": FORMAT_VERSION,
        "run_id": config.run.run_id,
        "run_generation": view.run_generation,
        "version": view.commit_seq,
        "global_merge_event": view.optimizer_transition_count,
        "optimizer_transition_count": view.optimizer_transition_count,
        "fragment_versions": {
            str(fragment_id): state.version
            for fragment_id, state in sorted(view.fragments.items())
        },
        "committed_interval_identities": [
            list(item) for item in sorted(view.committed_interval_identities)
        ],
        "commit_id": view.commit_id,
        "commit_seq": view.commit_seq,
        "frontier_sha256": view.frontier_sha256,
        "committed_state_digest": view.committed_state_digest,
        "runtime_view_digest": view.view_digest,
        "created_at": time.time(),
        "total_seen_tokens": view.total_seen_tokens,
        "fencing_epoch": view.fencing_epoch,
        "owner_id": view.owner_id,
        "owner_session_id": view.owner_session_id,
        "authority": "committed-transition-log-and-head-fence",
    }


def publish_materialized_view(
    *,
    config: Config,
    paths: RunPaths,
    view: RuntimeView,
    param_index: dict[str, Any],
    fragment_index: dict[str, Any],
    fragment_thetas: dict[int, torch.Tensor],
    outer_states: dict[int, dict[str, torch.Tensor]],
) -> Path:
    fragment_versions = {
        fragment_id: state.version for fragment_id, state in view.fragments.items()
    }
    for fragment_id, theta in fragment_thetas.items():
        version = fragment_versions[fragment_id]
        save_fragment_weight(paths.fragment_weight_path(fragment_id, version), theta)
        save_outer_state(
            paths.fragment_outer_optim_path(fragment_id, version),
            theta,
            outer_states[fragment_id],
        )
    full = materialize_full_from_fragments(
        fragment_thetas,
        fragment_index,
        int(param_index["total_numel"]),
    )
    weight_path = paths.global_weight_path(view.commit_seq)
    save_global_weights(weight_path, full, param_index)
    if len(fragment_thetas) == 1:
        optim_path = paths.outer_optim_path(view.commit_seq)
        save_outer_state(optim_path, full, outer_states[0])
        payload = {
            **_latest_common(config, view),
            "weight_path": str(weight_path),
            "optim_path": str(optim_path),
            "param_index_path": str(paths.param_index_json),
        }
    else:
        fragments = {
            str(fragment_id): {
                "version": fragment_versions[fragment_id],
                "weight_path": str(
                    paths.fragment_weight_path(fragment_id, fragment_versions[fragment_id])
                ),
                "optim_path": str(
                    paths.fragment_outer_optim_path(fragment_id, fragment_versions[fragment_id])
                ),
                "producing_commit_id": view.fragments[fragment_id].producing_commit_id,
            }
            for fragment_id in sorted(fragment_thetas)
        }
        payload = {
            **_latest_common(config, view),
            "latest_kind": "fragment",
            "latest_layout_version": 3,
            "param_index_path": str(paths.param_index_json),
            "fragment_index_path": str(paths.fragment_index_json),
            "materialized_weight_path": str(weight_path),
            "fragments": fragments,
        }
    atomic_write_json(paths.latest_json, payload)
    return weight_path


def _load_committed_tensors(
    log: ProductionTransactionalLog,
    view: RuntimeView,
    *,
    device: torch.device | str,
) -> tuple[dict[int, torch.Tensor], dict[int, dict[str, torch.Tensor]]]:
    params: dict[int, torch.Tensor] = {}
    states: dict[int, dict[str, torch.Tensor]] = {}
    for fragment_id, fragment in view.fragments.items():
        params[fragment_id] = decode_production_params(
            verified_get(log.backend, fragment.params_ref, commit_seq=view.commit_seq),
            device=device,
        )
        states[fragment_id] = decode_production_outer_state(
            verified_get(log.backend, fragment.outer_state_ref, commit_seq=view.commit_seq),
            device=device,
        )
    return params, states


def initialize_generation(
    config: Config,
    paths: RunPaths,
    backend: PosixStorageBackend,
    *,
    device: torch.device | str,
    run_spec_factory=_run_spec,
) -> tuple[
    ProductionTransactionalLog,
    RuntimeView,
    dict[str, Any],
    dict[str, Any],
    dict[int, torch.Tensor],
    dict[int, dict[str, torch.Tensor]],
]:
    if paths.latest_json.exists():
        raise FileExistsError(
            f"{paths.latest_json} exists; resume this generation or choose a new run generation"
        )
    model, _ = load_causal_lm_and_tokenizer(config.model)
    model.to(device)
    param_index = build_param_index(model, model_name_or_path=config.model.name_or_path)
    theta = flatten_trainable_params(model, param_index, device=device).float()
    fragment_index = build_fragment_index(
        param_index,
        strategy=config.fragments.strategy if config.fragments.enabled else "full",
        num_fragments=config.fragments.num_fragments if config.fragments.enabled else 1,
        source_param_index_path=paths.param_index_json,
    )
    atomic_write_json(paths.param_index_json, param_index)
    save_fragment_index(fragment_index, paths.fragment_index_json)
    write_resolved_config(config, paths.resolved_config_yaml)
    fragments: dict[int, torch.Tensor] = {}
    states: dict[int, dict[str, torch.Tensor]] = {}
    initial: dict[int, tuple[bytes, bytes]] = {}
    for item in fragment_index["fragments"]:
        fragment_id = int(item["fragment_id"])
        fragment = extract_fragment(theta, fragment_index, fragment_id).float()
        state = init_outer_state(fragment, config.outer_optimizer)
        fragments[fragment_id] = fragment
        states[fragment_id] = state
        initial[fragment_id] = (
            encode_production_params(fragment),
            encode_production_outer_state(state),
        )
    spec = run_spec_factory(
        config,
        parameter_digest=param_index_digest(param_index),
        layout_digest=fragment_layout_digest(fragment_index),
    )
    log = ProductionTransactionalLog.initialize(backend, spec, initial)
    log.set_replay_validation_device(device)
    view = build_runtime_view(log)
    return log, view, param_index, fragment_index, fragments, states


def resume_generation(
    config: Config,
    paths: RunPaths,
    backend: PosixStorageBackend,
    *,
    device: torch.device | str,
) -> tuple[
    ProductionTransactionalLog,
    RuntimeView,
    dict[str, Any],
    dict[str, Any],
    dict[int, torch.Tensor],
    dict[int, dict[str, torch.Tensor]],
]:
    if config.init.resume_version != "latest":
        raise ValueError("exact resume only supports the authoritative current head")
    param_index = load_param_index(paths.param_index_json)
    fragment_index = load_fragment_index(paths.fragment_index_json)
    log = ProductionTransactionalLog.open(
        backend,
        config.run.run_id or "",
        config.init.run_generation,
    )
    log.set_replay_validation_device(device)
    if log.spec.parameter_index_digest != param_index_digest(param_index):
        raise ValueError("parameter index differs from the committed run contract")
    if log.spec.fragment_layout_digest != fragment_layout_digest(fragment_index):
        raise ValueError("fragment layout differs from the committed run contract")
    view = build_runtime_view(log)
    fragments, states = _load_committed_tensors(log, view, device=device)
    return log, view, param_index, fragment_index, fragments, states


def _heartbeat_snapshot(paths: RunPaths, config: Config) -> dict[str, dict[str, Any]]:
    expected = {learner_id_from_index(index) for index in range(config.sync.num_learners)}
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(paths.heartbeats.glob("learner_*.json")):
        payload = safe_read_json(path)
        if not isinstance(payload, dict):
            continue
        learner_id = payload.get("learner_id")
        if payload.get("run_id") != config.run.run_id or learner_id not in expected:
            continue
        result[learner_id] = payload
    return result


def finite_local_training_complete(paths: RunPaths, config: Config) -> bool:
    if config.training.max_local_steps is None:
        return False
    heartbeats = _heartbeat_snapshot(paths, config)
    if len(heartbeats) < config.sync.num_learners:
        return False
    target = int(config.training.max_local_steps)
    return all(int(item.get("last_local_step") or 0) >= target for item in heartbeats.values())


def _candidate_paths(paths: RunPaths) -> list[Path]:
    return list(paths.updates_pending.glob("learner_*/update_*.meta.json"))


def collect_candidates(
    *,
    catalog: ProposalCatalog,
    log: ProductionTransactionalLog,
    view: RuntimeView,
    paths: RunPaths,
    config: Config,
    fragment_id: int,
) -> tuple[CatalogEntry, ...]:
    deadline = time.monotonic() + min(
        config.sync.grace_window.fixed_seconds,
        config.sync.grace_window.max_seconds,
    )
    selected: tuple[CatalogEntry, ...] = ()
    while True:
        entries = catalog.scan(
            metadata_paths=_candidate_paths(paths),
            log=log,
            view=view,
        )
        selected = catalog.select(
            entries,
            fragment_id=fragment_id,
            quorum_max=config.sync.quorum_max,
        )
        if len(selected) >= config.sync.quorum_max or time.monotonic() >= deadline:
            return selected
        time.sleep(min(config.sync.scan_interval_seconds, max(0.0, deadline - time.monotonic())))


def _load_selected_tensor(entry: CatalogEntry, payload: bytes, device) -> torch.Tensor:
    tensors = load_safetensors_bytes(payload)
    return tensors[entry.manifest.tensor_key].detach().to(device=device, dtype=torch.float32).reshape(-1)


def _publish_stop(
    paths: RunPaths,
    *,
    config: Config,
    view: RuntimeView,
    reason: str,
) -> None:
    if view.authoritative_stop is None:
        raise RuntimeError("cannot export stop.json without a committed stop fact")
    if view.authoritative_stop.reason != reason:
        raise RuntimeError("derived stop reason differs from committed stop fact")
    atomic_write_json(
        paths.stop_json,
        {
            "format_version": FORMAT_VERSION,
            "run_id": config.run.run_id,
            "run_generation": view.run_generation,
            "reason": reason,
            "version": view.commit_seq,
            "commit_id": view.commit_id,
            "frontier_sha256": view.frontier_sha256,
            "total_seen_tokens": view.total_seen_tokens,
            "created_at": time.time(),
            "stop_request_id": view.authoritative_stop.request_id,
            "stop_committed_at_seq": view.authoritative_stop.committed_at_seq,
            "authority": "derived-from-committed-stop-control-transition",
        },
    )


def _seconds_ns(value: float) -> int:
    return int(value * 1_000_000_000)


def _acquire_and_activate_owner(
    *,
    log: ProductionTransactionalLog,
    config: Config,
    owner_id: str,
    owner_session_id: str,
    logger: JsonlLogger,
    standby: bool = False,
) -> tuple[LeaseManager, Any, RuntimeView]:
    lease_manager = LeaseManager(
        log.backend,
        log.layout,
        max_clock_skew_ns=_seconds_ns(config.coordination.max_clock_skew_seconds),
    )
    wait_started = time.monotonic()
    attempt = 0
    while True:
        if standby:
            observed_view = build_runtime_view(log)
            if observed_view.authoritative_stop is not None:
                logger.event(
                    "standby_observed_authoritative_stop",
                    reason=observed_view.authoritative_stop.reason,
                    commit_seq=observed_view.commit_seq,
                )
                return lease_manager, None, observed_view
        head = log.load_head().manifest
        requested_at = time.time_ns()
        if standby:
            try:
                current_lease = lease_manager.load()
            except NotFound:
                current_lease = None
            if current_lease is not None:
                eligible_at = (
                    current_lease.record.expires_at_utc_ns
                    + _seconds_ns(config.coordination.max_clock_skew_seconds)
                )
                if requested_at < eligible_at:
                    logger.event(
                        "standby_wait",
                        observed_fencing_epoch=head.fencing_epoch,
                        lease_owner_id=current_lease.record.owner_id,
                        lease_sequence=current_lease.record.lease_sequence,
                        wait_seconds=(eligible_at - requested_at) / 1e9,
                    )
                    time.sleep(
                        min(
                            config.coordination.standby_poll_seconds,
                            max(0.0, (eligible_at - requested_at) / 1e9),
                        )
                    )
                    continue
        acquire_request_id = "lease-acquire-" + canonical_digest(
            {
                "run_id": log.spec.run_id,
                "run_generation": log.spec.run_generation,
                "owner_id": owner_id,
                "owner_session_id": owner_session_id,
                "observed_fencing_epoch": head.fencing_epoch,
                "attempt": attempt,
            }
        )
        mutation = LeaseMutation(
            operation="acquire",
            request_id=acquire_request_id,
            owner_id=owner_id,
            owner_session_id=owner_session_id,
            observed_fencing_epoch=head.fencing_epoch,
            requested_at_utc_ns=requested_at,
            ttl_ns=_seconds_ns(config.coordination.lease_ttl_seconds),
        )
        acquire_start = time.monotonic()
        try:
            loaded_lease = lease_manager.acquire(mutation)
            break
        except CoordinationConflict as exc:
            if not standby:
                raise
            logger.event(
                "standby_acquire_conflict",
                error=repr(exc),
                observed_fencing_epoch=head.fencing_epoch,
                attempt=attempt,
            )
            attempt += 1
            if time.monotonic() - wait_started > config.liveness.no_progress_timeout_seconds:
                raise TimeoutError("standby timed out waiting for takeover") from exc
            time.sleep(config.coordination.standby_poll_seconds)
    logger.event(
        "coordination_stage_completed",
        stage="lease_acquire",
        owner_id=owner_id,
        owner_session_id=owner_session_id,
        proposed_fencing_epoch=loaded_lease.record.proposed_fencing_epoch,
        lease_sequence=loaded_lease.record.lease_sequence,
        seconds=time.monotonic() - acquire_start,
    )
    # The former owner can commit stop while a standby is winning the
    # observational lease CAS.  Replay once more before preparing an epoch
    # bump so the terminal head does not create a guaranteed CAS-loser orphan.
    if standby:
        observed_view = build_runtime_view(log, force_full=True)
        if observed_view.authoritative_stop is not None:
            logger.event(
                "standby_observed_authoritative_stop_after_lease",
                reason=observed_view.authoritative_stop.reason,
                commit_seq=observed_view.commit_seq,
            )
            return lease_manager, None, observed_view
    token = loaded_lease.record.owner_token
    fence_request_id = "fence-" + canonical_digest(
        {
            "run_id": log.spec.run_id,
            "run_generation": log.spec.run_generation,
            **token.identity(),
            "lease_sequence": loaded_lease.record.lease_sequence,
        }
    )
    fence_start = time.monotonic()
    result = log.activate_owner(token=token, request_id=fence_request_id)
    view = build_runtime_view(log)
    logger.event(
        "coordination_stage_completed",
        stage="fence_commit_and_strict_replay",
        owner_id=owner_id,
        owner_session_id=owner_session_id,
        fencing_epoch=view.fencing_epoch,
        commit_seq=result.commit_seq,
        optimizer_transition_count=view.optimizer_transition_count,
        seconds=time.monotonic() - fence_start,
    )
    return lease_manager, loaded_lease, view


def _renew_owner_lease(
    *,
    lease_manager: LeaseManager,
    loaded_lease,
    config: Config,
    logger: JsonlLogger,
):
    now = time.time_ns()
    record = loaded_lease.record
    request_id = "lease-renew-" + canonical_digest(
        {
            "owner_id": record.owner_id,
            "owner_session_id": record.owner_session_id,
            "fencing_epoch": record.proposed_fencing_epoch,
            "lease_sequence": record.lease_sequence + 1,
        }
    )
    start = time.monotonic()
    renewed = lease_manager.renew(
        LeaseMutation(
            operation="renew",
            request_id=request_id,
            owner_id=record.owner_id,
            owner_session_id=record.owner_session_id,
            observed_fencing_epoch=record.proposed_fencing_epoch,
            requested_at_utc_ns=now,
            ttl_ns=_seconds_ns(config.coordination.lease_ttl_seconds),
        )
    )
    logger.event(
        "coordination_stage_completed",
        stage="lease_renew",
        fencing_epoch=renewed.record.proposed_fencing_epoch,
        lease_sequence=renewed.record.lease_sequence,
        renew_margin_seconds=(renewed.record.expires_at_utc_ns - now) / 1e9,
        seconds=time.monotonic() - start,
    )
    return renewed


def _init_wandb(config: Config, paths: RunPaths, logger: JsonlLogger, device, hostname):
    if wandb_is_disabled(config):
        logger.event("wandb_disabled")
        return None
    try:
        import wandb
    except Exception as exc:
        logger.event("wandb_unavailable", error=repr(exc))
        return None
    kwargs: dict[str, Any] = {
        "project": syncer_wandb_project_name(config),
        "name": syncer_wandb_run_name(config),
        "id": f"syncer-{config.run.run_id}",
        "resume": "allow",
        "config": wandb_config(
            config,
            device=str(device),
            hostname=hostname,
            shared_root=str(paths.shared_root),
        ),
        "tags": syncer_wandb_tags(config),
        "dir": str(paths.logs),
        "mode": os.environ.get("WANDB_MODE") or config.wandb.mode,
    }
    if config.wandb.entity:
        kwargs["entity"] = config.wandb.entity
    kwargs["group"] = config.wandb.group or config.run.name
    return wandb.init(**kwargs)


def _cleanup_success(
    *, paths: RunPaths, config: Config, logger: JsonlLogger, stop_reason: str
) -> None:
    if stop_reason not in _SUCCESSFUL_STOP_REASONS:
        return
    keep_syncer = config.io.keep_last_global_versions
    if keep_syncer is not None:
        cleanup_syncer_model_artifacts(paths, keep_last=keep_syncer, logger=logger)
    if config.io.keep_last_learner_update_versions is not None:
        cleanup_all_learner_update_artifacts(
            paths,
            keep_last=config.io.keep_last_learner_update_versions,
            logger=logger,
        )


def run_syncer(
    config: Config,
    *,
    owner_id: str | None = None,
    owner_session_id: str | None = None,
    standby: bool = False,
) -> None:
    paths = RunPaths(Path(config.run.shared_root or "."))
    prepare_run_dirs(paths, config.sync.num_learners)
    logger = JsonlLogger(paths.logs / "syncer.jsonl", "syncer")
    log_uncaught_exception(logger)
    device = choose_device()
    hostname = socket.gethostname()
    owner_id = owner_id or f"syncer-{hostname}"
    owner_session_id = owner_session_id or str(uuid.uuid4())
    backend = PosixStorageBackend(paths.authority)
    logger.event(
        "process_start",
        run_id=config.run.run_id,
        run_generation=config.init.run_generation,
        shared_root=str(paths.shared_root),
        authority_root=str(paths.authority),
        hostname=hostname,
        device=str(device),
        cuda_visible_devices=os.environ.get("CUDA_VISIBLE_DEVICES"),
        owner_id=owner_id,
        owner_session_id=owner_session_id,
        standby=standby,
    )
    wandb_run = _init_wandb(config, paths, logger, device, hostname)
    if config.init.resume or standby:
        if standby:
            wait_deadline = time.monotonic() + config.liveness.no_progress_timeout_seconds
            while True:
                try:
                    log, view, param_index, fragment_index, fragments, states = resume_generation(
                        config, paths, backend, device=device
                    )
                    break
                except (RunInitializationError, FileNotFoundError):
                    if time.monotonic() >= wait_deadline:
                        raise
                    logger.event("standby_wait_for_generation")
                    time.sleep(config.coordination.standby_poll_seconds)
        else:
            log, view, param_index, fragment_index, fragments, states = resume_generation(
                config, paths, backend, device=device
            )
        logger.event("log_only_resume", commit_seq=view.commit_seq, view_digest=view.view_digest)
    else:
        log, view, param_index, fragment_index, fragments, states = initialize_generation(
            config, paths, backend, device=device
        )
        logger.event("generation_initialized", commit_seq=0, view_digest=view.view_digest)
    if view.authoritative_stop is not None:
        publish_materialized_view(
            config=config,
            paths=paths,
            view=view,
            param_index=param_index,
            fragment_index=fragment_index,
            fragment_thetas=fragments,
            outer_states=states,
        )
        _publish_stop(
            paths,
            config=config,
            view=view,
            reason=view.authoritative_stop.reason,
        )
        logger.event(
            "process_exit",
            reason=view.authoritative_stop.reason,
            commit_seq=view.commit_seq,
        )
        if wandb_run is not None:
            wandb_run.finish(exit_code=0)
        return
    lease_manager, loaded_lease, view = _acquire_and_activate_owner(
        log=log,
        config=config,
        owner_id=owner_id,
        owner_session_id=owner_session_id,
        logger=logger,
        standby=standby,
    )
    if loaded_lease is None:
        publish_materialized_view(
            config=config,
            paths=paths,
            view=view,
            param_index=param_index,
            fragment_index=fragment_index,
            fragment_thetas=fragments,
            outer_states=states,
        )
        _publish_stop(
            paths,
            config=config,
            view=view,
            reason=view.authoritative_stop.reason,
        )
        logger.event(
            "process_exit",
            reason=view.authoritative_stop.reason,
            commit_seq=view.commit_seq,
        )
        if wandb_run is not None:
            wandb_run.finish(exit_code=0)
        return
    publish_materialized_view(
        config=config,
        paths=paths,
        view=view,
        param_index=param_index,
        fragment_index=fragment_index,
        fragment_thetas=fragments,
        outer_states=states,
    )
    catalog = ProposalCatalog(
        namespace_root=paths.shared_root,
        quarantine_root=paths.quarantine,
        validation_device=device,
    )
    optimizer_impl_digest = production_optimizer_digest(log.spec.optimizer_config.identity())
    last_progress = time.time()
    last_global = last_progress
    stop_reason = "completed"
    next_renew_monotonic = time.monotonic() + config.coordination.renew_interval_seconds
    try:
        while True:
            if view.authoritative_stop is not None:
                stop_reason = view.authoritative_stop.reason
                break
            if (
                time.monotonic() >= next_renew_monotonic
                or time.time_ns()
                >= loaded_lease.record.expires_at_utc_ns
                - _seconds_ns(config.coordination.renew_margin_seconds)
            ):
                loaded_lease = _renew_owner_lease(
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                )
                next_renew_monotonic = (
                    time.monotonic() + config.coordination.renew_interval_seconds
                )
            if (
                config.sync.stop_after_outer_steps is not None
                and view.optimizer_transition_count >= config.sync.stop_after_outer_steps
            ):
                stop_reason = "stop_after_outer_steps"
                break
            if (
                config.sync.stop_after_global_tokens is not None
                and view.total_seen_tokens >= config.sync.stop_after_global_tokens
            ):
                stop_reason = "stop_after_global_tokens"
                break
            fragment_id = 0 if len(view.fragments) == 1 else view.scheduler_cursor
            catalog_start = time.monotonic()
            selected = collect_candidates(
                catalog=catalog,
                log=log,
                view=view,
                paths=paths,
                config=config,
                fragment_id=fragment_id,
            )
            catalog_done = time.monotonic()
            terminal_drain = finite_local_training_complete(paths, config)
            if len(selected) < config.sync.quorum_min and not (terminal_drain and selected):
                logger.event(
                    "quorum_wait",
                    eligible=len(selected),
                    quorum_min=config.sync.quorum_min,
                    commit_seq=view.commit_seq,
                    fragment_id=fragment_id,
                )
                if time.time() - last_progress > config.liveness.no_progress_timeout_seconds:
                    stop_reason = "no_progress_timeout"
                    break
                time.sleep(config.sync.scan_interval_seconds)
                continue
            logger.event(
                "transaction_stage_completed",
                stage="catalog",
                target_commit_seq=view.commit_seq + 1,
                selected_count=len(selected),
                seconds=catalog_done - catalog_start,
            )

            tensors: dict[str, torch.Tensor] = {}
            for entry in selected:
                payload = catalog.load_payload(entry)
                log.publish_validated_proposal(entry.manifest, entry.payload)
                tensors[entry.proposal_id] = _load_selected_tensor(entry, payload, device)
            proposal_observation_done = time.monotonic()
            logger.event(
                "transaction_stage_completed",
                stage="proposal_observation",
                target_commit_seq=view.commit_seq + 1,
                seconds=proposal_observation_done - catalog_done,
            )
            current_fragment = fragments[fragment_id]
            plan = build_fragment_plan(
                (
                    PlanningCandidate(
                        proposal_id=entry.proposal_id,
                        learner_id=entry.manifest.learner_id,
                        sequence=entry.manifest.sequence,
                        fragment_id=entry.manifest.fragment_id,
                        target_tokens=entry.manifest.target_tokens_since_base,
                        base_fragment_version=entry.manifest.base_fragment_version,
                        payload_sha256=entry.manifest.payload_sha256,
                    )
                    for entry in selected
                ),
                fragment_id=fragment_id,
                current_fragment_version=view.fragments[fragment_id].version,
                parent_commit_id=view.commit_id,
                parent_commit_seq=view.commit_seq,
                parent_frontier_digest=view.frontier_sha256,
                quorum_max=len(selected),
                weighting_config=log.spec.weighting_config,
            )
            aggregate = reduce_fragment(
                plan=plan,
                proposal_tensors=tensors,
                current_params=current_fragment,
            )
            aggregation_done = time.monotonic()
            logger.event(
                "transaction_stage_completed",
                stage="aggregation",
                target_commit_seq=view.commit_seq + 1,
                seconds=aggregation_done - proposal_observation_done,
            )
            computation = apply_outer_transition(
                aggregate=aggregate,
                current_params=current_fragment,
                current_outer_state=states[fragment_id],
                optimizer_config=config.outer_optimizer,
                optimizer_implementation_digest=optimizer_impl_digest,
            )
            new_fragment = computation.new_params
            new_state = dict(computation.new_outer_state)
            outer_done = time.monotonic()
            logger.event(
                "transaction_stage_completed",
                stage="outer_step",
                target_commit_seq=view.commit_seq + 1,
                seconds=outer_done - aggregation_done,
            )
            attempt = build_transition_attempt(
                plan=plan,
                computation=computation,
                owner_id=owner_id,
                owner_session_id=owner_session_id,
                fencing_epoch=view.fencing_epoch,
                outer_optimizer_impl_digest=optimizer_impl_digest,
            )
            prepare_start = time.monotonic()
            prepared = log.prepare_transition(
                fragment_id=attempt.fragment_id,
                selected_proposal_ids=attempt.selected_proposal_ids,
                new_params=attempt.new_params,
                new_outer_state=attempt.new_outer_state,
                aggregate_digest=attempt.aggregate_digest,
                outer_optimizer_impl_digest=attempt.outer_optimizer_impl_digest,
                request_id=attempt.request_id,
            )
            prepare_done = time.monotonic()
            logger.event(
                "transaction_stage_completed",
                stage="successor_prepare",
                target_commit_seq=view.commit_seq + 1,
                seconds=prepare_done - prepare_start,
            )
            cas_start = prepare_done
            try:
                result = log.commit_prepared(prepared)
            except (CommitConflict, InjectedTimeout) as exc:
                logger.event("head_conflict_replay", error=repr(exc), parent_commit_id=view.commit_id)
                view = build_runtime_view(log, force_full=True)
                fragments, states = _load_committed_tensors(log, view, device=device)
                continue
            cas_done = time.monotonic()
            logger.event(
                "head_cas_completed",
                commit_seq=result.commit_seq,
                commit_id=result.commit_id,
                seconds=cas_done - cas_start,
            )
            prior_view = view
            replay_start = time.monotonic()
            view = build_runtime_view(log)
            replay_done = time.monotonic()
            logger.event(
                "post_cas_replay_completed",
                commit_seq=view.commit_seq,
                commit_id=view.commit_id,
                seconds=replay_done - replay_start,
            )
            if view.commit_id != result.commit_id or view.commit_seq != prior_view.commit_seq + 1:
                raise RuntimeError("committed result and replay-derived RuntimeView differ")
            fragments[fragment_id] = new_fragment
            states[fragment_id] = new_state
            publish_start = time.monotonic()
            publish_materialized_view(
                config=config,
                paths=paths,
                view=view,
                param_index=param_index,
                fragment_index=fragment_index,
                fragment_thetas=fragments,
                outer_states=states,
            )
            publish_done = time.monotonic()
            logger.event(
                "transaction_stage_completed",
                stage="materialized_export",
                target_commit_seq=view.commit_seq,
                seconds=publish_done - publish_start,
            )
            total_tokens = sum(entry.manifest.target_tokens_since_base for entry in selected)
            append_csv_row(
                paths.metrics / "syncer_metrics.csv",
                {
                    "timestamp": time.time(),
                    "version": view.commit_seq,
                    "global_merge_event": view.optimizer_transition_count,
                    "optimizer_transition_count": view.optimizer_transition_count,
                    "fragment_id": fragment_id,
                    "fragment_version": view.fragments[fragment_id].version,
                    "selected_count": len(selected),
                    "total_update_tokens": total_tokens,
                    "catalog_seconds": catalog_done - catalog_start,
                    "read_seconds": proposal_observation_done - catalog_done,
                    "fragment_read_seconds": proposal_observation_done - catalog_done,
                    "aggregation_seconds": aggregation_done - proposal_observation_done,
                    "fragment_aggregation_seconds": aggregation_done
                    - proposal_observation_done,
                    "outer_step_seconds": outer_done - aggregation_done,
                    "successor_prepare_seconds": prepare_done - prepare_start,
                    "head_cas_seconds": cas_done - cas_start,
                    "post_cas_replay_seconds": replay_done - replay_start,
                    "publish_seconds": publish_done - publish_start,
                    "materialize_full_seconds": publish_done - publish_start,
                    "fragment_staleness_min": min(
                        view.fragments[fragment_id].version - 1 - entry.manifest.base_fragment_version
                        for entry in selected
                    ),
                    "fragment_staleness_mean": sum(
                        view.fragments[fragment_id].version - 1 - entry.manifest.base_fragment_version
                        for entry in selected
                    )
                    / len(selected),
                    "fragment_staleness_max": max(
                        view.fragments[fragment_id].version - 1 - entry.manifest.base_fragment_version
                        for entry in selected
                    ),
                    "stale_updates_dropped": 0,
                    "global_interval_seconds": time.time() - last_global,
                },
                SYNCER_METRIC_FIELDS,
            )
            logger.event(
                "transition_committed",
                commit_seq=view.commit_seq,
                commit_id=view.commit_id,
                fragment_id=fragment_id,
                selected_proposal_ids=[entry.proposal_id for entry in selected],
                view_digest=view.view_digest,
            )
            if wandb_run is not None:
                wandb_run.log(
                    {
                        "syncer/version": view.commit_seq,
                        "syncer/global_merge_event": view.optimizer_transition_count,
                        "syncer/optimizer_transition_count": view.optimizer_transition_count,
                        "syncer/fragment_id": fragment_id,
                        "syncer/selected_count": len(selected),
                        "syncer/total_update_tokens": total_tokens,
                        "syncer/total_seen_tokens": view.total_seen_tokens,
                    },
                    step=view.commit_seq,
                )
            last_progress = time.time()
            last_global = last_progress
    except Exception:
        stop_reason = "error"
        logger.exception("error", commit_seq=view.commit_seq)
        raise
    finally:
        try:
            if view.authoritative_stop is None:
                stop_request_id = "stop-" + canonical_digest(
                    {
                        "owner_id": owner_id,
                        "owner_session_id": owner_session_id,
                        "fencing_epoch": view.fencing_epoch,
                        "parent_commit_id": view.commit_id,
                        "reason": stop_reason,
                    }
                )
                stop_start = time.monotonic()
                try:
                    log.commit_stop(reason=stop_reason, request_id=stop_request_id)
                    view = build_runtime_view(log)
                    logger.event(
                        "coordination_stage_completed",
                        stage="authoritative_stop",
                        commit_seq=view.commit_seq,
                        optimizer_transition_count=view.optimizer_transition_count,
                        seconds=time.monotonic() - stop_start,
                    )
                except CommitConflict as exc:
                    logger.event(
                        "stale_owner_stop_rejected",
                        error=repr(exc),
                        owner_id=owner_id,
                        owner_session_id=owner_session_id,
                    )
                    view = build_runtime_view(log, force_full=True)
            if view.authoritative_stop is not None:
                stop_reason = view.authoritative_stop.reason
                publish_materialized_view(
                    config=config,
                    paths=paths,
                    view=view,
                    param_index=param_index,
                    fragment_index=fragment_index,
                    fragment_thetas=fragments,
                    outer_states=states,
                )
                _publish_stop(paths, config=config, view=view, reason=stop_reason)
                logger.event(
                    "stop_published",
                    reason=stop_reason,
                    commit_seq=view.commit_seq,
                    commit_id=view.commit_id,
                )
                _cleanup_success(
                    paths=paths,
                    config=config,
                    logger=logger,
                    stop_reason=stop_reason,
                )
            else:
                logger.event(
                    "stop_not_published_without_authority",
                    reason=stop_reason,
                    commit_seq=view.commit_seq,
                )
            if wandb_run is not None:
                wandb_run.summary["stop_reason"] = stop_reason
                wandb_run.summary["final_version"] = view.commit_seq
                wandb_run.summary["final_optimizer_transition_count"] = (
                    view.optimizer_transition_count
                )
                wandb_run.summary["total_seen_tokens"] = view.total_seen_tokens
            logger.event("process_exit", reason=stop_reason, commit_seq=view.commit_seq)
        finally:
            if wandb_run is not None:
                wandb_run.finish(exit_code=1 if stop_reason == "error" else 0)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config = resolve_config(
        args.config,
        run_id=args.run_id,
        shared_root=args.shared_root,
        num_learners=args.num_learners,
    )
    run_syncer(
        config,
        owner_id=args.owner_id,
        owner_session_id=args.owner_session_id,
        standby=args.standby,
    )


if __name__ == "__main__":
    main()
