"""O(fragment) ordered weighted reduction for learner-hosted executors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import torch

from fs_diloco.syncer_core.types import FragmentPlan


@dataclass(frozen=True)
class StreamingReductionStats:
    proposal_count: int
    fragment_numel: int
    accumulator_bytes: int
    peak_proposal_bytes: int
    peak_working_bytes: int
    load_count: int
    finite_check_count: int

    def to_counters(self) -> dict[str, int]:
        return {
            "proposal_count": self.proposal_count,
            "fragment_numel": self.fragment_numel,
            "accumulator_bytes": self.accumulator_bytes,
            "peak_proposal_bytes": self.peak_proposal_bytes,
            "peak_working_bytes": self.peak_working_bytes,
            "load_count": self.load_count,
            "finite_check_count": self.finite_check_count,
        }


def reduce_fragment_streaming(
    *,
    plan: FragmentPlan,
    load_proposal: Callable[[str], torch.Tensor],
    current_params: torch.Tensor,
    max_inflight_bytes: int | None = None,
) -> tuple[torch.Tensor, StreamingReductionStats]:
    """Load, validate, accumulate, and release one proposal in canonical order."""

    if (
        current_params.ndim != 1
        or current_params.numel() < 1
        or not torch.is_floating_point(current_params)
        or not bool(torch.isfinite(current_params).all().item())
    ):
        raise ValueError("current parameter fragment must be a finite floating flat tensor")
    accumulator: torch.Tensor | None = None
    peak_proposal_bytes = 0
    load_count = 0
    finite_checks = 0
    for proposal_id, weight in zip(
        plan.selected_proposal_ids, plan.weights, strict=True
    ):
        tensor = load_proposal(proposal_id)
        load_count += 1
        if tensor.shape != current_params.shape:
            raise ValueError(f"proposal {proposal_id} size differs from current fragment")
        if not torch.is_floating_point(tensor):
            raise ValueError(f"proposal {proposal_id} is not floating point")
        finite_checks += 1
        if not bool(torch.isfinite(tensor).all().item()):
            raise ValueError(f"proposal {proposal_id} is not finite")
        proposal_bytes = tensor.numel() * tensor.element_size()
        peak_proposal_bytes = max(peak_proposal_bytes, proposal_bytes)
        if max_inflight_bytes is not None and proposal_bytes > max_inflight_bytes:
            raise MemoryError("proposal exceeds the declared streaming in-flight budget")
        values = tensor.detach().to(
            device=current_params.device,
            dtype=torch.float32,
            non_blocking=False,
        )
        if accumulator is None:
            accumulator = values.mul(weight)
        else:
            accumulator.add_(values, alpha=weight)
        del values
        del tensor
    if accumulator is None:
        raise ValueError("streaming reduction requires at least one proposal")
    accumulator = accumulator.contiguous()
    accumulator_bytes = accumulator.numel() * accumulator.element_size()
    return accumulator, StreamingReductionStats(
        proposal_count=len(plan.selected_proposal_ids),
        fragment_numel=int(accumulator.numel()),
        accumulator_bytes=accumulator_bytes,
        peak_proposal_bytes=peak_proposal_bytes,
        peak_working_bytes=accumulator_bytes + peak_proposal_bytes,
        load_count=load_count,
        finite_check_count=finite_checks,
    )
