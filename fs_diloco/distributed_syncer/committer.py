"""Floating Committer: plan, dispatch prepare, validate, and CAS one global head."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import atexit
from pathlib import Path
import time
from typing import Callable, TypeVar

from fs_diloco.atomic_io import atomic_write_json
from fs_diloco.atomic_io import safe_read_json
from fs_diloco.config import Config
from fs_diloco.coordination import CoordinationConflict
from fs_diloco.distributed_syncer.bootstrap import distributed_run_spec_factory
from fs_diloco.log.codec import verified_get
from fs_diloco.log.codec import canonical_object
from fs_diloco.log.errors import CommitConflict
from fs_diloco.log.production_codec import (
    decode_production_outer_state,
    decode_production_params,
    production_optimizer_digest,
)
from fs_diloco.log.run import (
    DISTRIBUTED_COORDINATION_PROTOCOLS,
    ERROR_RESUME_COORDINATION_PROTOCOL,
)
from fs_diloco.log.gc import create_gc_mark
from fs_diloco.logging_utils import JsonlLogger
from fs_diloco.paths import RunPaths, prepare_run_dirs
from fs_diloco.proposal_catalog import ProposalCatalog
from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.protocol.schemas import ObjectRef
from fs_diloco.protocol.work_order_v1 import FragmentWorkOrderV1
from fs_diloco.protocol.work_order_v2 import RedundantFragmentWorkOrderV2
from fs_diloco.runtime_view import build_runtime_view
from fs_diloco.storage import InjectedTimeout, PosixStorageBackend
from fs_diloco.syncer import (
    PlanningCandidate,
    _acquire_and_activate_owner,
    _load_committed_tensors,
    _publish_stop,
    _renew_owner_lease,
    build_fragment_plan,
    collect_candidates,
    finite_local_training_complete,
    initialize_generation,
    publish_materialized_view,
    resume_generation,
)
from fs_diloco.telemetry import StageRecorder

from .executor import ExecutorBudget
from .duplicate_validation import (
    PreparedResultObservation,
    decide_duplicate_results,
)
from .hedge_policy import RedundancyPolicyV1
from .input_bundle import ExecutorInputBundleV1, publish_input_bundle
from .layout import DistributedLayout
from .membership import MembershipRevisionV1
from .ownership import derive_ownership
from .prepared_store import load_prepared_attempt
from .reconfiguration import ReconfigurationRequestV1
from .work_order_store import publish_work_order


_T = TypeVar("_T")


def _payload_ref(entry) -> ObjectRef:
    return ObjectRef(
        key=entry.manifest.payload_key,
        sha256=entry.manifest.payload_sha256,
        size=entry.manifest.payload_size,
    )


def _committed_membership_candidates(selected, membership: MembershipRevisionV1):
    active_learner_ids = {item.learner_id for item in membership.members}
    return tuple(
        entry for entry in selected if entry.manifest.learner_id in active_learner_ids
    )


def _renew_for_authoritative_stage(
    *, lease_manager, loaded_lease, config, logger, stage: str
):
    if stage not in {
        "post_activation",
        "membership_transition",
        "work_dispatch",
        "lifecycle_snapshot",
        "lifecycle_snapshot_committed",
        "lifecycle_accelerated_replay_completed",
        "lifecycle_strict_replay_completed",
        "lifecycle_reachability_completed",
        "lifecycle_inventory_completed",
        "lifecycle_substage_heartbeat",
        "optimizer_head_cas",
        "stop_head_cas",
    }:
        raise ValueError("unknown authoritative lease-renewal stage")
    renewed = _renew_owner_lease(
        lease_manager=lease_manager,
        loaded_lease=loaded_lease,
        config=config,
        logger=logger,
    )
    logger.event("lease_stage_guard", stage=stage)
    return renewed


def _run_lifecycle_substage(
    operation: Callable[[], _T],
    *,
    substage: str,
    lease_manager,
    loaded_lease,
    config,
    logger,
) -> tuple[_T, object]:
    """Run storage work while the main thread keeps the fenced lease alive.

    Lease mutation remains serialized on the committer thread.  The worker has
    no lease capability and performs only the supplied log/read operation.
    """

    interval = max(0.01, float(config.coordination.renew_interval_seconds))
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="lifecycle") as pool:
        future = pool.submit(operation)
        while True:
            try:
                return future.result(timeout=interval), loaded_lease
            except FutureTimeout:
                loaded_lease = _renew_for_authoritative_stage(
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                    stage="lifecycle_substage_heartbeat",
                )
                logger.event("lifecycle_substage_heartbeat", substage=substage)


def _wait_for_result(
    backend,
    layout: DistributedLayout,
    order: FragmentWorkOrderV1 | RedundantFragmentWorkOrderV2,
    *,
    active_path: Path,
    allowed_executor_ids: tuple[str, ...],
    timeout_seconds: float,
):
    deadline = time.monotonic() + timeout_seconds
    prefix = f"{layout.prepared_prefix}markers/{order.work_order_id}/"
    while time.monotonic() < deadline:
        markers = backend.list_prefix(prefix)
        loaded = []
        for key in markers:
            result, envelope = load_prepared_attempt(backend, key)
            if (
                result.work_order_id == order.work_order_id
                and result.parent_commit_id == order.parent_commit_id
                and envelope.membership_revision == order.membership_revision
                and envelope.executor_id in allowed_executor_ids
            ):
                loaded.append((result, envelope))
        required_attempts = 1
        if isinstance(order, RedundantFragmentWorkOrderV2):
            dispatch = safe_read_json(active_path)
            if not isinstance(dispatch, dict) or dispatch.get("work_order_id") != order.work_order_id:
                raise RuntimeError("active dispatch disappeared or changed while awaiting result")
            failed = dispatch.get("failed_member_ids", [])
            if (
                not isinstance(failed, list)
                or any(not isinstance(value, str) for value in failed)
                or not set(failed).issubset(order.owner_member_ids)
            ):
                raise ValueError("derived dispatch has invalid failed-member evidence")
            surviving = tuple(
                member_id for member_id in order.owner_member_ids if member_id not in failed
            )
            if not surviving:
                raise RuntimeError("no redundant executor remains eligible")
            mode = order.redundancy_policy.mode
            backup_activated = dispatch.get("backup_activated", False)
            if type(backup_activated) is not bool:
                raise ValueError("derived dispatch backup activation must be boolean")
            published_at = dispatch.get("published_at")
            if not isinstance(published_at, (int, float)) or isinstance(published_at, bool):
                raise ValueError("derived dispatch has invalid publication time")
            elapsed_ms = max(0, int((time.time() - float(published_at)) * 1000))
            backup_is_eligible = (
                order.backup_member_id in surviving
                and (
                    mode == "active_active"
                    or backup_activated
                    or (
                        mode == "hedged"
                        and order.redundancy_policy.hedge_delay_ms is not None
                        and elapsed_ms >= order.redundancy_policy.hedge_delay_ms
                    )
                )
            )
            primary_is_eligible = order.primary_member_id in surviving
            required_attempts = int(primary_is_eligible) + int(backup_is_eligible)
            if required_attempts == 0:
                raise RuntimeError("failure evidence requires backup activation before progress")
        if len(loaded) >= required_attempts:
            decision = decide_duplicate_results(
                order.work_order_id,
                tuple(
                    PreparedResultObservation(
                        work_order_id=result.work_order_id,
                        prepared_result_id=result.prepared_result_id,
                        attempt_envelope_id=envelope.attempt_envelope_id,
                        executor_id=envelope.executor_id,
                    )
                    for result, envelope in loaded
                ),
                required_attempts=required_attempts,
            )
            result = next(
                result
                for result, _envelope in loaded
                if result.prepared_result_id == decision.prepared_result_id
            )
            envelopes = tuple(
                sorted(
                    (envelope for _result, envelope in loaded),
                    key=lambda item: item.attempt_envelope_id,
                )
            )
            return result, envelopes, decision
        time.sleep(0.1)
    raise TimeoutError(f"timed out waiting for prepared result {order.work_order_id}")


def _validate_result(
    backend,
    *,
    order: FragmentWorkOrderV1 | RedundantFragmentWorkOrderV2,
    result,
    expected_aggregate_digest: str,
) -> tuple[bytes, bytes]:
    if (
        result.aggregate_digest != expected_aggregate_digest
        or result.numeric_implementation_digest != order.execution_backend_digest
        or result.validated_input_digests
        != tuple(sorted(item.payload_sha256 for item in order.proposals))
    ):
        raise ValueError("prepared result semantic identity differs from FWO")
    params = verified_get(backend, result.params_ref, commit_seq=0)
    outer = verified_get(backend, result.outer_state_ref, commit_seq=0)
    decode_production_params(params)
    decode_production_outer_state(outer)
    return params, outer


def _finalize_committer_stop(
    *,
    log,
    view,
    paths: RunPaths,
    config: Config,
    reason: str,
    member_id: str,
    owner_session_id: str,
    logger,
    lease_manager=None,
    loaded_lease=None,
):
    if view.authoritative_stop is None:
        request_id = "distributed-stop-" + canonical_digest(
            {
                "parent_commit_id": view.commit_id,
                "reason": reason,
                "owner_id": member_id,
                "owner_session_id": owner_session_id,
            }
        )
        try:
            if lease_manager is None or loaded_lease is None:
                log.commit_stop(reason=reason, request_id=request_id)
                view = build_runtime_view(log)
            else:
                prepared, loaded_lease = _run_lifecycle_substage(
                    lambda: log.prepare_control_transition(
                        control_kind="stop",
                        token=loaded_lease.record.owner_token,
                        request_id=request_id,
                        stop_reason=reason,
                    ),
                    substage="stop_prepare",
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                )
                loaded_lease = _renew_for_authoritative_stage(
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                    stage="stop_head_cas",
                )
                result = log.commit_prepared(prepared)
                view, loaded_lease = _run_lifecycle_substage(
                    lambda: build_runtime_view(log),
                    substage="stop_post_cas_replay",
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                )
                if view.commit_id != result.commit_id or view.authoritative_stop is None:
                    raise RuntimeError("guarded committer stop and replay-derived view differ")
        except CommitConflict as exc:
            logger.event(
                "stale_owner_stop_rejected",
                error=repr(exc),
                owner_id=member_id,
                owner_session_id=owner_session_id,
            )
            view = build_runtime_view(log, force_full=True)
    if view.authoritative_stop is None:
        logger.event(
            "stop_not_published_without_authority",
            reason=reason,
            commit_seq=view.commit_seq,
        )
        return view
    spec = getattr(log, "spec", None)
    if (
        spec is not None
        and spec.coordination_protocol == ERROR_RESUME_COORDINATION_PROTOCOL
        and view.authoritative_stop.reason == "error"
    ):
        recoverable_path = paths.control / "recoverable_error.json"
        atomic_write_json(
            recoverable_path,
            {
                "run_id": view.run_id,
                "run_generation": view.run_generation,
                "commit_id": view.commit_id,
                "commit_seq": view.commit_seq,
                "fencing_epoch": view.fencing_epoch,
                "reason": "error",
                "request_id": view.authoritative_stop.request_id,
                "request_digest": view.authoritative_stop.request_digest,
                "recoverable": True,
            },
        )
        logger.event(
            "recoverable_error_published_without_terminal_stop_sidecar",
            commit_seq=view.commit_seq,
            commit_id=view.commit_id,
            path=str(recoverable_path),
        )
        return view
    _publish_stop(
        paths,
        config=config,
        view=view,
        reason=view.authoritative_stop.reason,
    )
    logger.event(
        "stop_published",
        reason=view.authoritative_stop.reason,
        commit_seq=view.commit_seq,
        commit_id=view.commit_id,
    )
    return view


def _finalize_committer_without_masking(*, primary_error: bool, logger, **kwargs):
    try:
        return _finalize_committer_stop(logger=logger, **kwargs)
    except Exception as exc:
        try:
            logger.event(
                "committer_stop_finalization_failed",
                error=repr(exc),
                original_error_active=primary_error,
                reason=kwargs["reason"],
            )
        except Exception:
            if not primary_error:
                raise
        if not primary_error:
            raise
        return kwargs["view"]


def run_committer(
    config: Config,
    *,
    membership: MembershipRevisionV1,
    budget: ExecutorBudget,
    member_id: str,
    owner_session_id: str,
    standby: bool = False,
    replication_factor: int = 1,
    redundancy_policy: RedundancyPolicyV1 | None = None,
    lifecycle_cadence: int = 0,
    error_resume: bool = False,
    inject_error_after_transitions: int | None = None,
) -> None:
    if not membership.member(member_id).committer_eligible:
        raise ValueError("floating committer is not a committed candidate")
    if type(replication_factor) is not int or replication_factor not in {1, 2}:
        raise ValueError("replication factor must be one or two")
    paths = RunPaths(Path(config.run.shared_root or "."))
    prepare_run_dirs(paths, config.sync.num_learners)
    distributed_root = paths.shared_root / "distributed"
    distributed_root.mkdir(parents=True, exist_ok=True)
    active_path = distributed_root / "active_work_order.json"
    reconfigure_path = distributed_root / "reconfigure_membership.json"
    logger = JsonlLogger(paths.logs / "distributed_committer.jsonl", "floating_committer")
    stage_recorder = StageRecorder(
        paths.logs / f"performance_committer_{member_id}.jsonl",
        run_id=config.run.run_id or "",
        run_generation=config.init.run_generation,
        role="committer",
        role_session_id=owner_session_id,
        health_path=paths.logs / f"performance_committer_{member_id}.health.json",
    )
    atexit.register(stage_recorder.close)
    backend = PosixStorageBackend(paths.authority)
    if config.init.resume or standby:
        deadline = time.monotonic() + config.liveness.no_progress_timeout_seconds
        while True:
            try:
                log, view, param_index, fragment_index, fragments, states = resume_generation(
                    config, paths, backend, device="cpu"
                )
                break
            except Exception:
                if not standby or time.monotonic() >= deadline:
                    raise
                time.sleep(config.coordination.standby_poll_seconds)
    else:
        log, view, param_index, fragment_index, fragments, states = initialize_generation(
            config,
            paths,
            backend,
            device="cpu",
            run_spec_factory=distributed_run_spec_factory(
                membership=membership,
                budget=budget,
                replication_factor=replication_factor,
                error_resume=error_resume,
            ),
        )
    if log.spec.coordination_protocol not in DISTRIBUTED_COORDINATION_PROTOCOLS:
        raise ValueError("floating committer opened a non-distributed generation")
    if error_resume != (
        log.spec.coordination_protocol == ERROR_RESUME_COORDINATION_PROTOCOL
    ):
        raise ValueError("error-resume launch mode differs from immutable RunSpec")
    if log.spec.ownership_replication_factor != replication_factor:
        raise ValueError("committer replication factor differs from immutable RunSpec")
    if replication_factor == 2 and redundancy_policy is None:
        raise ValueError("factor-two committer requires a redundancy policy")
    if replication_factor == 1 and redundancy_policy is not None:
        raise ValueError("factor-one committer cannot carry a redundancy policy")
    if type(lifecycle_cadence) is not int or lifecycle_cadence < 0:
        raise ValueError("lifecycle cadence must be a non-negative integer")
    if inject_error_after_transitions is not None and (
        type(inject_error_after_transitions) is not int
        or inject_error_after_transitions < 1
    ):
        raise ValueError("injected error transition count must be positive")
    # An authoritative stop is terminal.  In particular, a standby must not
    # acquire a fresh fencing epoch after observing the stopped head.
    resuming_error_stop = (
        error_resume
        and view.authoritative_stop is not None
        and view.authoritative_stop.reason == "error"
    )
    if view.authoritative_stop is not None and not (
        error_resume and view.authoritative_stop.reason == "error"
    ):
        _publish_stop(paths, config=config, view=view, reason=view.authoritative_stop.reason)
        stage_recorder.close()
        return
    layout = DistributedLayout(log.layout)
    lease_manager, loaded_lease, view = _acquire_and_activate_owner(
        log=log,
        config=config,
        owner_id=member_id,
        owner_session_id=owner_session_id,
        logger=logger,
        standby=standby,
    )
    if loaded_lease is None:
        return
    if resuming_error_stop:
        if view.authoritative_stop is not None:
            raise RuntimeError("error resume returned a stopped authoritative view")
        (paths.control / "recoverable_error.json").unlink(missing_ok=True)
        paths.stop_json.unlink(missing_ok=True)
        logger.event(
            "derived_error_stop_cleared_after_resume",
            commit_seq=view.commit_seq,
            fencing_epoch=view.fencing_epoch,
        )
    if view.membership is None:
        raise RuntimeError("distributed head has no membership projection")
    membership = MembershipRevisionV1.from_dict(
        canonical_object(verified_get(backend, view.membership.membership_ref, commit_seq=view.commit_seq))
    )
    fragments, states = _load_committed_tensors(log, view, device="cpu")
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
        validation_device="cpu",
    )
    optimizer_impl = production_optimizer_digest(log.spec.optimizer_config.identity())
    loaded_lease = _renew_for_authoritative_stage(
        lease_manager=lease_manager,
        loaded_lease=loaded_lease,
        config=config,
        logger=logger,
        stage="post_activation",
    )
    last_progress = time.monotonic()
    next_renew = time.monotonic() + config.coordination.renew_interval_seconds
    stop_reason = "completed"
    primary_error = False
    lease_authority_lost = False
    try:
        while True:
            if config.sync.stop_after_outer_steps is not None and (
                view.optimizer_transition_count >= config.sync.stop_after_outer_steps
            ):
                stop_reason = "stop_after_outer_steps"
                break
            if time.monotonic() >= next_renew:
                loaded_lease = _renew_owner_lease(
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                )
                next_renew = time.monotonic() + config.coordination.renew_interval_seconds
            request = safe_read_json(reconfigure_path)
            if request is not None:
                if not isinstance(request, dict):
                    raise ValueError("reconfiguration request must be a JSON object")
                reconfiguration = ReconfigurationRequestV1.from_dict(request)
                if (
                    reconfiguration.expected_membership_revision != membership.revision
                    or reconfiguration.expected_membership_digest
                    != membership.membership_digest
                    or reconfiguration.evidence.run_id != view.run_id
                    or reconfiguration.evidence.run_generation != view.run_generation
                ):
                    raise ValueError("reconfiguration request differs from committed membership")
                remove_member_id = reconfiguration.remove_member_id
                remaining = tuple(
                    item for item in membership.members if item.member_id != remove_member_id
                )
                if (
                    len(remaining) == len(membership.members)
                    or len(remaining) < replication_factor
                ):
                    raise ValueError("invalid membership removal request")
                successor = MembershipRevisionV1.create(
                    membership.revision + 1, remaining
                )
                membership_request_id = "membership-" + canonical_digest(
                    {
                        "parent_commit_id": view.commit_id,
                        "membership_digest": successor.membership_digest,
                        "reconfiguration_request_id": reconfiguration.request_id,
                        "failure_evidence_id": reconfiguration.evidence.evidence_id,
                    }
                )
                loaded_lease = _renew_for_authoritative_stage(
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                    stage="membership_transition",
                )
                next_renew = (
                    time.monotonic() + config.coordination.renew_interval_seconds
                )
                log.commit_membership(
                    membership=successor, request_id=membership_request_id
                )
                view = build_runtime_view(log)
                membership = successor
                reconfigure_path.unlink(missing_ok=True)
                logger.event(
                    "membership_reconfigured",
                    revision=membership.revision,
                    removed_member_id=remove_member_id,
                    reconfiguration_request_id=reconfiguration.request_id,
                    failure_evidence_id=reconfiguration.evidence.evidence_id,
                    membership_digest=membership.membership_digest,
                    commit_seq=view.commit_seq,
                )
            fragment_id = 0 if len(view.fragments) == 1 else view.scheduler_cursor
            catalog_started_ns = time.monotonic_ns()
            selected = collect_candidates(
                catalog=catalog,
                log=log,
                view=view,
                paths=paths,
                config=config,
                fragment_id=fragment_id,
            )
            selected = _committed_membership_candidates(selected, membership)
            catalog_finished_ns = time.monotonic_ns()
            terminal_drain = finite_local_training_complete(paths, config)
            if len(selected) < config.sync.quorum_min and not (terminal_drain and selected):
                if time.monotonic() - last_progress > config.liveness.no_progress_timeout_seconds:
                    stop_reason = "no_progress_timeout"
                    break
                time.sleep(config.sync.scan_interval_seconds)
                continue
            catalog_counters = getattr(catalog, "last_scan_counters", {})
            for entry in selected:
                catalog.publish_entry(log, entry)
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
            if view.membership is None:
                raise RuntimeError("distributed RuntimeView lost membership")
            ownership = derive_ownership(
                membership,
                fragment_ids=tuple(sorted(view.fragments)),
                replication_factor=view.membership.replication_factor,
            )
            if ownership.ownership_digest != view.membership.ownership_digest:
                raise RuntimeError("local ownership differs from committed projection")
            owner_member_ids = ownership.owner_ids(fragment_id)
            base_order = FragmentWorkOrderV1.with_computed_id(
                {
                    "schema": FragmentWorkOrderV1.SCHEMA,
                    "run_id": view.run_id,
                    "run_generation": view.run_generation,
                    "parent_commit_id": view.commit_id,
                    "parent_frontier_digest": view.frontier_sha256,
                    "fragment_id": fragment_id,
                    "committer_fencing_epoch": view.fencing_epoch,
                    "membership_revision": view.membership.revision,
                    "ownership_digest": view.membership.ownership_digest,
                    "proposals": [
                        {
                            "proposal_id": entry.proposal_id,
                            "payload_sha256": entry.manifest.payload_sha256,
                            "target_tokens": entry.manifest.target_tokens_since_base,
                            "base_fragment_version": entry.manifest.base_fragment_version,
                            "weight_hex": plan.weights_hex[index],
                        }
                        for index, entry in enumerate(selected)
                    ],
                    "aggregation_policy_digest": canonical_digest(
                        {"policy": "ordered-weighted-left-fold-v1"}
                    ),
                    "outer_optimizer_impl_digest": optimizer_impl,
                    "execution_backend_digest": log.spec.execution_backend_digest,
                    "parameter_index_digest": log.spec.parameter_index_digest,
                    "fragment_layout_digest": log.spec.fragment_layout_digest,
                }
            )
            order: FragmentWorkOrderV1 | RedundantFragmentWorkOrderV2
            if replication_factor == 2:
                if redundancy_policy is None:
                    raise AssertionError("factor-two policy disappeared")
                order = RedundantFragmentWorkOrderV2.with_computed_id(
                    {
                        "schema": RedundantFragmentWorkOrderV2.SCHEMA,
                        "base_work_order": base_order.to_dict(),
                        "owner_member_ids": list(owner_member_ids),
                        "redundancy_policy": redundancy_policy.to_dict(),
                    }
                )
            else:
                order = base_order
            stage_recorder.record(
                "catalog_discovery",
                start_ns=catalog_started_ns,
                end_ns=catalog_finished_ns,
                work_order_id=order.work_order_id,
                commit_seq=view.commit_seq,
                head_commit_id=view.commit_id,
                fencing_epoch=view.fencing_epoch,
                membership_revision=membership.revision,
                counters={
                    "selected_count": len(selected),
                    "observed_count": int(
                        catalog_counters.get("observed_count", len(selected))
                    ),
                    "metadata_reads": int(catalog_counters.get("metadata_reads", 0)),
                    "cheap_rejections": int(
                        catalog_counters.get("cheap_rejections", 0)
                    ),
                },
            )
            stage_recorder.record(
                "proposal_validation",
                start_ns=catalog_started_ns,
                end_ns=catalog_finished_ns,
                work_order_id=order.work_order_id,
                commit_seq=view.commit_seq,
                head_commit_id=view.commit_id,
                fencing_epoch=view.fencing_epoch,
                membership_revision=membership.revision,
                counters={
                    "payload_reads": int(
                        catalog_counters.get("payload_reads", len(selected))
                    ),
                    "sha_checks": int(
                        catalog_counters.get("sha_checks", len(selected))
                    ),
                    "finite_checks": int(
                        catalog_counters.get("finite_checks", len(selected))
                    ),
                    "validation_token_hits": int(
                        catalog_counters.get("validation_token_hits", 0)
                    ),
                },
                attributes={
                    "proposal_ids": [item.proposal_id for item in selected],
                },
            )
            bundle = ExecutorInputBundleV1.create(
                {
                    "schema": ExecutorInputBundleV1.SCHEMA,
                    "work_order_id": order.work_order_id,
                    "parent_commit_id": view.commit_id,
                    "params_ref": view.fragments[fragment_id].params_ref.to_dict(),
                    "outer_state_ref": view.fragments[fragment_id].outer_state_ref.to_dict(),
                    "proposals": [
                        {
                            "proposal_id": entry.proposal_id,
                            "payload_ref": _payload_ref(entry).to_dict(),
                            "tensor_key": entry.manifest.tensor_key,
                        }
                        for entry in selected
                    ],
                }
            )
            loaded_lease = _renew_for_authoritative_stage(
                lease_manager=lease_manager,
                loaded_lease=loaded_lease,
                config=config,
                logger=logger,
                stage="work_dispatch",
            )
            next_renew = time.monotonic() + config.coordination.renew_interval_seconds
            publication_started_ns = time.monotonic_ns()
            publish_work_order(backend, layout, order)
            publish_input_bundle(backend, layout, bundle)
            dispatch_started = time.monotonic()
            atomic_write_json(
                active_path,
                {
                    "work_order_id": order.work_order_id,
                    "owner_member_ids": list(owner_member_ids),
                    "membership_revision": order.membership_revision,
                    "ownership_digest": order.ownership_digest,
                    "published_at": time.time(),
                    "backup_activated": False,
                    "failed_member_ids": [],
                },
            )
            stage_recorder.record(
                "work_order_publication",
                start_ns=publication_started_ns,
                work_order_id=order.work_order_id,
                commit_seq=view.commit_seq,
                head_commit_id=view.commit_id,
                fencing_epoch=view.fencing_epoch,
                membership_revision=order.membership_revision,
                counters={
                    "proposal_count": len(order.proposals),
                    "owner_count": len(owner_member_ids),
                    "input_bytes": (
                        bundle.params_ref.size
                        + bundle.outer_state_ref.size
                        + sum(item.payload_ref.size for item in bundle.proposals)
                    ),
                },
                attributes={
                    "proposal_ids": [item.proposal_id for item in order.proposals],
                    "owner_member_ids": list(owner_member_ids),
                },
            )
            allowed_executor_ids = tuple(
                membership.member(owner_id).executor_id for owner_id in owner_member_ids
            )
            visibility_started_ns = time.monotonic_ns()
            (result, envelopes, duplicate_decision), loaded_lease = (
                _run_lifecycle_substage(
                    lambda current_order=order, executor_ids=allowed_executor_ids: _wait_for_result(
                        backend,
                        layout,
                        current_order,
                        active_path=active_path,
                        allowed_executor_ids=executor_ids,
                        timeout_seconds=config.liveness.no_progress_timeout_seconds,
                    ),
                    substage="executor_result_wait",
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                )
            )
            stage_recorder.record(
                "prepared_visibility",
                start_ns=visibility_started_ns,
                work_order_id=order.work_order_id,
                commit_seq=view.commit_seq,
                head_commit_id=view.commit_id,
                fencing_epoch=view.fencing_epoch,
                membership_revision=order.membership_revision,
                counters={"observed_attempt_count": len(envelopes)},
                attributes={
                    "prepared_result_id": result.prepared_result_id,
                    "attempt_envelope_ids": [
                        item.attempt_envelope_id for item in envelopes
                    ],
                },
            )
            next_renew = time.monotonic() + config.coordination.renew_interval_seconds
            validation_started_ns = time.monotonic_ns()
            (params_data, outer_data), loaded_lease = _run_lifecycle_substage(
                lambda current_order=order, current_result=result, aggregate_digest=plan.aggregate_digest: _validate_result(
                    backend,
                    order=current_order,
                    result=current_result,
                    expected_aggregate_digest=aggregate_digest,
                ),
                substage="winner_validation",
                lease_manager=lease_manager,
                loaded_lease=loaded_lease,
                config=config,
                logger=logger,
            )
            stage_recorder.record(
                "winner_validation",
                start_ns=validation_started_ns,
                work_order_id=order.work_order_id,
                commit_seq=view.commit_seq,
                head_commit_id=view.commit_id,
                fencing_epoch=view.fencing_epoch,
                membership_revision=order.membership_revision,
                counters={
                    "params_bytes": len(params_data),
                    "outer_state_bytes": len(outer_data),
                    "attempt_count": len(envelopes),
                },
                attributes={"prepared_result_id": result.prepared_result_id},
            )
            request_id = "distributed-optimizer-" + canonical_digest(
                {
                    "work_order_id": order.work_order_id,
                    "prepared_result_id": result.prepared_result_id,
                    "owner_id": member_id,
                    "owner_session_id": owner_session_id,
                    "fencing_epoch": view.fencing_epoch,
                }
            )
            try:
                successor_started_ns = time.monotonic_ns()
                prepare_kwargs = {
                    "fragment_id": fragment_id,
                    "selected_proposal_ids": plan.selected_proposal_ids,
                    "new_params": params_data,
                    "new_outer_state": outer_data,
                    "aggregate_digest": result.aggregate_digest,
                    "outer_optimizer_impl_digest": order.outer_optimizer_impl_digest,
                    "request_id": request_id,
                    "distributed_work_order_id": order.work_order_id,
                    "prepared_result_id": result.prepared_result_id,
                }
                prepared, loaded_lease = _run_lifecycle_substage(
                    lambda kwargs=prepare_kwargs: log.prepare_transition(**kwargs),
                    substage="successor_prepare",
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                )
                stage_recorder.record(
                    "successor_publication",
                    start_ns=successor_started_ns,
                    work_order_id=order.work_order_id,
                    commit_seq=view.commit_seq,
                    head_commit_id=view.commit_id,
                    fencing_epoch=view.fencing_epoch,
                    membership_revision=order.membership_revision,
                    counters={
                        "params_bytes": len(params_data),
                        "outer_state_bytes": len(outer_data),
                    },
                    attributes={"prepared_result_id": result.prepared_result_id},
                )
                loaded_lease = _renew_for_authoritative_stage(
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                    stage="optimizer_head_cas",
                )
                next_renew = (
                    time.monotonic() + config.coordination.renew_interval_seconds
                )
                cas_started_ns = time.monotonic_ns()
                log.commit_prepared(prepared)
                stage_recorder.record(
                    "head_cas",
                    start_ns=cas_started_ns,
                    work_order_id=order.work_order_id,
                    transition_id=prepared.commit.commit_id,
                    commit_seq=prepared.commit.commit_seq,
                    head_commit_id=view.commit_id,
                    fencing_epoch=view.fencing_epoch,
                    membership_revision=order.membership_revision,
                )
            except (CommitConflict, InjectedTimeout) as exc:
                logger.event(
                    "head_conflict_replay",
                    error=repr(exc),
                    parent_commit_id=view.commit_id,
                    work_order_id=order.work_order_id,
                )
                active_path.unlink(missing_ok=True)
                view = build_runtime_view(log, force_full=True)
                fragments, states = _load_committed_tensors(log, view, device="cpu")
                if view.authoritative_stop is not None:
                    stop_reason = view.authoritative_stop.reason
                    break
                if view.membership is None:
                    raise RuntimeError(
                        "distributed head lost membership after conflict"
                    ) from exc
                membership = MembershipRevisionV1.from_dict(
                    canonical_object(
                        verified_get(
                            backend,
                            view.membership.membership_ref,
                            commit_seq=view.commit_seq,
                        )
                    )
                )
                continue
            view, loaded_lease = _run_lifecycle_substage(
                lambda: build_runtime_view(log),
                substage="post_cas_replay",
                lease_manager=lease_manager,
                loaded_lease=loaded_lease,
                config=config,
                logger=logger,
            )
            next_renew = time.monotonic() + config.coordination.renew_interval_seconds
            fragments[fragment_id] = decode_production_params(params_data)
            states[fragment_id] = decode_production_outer_state(outer_data)
            if lifecycle_cadence and (
                view.optimizer_transition_count % lifecycle_cadence == 0
            ):
                lifecycle_started = time.monotonic()
                lifecycle_reads_started = backend.read_counters
                loaded_lease = _renew_for_authoritative_stage(
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                    stage="lifecycle_snapshot",
                )
                next_renew = (
                    time.monotonic() + config.coordination.renew_interval_seconds
                )
                snapshot_request_id = "snapshot-" + canonical_digest(
                    {
                        "parent_commit_id": view.commit_id,
                        "optimizer_transition_count": view.optimizer_transition_count,
                        "owner_id": member_id,
                        "owner_session_id": owner_session_id,
                    }
                )
                _snapshot_result, loaded_lease = _run_lifecycle_substage(
                    lambda request_id=snapshot_request_id: log.commit_snapshot(
                        request_id=request_id
                    ),
                    substage="snapshot_commit",
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                )
                loaded_lease = _renew_for_authoritative_stage(
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                    stage="lifecycle_snapshot_committed",
                )
                accelerated, loaded_lease = _run_lifecycle_substage(
                    log.replay_from_snapshot,
                    substage="accelerated_replay",
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                )
                loaded_lease = _renew_for_authoritative_stage(
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                    stage="lifecycle_accelerated_replay_completed",
                )
                strict, loaded_lease = _run_lifecycle_substage(
                    lambda: log.replay(force_full=True),
                    substage="strict_replay",
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                )
                loaded_lease = _renew_for_authoritative_stage(
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                    stage="lifecycle_strict_replay_completed",
                )
                if accelerated.replay != strict:
                    raise RuntimeError("snapshot+suffix replay differs from strict replay")
                (mark, reachability), loaded_lease = _run_lifecycle_substage(
                    lambda: create_gc_mark(log),
                    substage="reachability",
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                )
                loaded_lease = _renew_for_authoritative_stage(
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                    stage="lifecycle_reachability_completed",
                )
                view = build_runtime_view(log)
                inventory_reads_started = backend.read_counters
                inventory_bytes, loaded_lease = _run_lifecycle_substage(
                    lambda inventory=reachability.inventory: sum(
                        backend.head(key).size for key in inventory
                    ),
                    substage="inventory",
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                )
                inventory_reads_finished = backend.read_counters
                loaded_lease = _renew_for_authoritative_stage(
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                    config=config,
                    logger=logger,
                    stage="lifecycle_inventory_completed",
                )
                lifecycle_reads_finished = backend.read_counters
                next_renew = (
                    time.monotonic() + config.coordination.renew_interval_seconds
                )
                lifecycle_report = {
                    "schema": "duraloco-lifecycle-cycle-v1",
                    "snapshot_id": accelerated.snapshot_id,
                    "snapshot_mode": accelerated.mode,
                    "covered_commit_seq": accelerated.covered_commit_seq,
                    "suffix_length": accelerated.suffix_length,
                    "snapshot_storage_get_count": accelerated.storage_get_count,
                    "strict_state_digest": strict.committed_state_digest,
                    "mark_id": mark.mark_id,
                    "dry_run": True,
                    "head_commit_id": reachability.head_commit_id,
                    "head_commit_seq": reachability.head_commit_seq,
                    "reachable_count": len(reachability.reachable),
                    "candidate_count": len(reachability.candidates),
                    "protected_unknown_count": len(
                        reachability.protected_unknown
                    ),
                    "inventory_count": len(reachability.inventory),
                    "inventory_bytes": inventory_bytes,
                    "inventory_header_bytes_read": (
                        inventory_reads_finished["header_bytes"]
                        - inventory_reads_started["header_bytes"]
                    ),
                    "inventory_payload_bytes_read": (
                        inventory_reads_finished["payload_bytes"]
                        - inventory_reads_started["payload_bytes"]
                    ),
                    "lifecycle_header_bytes_read": (
                        lifecycle_reads_finished["header_bytes"]
                        - lifecycle_reads_started["header_bytes"]
                    ),
                    "lifecycle_payload_bytes_read": (
                        lifecycle_reads_finished["payload_bytes"]
                        - lifecycle_reads_started["payload_bytes"]
                    ),
                    "lifecycle_seconds": time.monotonic() - lifecycle_started,
                }
                report_path = (
                    distributed_root
                    / "lifecycle"
                    / f"cycle-{view.optimizer_transition_count:08d}.json"
                )
                atomic_write_json(report_path, lifecycle_report)
                logger.event("lifecycle_cycle_completed", **lifecycle_report)
            materialization_started_ns = time.monotonic_ns()
            publish_materialized_view(
                config=config,
                paths=paths,
                view=view,
                param_index=param_index,
                fragment_index=fragment_index,
                fragment_thetas=fragments,
                outer_states=states,
            )
            stage_recorder.record(
                "materialization",
                start_ns=materialization_started_ns,
                work_order_id=order.work_order_id,
                transition_id=view.commit_id,
                commit_seq=view.commit_seq,
                head_commit_id=view.commit_id,
                fencing_epoch=view.fencing_epoch,
                membership_revision=(view.membership.revision if view.membership else None),
                counters={"fragment_count": len(fragments)},
            )
            logger.event(
                "distributed_transition_committed",
                commit_seq=view.commit_seq,
                optimizer_transition_count=view.optimizer_transition_count,
                work_order_id=order.work_order_id,
                prepared_result_id=result.prepared_result_id,
                attempt_envelope_ids=list(duplicate_decision.attempt_envelope_ids),
                executor_ids=list(duplicate_decision.executor_ids),
                owner_member_ids=list(owner_member_ids),
                redundancy_mode=(
                    redundancy_policy.mode if redundancy_policy is not None else "factor_one"
                ),
                observed_attempt_count=len(envelopes),
                publish_to_commit_seconds=time.monotonic() - dispatch_started,
                prepared_parameter_bytes=result.params_ref.size,
                prepared_outer_state_bytes=result.outer_state_ref.size,
            )
            active_path.unlink(missing_ok=True)
            last_progress = time.monotonic()
            if (
                inject_error_after_transitions is not None
                and view.optimizer_transition_count
                == inject_error_after_transitions
            ):
                raise RuntimeError(
                    "injected P08 committer error after committed transition"
                )
            time.sleep(0.5)
    except CoordinationConflict:
        primary_error = True
        lease_authority_lost = True
        stop_reason = "lease_authority_lost"
        logger.exception("lease_authority_lost", commit_seq=view.commit_seq)
        raise
    except Exception:
        primary_error = True
        stop_reason = "error"
        logger.exception("error", commit_seq=view.commit_seq)
        raise
    finally:
        try:
            if lease_authority_lost:
                logger.event(
                    "stop_not_published_after_lease_authority_loss",
                    commit_seq=view.commit_seq,
                )
            else:
                view = _finalize_committer_without_masking(
                    primary_error=primary_error,
                    logger=logger,
                    log=log,
                    view=view,
                    paths=paths,
                    config=config,
                    reason=stop_reason,
                    member_id=member_id,
                    owner_session_id=owner_session_id,
                    lease_manager=lease_manager,
                    loaded_lease=loaded_lease,
                )
        finally:
            try:
                active_path.unlink(missing_ok=True)
            except Exception as exc:
                try:
                    logger.event(
                        "active_work_order_cleanup_failed",
                        error=repr(exc),
                        original_error_active=primary_error,
                    )
                except Exception:
                    if not primary_error:
                        raise
                if not primary_error:
                    raise
            stage_recorder.close()
