"""Pure deterministic tensor aggregation and outer-optimizer execution."""

from __future__ import annotations

from typing import Any, Mapping

import torch

from fs_diloco.log.production_codec import (
    encode_production_outer_state,
    encode_production_params,
)
from fs_diloco.outer_optim import config_from_any, outer_optimizer_step

from .semantic_digest import content_digest, paired_state_semantic_digest
from .types import FragmentComputation, FragmentPlan


def validate_parameter_state_pair(
    params: torch.Tensor,
    outer_state: Mapping[str, torch.Tensor],
    optimizer_config: Any,
) -> None:
    if params.ndim != 1 or params.numel() < 1 or not torch.is_floating_point(params):
        raise ValueError("parameter fragment must be a non-empty floating flat tensor")
    if not bool(torch.isfinite(params).all().item()):
        raise ValueError("parameter fragment contains non-finite values")
    step = outer_state.get("step")
    if step is None or step.numel() != 1 or step.dtype != torch.int64:
        raise ValueError("outer optimizer state requires one int64 step tensor")
    config = config_from_any(optimizer_config)
    expected = (
        {"step", "exp_avg", "exp_avg_sq"}
        if config.name.lower() == "adamw"
        else {"step", "momentum"}
    )
    if set(outer_state) != expected:
        raise ValueError("outer optimizer state keys do not match optimizer identity")
    for key in expected - {"step"}:
        tensor = outer_state[key]
        if tensor.shape != params.shape or tensor.dtype != params.dtype:
            raise ValueError(f"outer optimizer tensor {key} does not match parameter fragment")
        if not bool(torch.isfinite(tensor).all().item()):
            raise ValueError(f"outer optimizer tensor {key} contains non-finite values")


def compute_fragment_transition(
    *,
    plan: FragmentPlan,
    proposal_tensors: Mapping[str, torch.Tensor],
    current_params: torch.Tensor,
    current_outer_state: Mapping[str, torch.Tensor],
    optimizer_config: Any,
    optimizer_implementation_digest: str,
) -> FragmentComputation:
    """Execute exactly the frozen ordered reduction and paired outer step."""

    aggregate = reduce_fragment(
        plan=plan,
        proposal_tensors=proposal_tensors,
        current_params=current_params,
    )
    return apply_outer_transition(
        aggregate=aggregate,
        current_params=current_params,
        current_outer_state=current_outer_state,
        optimizer_config=optimizer_config,
        optimizer_implementation_digest=optimizer_implementation_digest,
    )


def reduce_fragment(
    *,
    plan: FragmentPlan,
    proposal_tensors: Mapping[str, torch.Tensor],
    current_params: torch.Tensor,
) -> torch.Tensor:
    """Reduce proposal tensors in the exact order frozen by the plan."""

    if (
        current_params.ndim != 1
        or current_params.numel() < 1
        or not torch.is_floating_point(current_params)
        or not bool(torch.isfinite(current_params).all().item())
    ):
        raise ValueError("current parameter fragment must be a finite floating flat tensor")
    if set(proposal_tensors) != set(plan.selected_proposal_ids):
        raise ValueError("proposal tensors must exactly match the frozen plan")
    ordered = tuple(proposal_tensors[proposal_id] for proposal_id in plan.selected_proposal_ids)
    for proposal_id, tensor in zip(plan.selected_proposal_ids, ordered, strict=True):
        if tensor.shape != current_params.shape:
            raise ValueError(f"proposal {proposal_id} size differs from current fragment")
        if not torch.is_floating_point(tensor) or not bool(torch.isfinite(tensor).all().item()):
            raise ValueError(f"proposal {proposal_id} is not a finite floating tensor")
    weights = plan.weights
    aggregate = ordered[0].mul(weights[0])
    for tensor, weight in zip(ordered[1:], weights[1:], strict=True):
        aggregate = aggregate.add(tensor, alpha=weight)
    return aggregate


def apply_outer_transition(
    *,
    aggregate: torch.Tensor,
    current_params: torch.Tensor,
    current_outer_state: Mapping[str, torch.Tensor],
    optimizer_config: Any,
    optimizer_implementation_digest: str,
) -> FragmentComputation:
    """Apply the existing outer optimizer and bind the parameter/state pair."""

    validate_parameter_state_pair(current_params, current_outer_state, optimizer_config)
    if aggregate.shape != current_params.shape or not bool(torch.isfinite(aggregate).all().item()):
        raise ValueError("aggregate must be finite and match the current parameter fragment")
    gradient = current_params - aggregate
    new_params, new_outer_state = outer_optimizer_step(
        current_params,
        gradient,
        dict(current_outer_state),
        optimizer_config,
    )
    validate_parameter_state_pair(new_params, new_outer_state, optimizer_config)
    aggregate_bytes = encode_production_params(aggregate)
    params_bytes = encode_production_params(new_params)
    outer_state_bytes = encode_production_outer_state(new_outer_state)
    params_sha256 = content_digest(params_bytes)
    outer_state_sha256 = content_digest(outer_state_bytes)
    return FragmentComputation(
        aggregate=aggregate,
        new_params=new_params,
        new_outer_state=new_outer_state,
        aggregate_content_sha256=content_digest(aggregate_bytes),
        params_content_sha256=params_sha256,
        outer_state_content_sha256=outer_state_sha256,
        state_semantic_digest=paired_state_semantic_digest(
            params_content_sha256=params_sha256,
            outer_state_content_sha256=outer_state_sha256,
            optimizer_implementation_digest=optimizer_implementation_digest,
        ),
    )
