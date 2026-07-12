"""P04 adapter over the frozen P02 standard-library optimizer oracle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

from fs_diloco.testing.deterministic_reference import (
    ReferenceOptimizerConfig,
    ReferenceOptimizerState,
    ReferenceWeightingConfig,
    Vector,
    normalized_weights,
    optimizer_state_digest,
    outer_step,
    weighted_reduce,
)

if TYPE_CHECKING:
    from fs_diloco.log.model import ReferenceProposal


@dataclass(frozen=True)
class TransitionOutput:
    aggregate: Vector
    weights: tuple[tuple[str, float], ...]
    new_params: Vector
    new_outer_state: ReferenceOptimizerState
    transition_digest: str


def transition(
    *,
    current_params: Vector,
    current_outer_state: ReferenceOptimizerState,
    current_fragment_version: int,
    proposals: Iterable[ReferenceProposal],
    optimizer_config: ReferenceOptimizerConfig,
    weighting_config: ReferenceWeightingConfig,
) -> TransitionOutput:
    selected = tuple(sorted(proposals, key=lambda proposal: proposal.proposal_id))
    if not selected:
        raise ValueError("transition requires at least one proposal")
    if len({proposal.proposal_id for proposal in selected}) != len(selected):
        raise ValueError("transition proposal IDs must be unique")
    if len({proposal.learner_id for proposal in selected}) != len(selected):
        raise ValueError("transition permits at most one proposal per learner")
    weights = normalized_weights(
        {proposal.proposal_id: proposal.target_tokens for proposal in selected},
        staleness={
            proposal.proposal_id: current_fragment_version - proposal.base_fragment_version
            for proposal in selected
        },
        config=weighting_config,
    )
    aggregate = weighted_reduce(
        {proposal.proposal_id: proposal.values for proposal in selected}, weights
    )
    new_params, new_outer_state = outer_step(
        current_params,
        aggregate,
        current_outer_state,
        optimizer_config,
    )
    return TransitionOutput(
        aggregate=aggregate,
        weights=tuple((key, weights[key]) for key in sorted(weights)),
        new_params=new_params,
        new_outer_state=new_outer_state,
        transition_digest=optimizer_state_digest(
            new_params, new_outer_state, optimizer_config
        ),
    )
