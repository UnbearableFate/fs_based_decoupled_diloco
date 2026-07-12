"""Prepare-only learner-hosted fragment executor kernel and resource identity."""

from __future__ import annotations

from dataclasses import dataclass
import resource

import torch

from fs_diloco.log.production_codec import encode_production_outer_state, encode_production_params
from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.protocol.prepared_transition_v1 import (
    PreparedAttemptEnvelopeV1,
    PreparedFragmentResultV1,
)
from fs_diloco.protocol.work_order_v1 import FragmentWorkOrderV1
from fs_diloco.syncer_core.aggregation import apply_outer_transition, reduce_fragment
from fs_diloco.syncer_core.types import FragmentPlan

from .layout import DistributedLayout
from .prepared_store import content_ref, publish_prepared_attempt


@dataclass(frozen=True)
class ExecutorBudget:
    threads: int = 8
    max_inflight: int = 1
    max_rss_bytes: int = 16 * 1024**3

    def __post_init__(self) -> None:
        if self.threads < 1 or self.max_inflight != 1 or self.max_rss_bytes < 1:
            raise ValueError("invalid LFE resource budget")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, int]:
        return {
            "threads": self.threads,
            "max_inflight": self.max_inflight,
            "max_rss_bytes": self.max_rss_bytes,
        }


def execution_backend_identity(*, threads: int) -> dict[str, object]:
    return {
        "schema": "duraloco-lfe-execution-backend-v1",
        "device": "cpu",
        "dtype": "float32",
        "torch_version": torch.__version__,
        "threads": threads,
        "reduction_order": "work-order-proposal-order-left-fold-v1",
    }


def execute_work_order(
    *,
    facade,
    layout: DistributedLayout,
    order: FragmentWorkOrderV1,
    current_params: torch.Tensor,
    current_outer_state: dict[str, torch.Tensor],
    proposal_tensors: dict[str, torch.Tensor],
    optimizer_config,
    executor_id: str,
    executor_session_id: str,
    attempt_id: str,
    resource_evidence_digest: str,
    budget: ExecutorBudget,
) -> tuple[PreparedFragmentResultV1, PreparedAttemptEnvelopeV1]:
    torch.set_num_threads(budget.threads)
    if canonical_digest(execution_backend_identity(threads=budget.threads)) != order.execution_backend_digest:
        raise ValueError("executor backend identity differs from work order")
    plan = FragmentPlan(
        fragment_id=order.fragment_id,
        parent_commit_id=order.parent_commit_id,
        parent_commit_seq=0,
        parent_frontier_digest=order.parent_frontier_digest,
        selected_proposal_ids=tuple(item.proposal_id for item in order.proposals),
        payload_sha256=tuple(item.payload_sha256 for item in order.proposals),
        weights_hex=tuple(item.weight_hex for item in order.proposals),
        aggregate_digest=canonical_digest(
            {
                "proposal_ids": [item.proposal_id for item in order.proposals],
                "payload_sha256": [item.payload_sha256 for item in order.proposals],
                "weights": [item.weight_hex for item in order.proposals],
            }
        ),
        selection_digest=order.work_order_id.removeprefix("fwo-"),
    )
    aggregate = reduce_fragment(
        plan=plan, proposal_tensors=proposal_tensors, current_params=current_params
    )
    computation = apply_outer_transition(
        aggregate=aggregate,
        current_params=current_params,
        current_outer_state=current_outer_state,
        optimizer_config=optimizer_config,
        optimizer_implementation_digest=order.outer_optimizer_impl_digest,
    )
    params_data = encode_production_params(computation.new_params)
    state_data = encode_production_outer_state(dict(computation.new_outer_state))
    params_ref = content_ref(
        f"{layout.prepared_prefix}payloads/params-{computation.params_content_sha256}.safetensors",
        params_data,
    )
    state_ref = content_ref(
        f"{layout.prepared_prefix}payloads/outer-{computation.outer_state_content_sha256}.safetensors",
        state_data,
    )
    facade.put_immutable(params_ref.key, params_data, sha256=params_ref.sha256)
    facade.put_immutable(state_ref.key, state_data, sha256=state_ref.sha256)
    result = PreparedFragmentResultV1.with_computed_id(
        {
            "schema": PreparedFragmentResultV1.SCHEMA,
            "work_order_id": order.work_order_id,
            "parent_commit_id": order.parent_commit_id,
            "validated_input_digests": sorted(item.payload_sha256 for item in order.proposals),
            "aggregate_digest": plan.aggregate_digest,
            "aggregate_content_sha256": computation.aggregate_content_sha256,
            "params_ref": params_ref.to_dict(),
            "outer_state_ref": state_ref.to_dict(),
            "state_semantic_digest": computation.state_semantic_digest,
            "numeric_implementation_digest": order.execution_backend_digest,
        }
    )
    envelope = PreparedAttemptEnvelopeV1.with_computed_id(
        {
            "schema": PreparedAttemptEnvelopeV1.SCHEMA,
            "prepared_result_id": result.prepared_result_id,
            "work_order_id": order.work_order_id,
            "executor_id": executor_id,
            "executor_session_id": executor_session_id,
            "attempt_id": attempt_id,
            "membership_revision": order.membership_revision,
            "resource_evidence_digest": resource_evidence_digest,
        }
    )
    rss_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    if rss_bytes > budget.max_rss_bytes:
        raise MemoryError("LFE exceeded its declared RSS budget")
    publish_prepared_attempt(facade, layout, result=result, envelope=envelope)
    return result, envelope
