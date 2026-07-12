"""Deterministic optimizer adapters used by the durable DuraLoCo log."""

from .reference_adapter import TransitionOutput, transition

__all__ = ["TransitionOutput", "transition"]
from .fragment_access import (
    FragmentAccessPlan,
    FragmentAccessPlanCache,
    model_parameter_norm,
)
from .streaming_reduce import StreamingReductionStats, reduce_fragment_streaming

__all__ = [
    "FragmentAccessPlan",
    "FragmentAccessPlanCache",
    "StreamingReductionStats",
    "model_parameter_norm",
    "reduce_fragment_streaming",
]
