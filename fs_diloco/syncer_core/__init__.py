"""Pure syncer data-plane kernels shared by CRS and future executors."""

from .aggregation import (
    apply_outer_transition,
    compute_fragment_transition,
    reduce_fragment,
    validate_parameter_state_pair,
)
from .planning import PlanningCandidate, build_fragment_plan, select_candidate_ids
from .transaction_attempt import build_transition_attempt
from .types import FragmentComputation, FragmentPlan, TransitionAttempt

__all__ = [
    "FragmentComputation",
    "FragmentPlan",
    "PlanningCandidate",
    "TransitionAttempt",
    "build_fragment_plan",
    "build_transition_attempt",
    "apply_outer_transition",
    "compute_fragment_transition",
    "reduce_fragment",
    "select_candidate_ids",
    "validate_parameter_state_pair",
]
