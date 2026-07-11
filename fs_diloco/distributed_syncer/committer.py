"""Floating Committer: plan, dispatch prepare, validate, and CAS one global head."""

from __future__ import annotations

import hashlib
from pathlib import Path
import time

from fs_diloco.atomic_io import atomic_write_json
from fs_diloco.atomic_io import safe_read_json
from fs_diloco.config import Config
from fs_diloco.distributed_syncer.bootstrap import distributed_run_spec_factory
from fs_diloco.log.codec import verified_get
from fs_diloco.log.codec import canonical_object
from fs_diloco.log.production_codec import (
    decode_production_outer_state,
    decode_production_params,
    production_optimizer_digest,
)
from fs_diloco.logging_utils import JsonlLogger
from fs_diloco.paths import RunPaths, prepare_run_dirs
from fs_diloco.proposal_catalog import ProposalCatalog
from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.protocol.schemas import ObjectRef
from fs_diloco.protocol.work_order_v1 import FragmentWorkOrderV1
from fs_diloco.runtime_view import build_runtime_view
from fs_diloco.storage import PosixStorageBackend
from fs_diloco.syncer import (
    PlanningCandidate,
    _acquire_and_activate_owner,
    _candidate_paths,
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

from .executor import ExecutorBudget
from .input_bundle import ExecutorInputBundleV1, publish_input_bundle
from .layout import DistributedLayout
from .membership import MembershipRevisionV1
from .ownership import derive_ownership
from .prepared_store import load_prepared_attempt
from .work_order_store import publish_work_order


def _payload_ref(entry) -> ObjectRef:
    return ObjectRef(
        key=entry.manifest.payload_key,
        sha256=entry.manifest.payload_sha256,
        size=entry.manifest.payload_size,
    )


def _wait_for_result(
    backend,
    layout: DistributedLayout,
    order: FragmentWorkOrderV1,
    *,
    timeout_seconds: float,
):
    deadline = time.monotonic() + timeout_seconds
    prefix = f"{layout.prepared_prefix}markers/{order.work_order_id}/"
    while time.monotonic() < deadline:
        markers = backend.list_prefix(prefix)
        for key in markers:
            result, envelope = load_prepared_attempt(backend, key)
            if (
                result.work_order_id == order.work_order_id
                and result.parent_commit_id == order.parent_commit_id
                and envelope.membership_revision == order.membership_revision
            ):
                return result, envelope
        time.sleep(0.1)
    raise TimeoutError(f"timed out waiting for prepared result {order.work_order_id}")


def _validate_result(
    backend,
    *,
    order: FragmentWorkOrderV1,
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


def run_committer(
    config: Config,
    *,
    membership: MembershipRevisionV1,
    budget: ExecutorBudget,
    member_id: str,
    owner_session_id: str,
    standby: bool = False,
) -> None:
    if not membership.member(member_id).committer_eligible:
        raise ValueError("floating committer is not a committed candidate")
    paths = RunPaths(Path(config.run.shared_root or "."))
    prepare_run_dirs(paths, config.sync.num_learners)
    distributed_root = paths.shared_root / "distributed"
    distributed_root.mkdir(parents=True, exist_ok=True)
    active_path = distributed_root / "active_work_order.json"
    reconfigure_path = distributed_root / "reconfigure_membership.json"
    logger = JsonlLogger(paths.logs / "distributed_committer.jsonl", "floating_committer")
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
                membership=membership, budget=budget
            ),
        )
    if log.spec.coordination_protocol != "distributed-head-fenced-v1":
        raise ValueError("floating committer opened a non-distributed generation")
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
    last_progress = time.monotonic()
    next_renew = time.monotonic() + config.coordination.renew_interval_seconds
    stop_reason = "completed"
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
            if isinstance(request, dict) and request.get("remove_member_id"):
                remove_member_id = str(request["remove_member_id"])
                remaining = tuple(
                    item for item in membership.members if item.member_id != remove_member_id
                )
                if len(remaining) == len(membership.members) or not remaining:
                    raise ValueError("invalid membership removal request")
                successor = MembershipRevisionV1.create(
                    membership.revision + 1, remaining
                )
                membership_request_id = "membership-" + canonical_digest(
                    {
                        "parent_commit_id": view.commit_id,
                        "membership_digest": successor.membership_digest,
                        "evidence_digest": str(request.get("evidence_digest") or ""),
                    }
                )
                log.commit_membership(
                    membership=successor, request_id=membership_request_id
                )
                view = build_runtime_view(log)
                membership = successor
                fragments, states = _load_committed_tensors(log, view, device="cpu")
                reconfigure_path.unlink(missing_ok=True)
                logger.event(
                    "membership_reconfigured",
                    revision=membership.revision,
                    removed_member_id=remove_member_id,
                    membership_digest=membership.membership_digest,
                    commit_seq=view.commit_seq,
                )
            fragment_id = 0 if len(view.fragments) == 1 else view.scheduler_cursor
            selected = collect_candidates(
                catalog=catalog,
                log=log,
                view=view,
                paths=paths,
                config=config,
                fragment_id=fragment_id,
            )
            terminal_drain = finite_local_training_complete(paths, config)
            if len(selected) < config.sync.quorum_min and not (terminal_drain and selected):
                if time.monotonic() - last_progress > config.liveness.no_progress_timeout_seconds:
                    stop_reason = "no_progress_timeout"
                    break
                time.sleep(config.sync.scan_interval_seconds)
                continue
            for entry in selected:
                log.publish_validated_proposal(entry.manifest, entry.payload)
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
            owner_member_id = ownership.owner_ids(fragment_id)[0]
            order = FragmentWorkOrderV1.with_computed_id(
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
            publish_work_order(backend, layout, order)
            publish_input_bundle(backend, layout, bundle)
            dispatch_started = time.monotonic()
            atomic_write_json(
                active_path,
                {
                    "work_order_id": order.work_order_id,
                    "owner_member_id": owner_member_id,
                    "membership_revision": order.membership_revision,
                    "ownership_digest": order.ownership_digest,
                    "published_at": time.time(),
                },
            )
            result, envelope = _wait_for_result(
                backend,
                layout,
                order,
                timeout_seconds=config.liveness.no_progress_timeout_seconds,
            )
            params_data, outer_data = _validate_result(
                backend,
                order=order,
                result=result,
                expected_aggregate_digest=plan.aggregate_digest,
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
            prepared = log.prepare_transition(
                fragment_id=fragment_id,
                selected_proposal_ids=plan.selected_proposal_ids,
                new_params=params_data,
                new_outer_state=outer_data,
                aggregate_digest=result.aggregate_digest,
                outer_optimizer_impl_digest=order.outer_optimizer_impl_digest,
                request_id=request_id,
            )
            log.commit_prepared(prepared)
            view = build_runtime_view(log)
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
            logger.event(
                "distributed_transition_committed",
                commit_seq=view.commit_seq,
                optimizer_transition_count=view.optimizer_transition_count,
                work_order_id=order.work_order_id,
                prepared_result_id=result.prepared_result_id,
                attempt_envelope_id=envelope.attempt_envelope_id,
                executor_member_id=owner_member_id,
                publish_to_commit_seconds=time.monotonic() - dispatch_started,
                prepared_parameter_bytes=result.params_ref.size,
                prepared_outer_state_bytes=result.outer_state_ref.size,
            )
            active_path.unlink(missing_ok=True)
            last_progress = time.monotonic()
            time.sleep(0.5)
    finally:
        if view.authoritative_stop is None:
            request_id = "distributed-stop-" + canonical_digest(
                {
                    "parent_commit_id": view.commit_id,
                    "reason": stop_reason,
                    "owner_id": member_id,
                    "owner_session_id": owner_session_id,
                }
            )
            log.commit_stop(reason=stop_reason, request_id=request_id)
            view = build_runtime_view(log)
        _publish_stop(paths, config=config, view=view, reason=view.authoritative_stop.reason)
        active_path.unlink(missing_ok=True)
