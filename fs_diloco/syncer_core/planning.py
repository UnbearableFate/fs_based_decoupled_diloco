"""Deterministic proposal selection and fragment planning.

This module consumes already validated proposal metadata. It performs no I/O and
does not consult clocks, process identity, listing order, or mutable globals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.testing.deterministic_reference import (
    ReferenceWeightingConfig,
    normalized_weights,
)

from .types import FragmentPlan


@dataclass(frozen=True)
class PlanningCandidate:
    proposal_id: str
    learner_id: str
    sequence: int
    fragment_id: int
    target_tokens: int
    base_fragment_version: int
    payload_sha256: str

    def __post_init__(self) -> None:
        if not self.proposal_id or not self.learner_id:
            raise ValueError("planning candidate identities must be non-empty")
        if self.sequence < 0 or self.fragment_id < 0 or self.base_fragment_version < 0:
            raise ValueError("planning candidate integer fields must be non-negative")
        if self.target_tokens < 1:
            raise ValueError("planning candidate target_tokens must be positive")
        if len(self.payload_sha256) != 64:
            raise ValueError("planning candidate payload_sha256 must be a SHA-256 digest")


def select_candidate_ids(
    candidates: Iterable[PlanningCandidate],
    *,
    fragment_id: int,
    quorum_max: int,
) -> tuple[str, ...]:
    """Select the oldest proposal per learner, then canonicalize by proposal ID."""

    if fragment_id < 0 or quorum_max < 1:
        raise ValueError("fragment_id must be non-negative and quorum_max positive")
    by_learner: dict[str, PlanningCandidate] = {}
    identities: dict[str, PlanningCandidate] = {}
    for candidate in candidates:
        prior_identity = identities.get(candidate.proposal_id)
        if prior_identity is not None and prior_identity != candidate:
            raise ValueError("one proposal identity maps to conflicting planning content")
        identities[candidate.proposal_id] = candidate
        if candidate.fragment_id != fragment_id:
            continue
        current = by_learner.get(candidate.learner_id)
        candidate_key = (candidate.sequence, candidate.proposal_id)
        if current is None or candidate_key < (current.sequence, current.proposal_id):
            by_learner[candidate.learner_id] = candidate
    selected = sorted(by_learner.values(), key=lambda item: item.proposal_id)
    return tuple(item.proposal_id for item in selected[:quorum_max])


def build_fragment_plan(
    candidates: Iterable[PlanningCandidate],
    *,
    fragment_id: int,
    current_fragment_version: int,
    parent_commit_id: str,
    parent_commit_seq: int,
    parent_frontier_digest: str,
    quorum_max: int,
    weighting_config: ReferenceWeightingConfig,
) -> FragmentPlan:
    """Freeze selection and weights into a replayable fragment plan."""

    materialized = tuple(candidates)
    selected_ids = select_candidate_ids(
        materialized,
        fragment_id=fragment_id,
        quorum_max=quorum_max,
    )
    if not selected_ids:
        raise ValueError("fragment planning requires at least one eligible proposal")
    by_id = {candidate.proposal_id: candidate for candidate in materialized}
    selected = tuple(by_id[proposal_id] for proposal_id in selected_ids)
    weights = normalized_weights(
        {item.proposal_id: item.target_tokens for item in selected},
        staleness={
            item.proposal_id: current_fragment_version - item.base_fragment_version
            for item in selected
        },
        config=weighting_config,
    )
    weights_hex = tuple(weights[proposal_id].hex() for proposal_id in selected_ids)
    payload_sha256 = tuple(item.payload_sha256 for item in selected)
    aggregate_digest = canonical_digest(
        {
            "proposal_ids": list(selected_ids),
            "payload_sha256": list(payload_sha256),
            "weights": list(weights_hex),
        }
    )
    plan_body = {
        "fragment_id": fragment_id,
        "parent_commit_id": parent_commit_id,
        "parent_commit_seq": parent_commit_seq,
        "parent_frontier_digest": parent_frontier_digest,
        "selected_proposal_ids": list(selected_ids),
        "payload_sha256": list(payload_sha256),
        "weights": list(weights_hex),
        "aggregate_digest": aggregate_digest,
    }
    return FragmentPlan(
        fragment_id=fragment_id,
        parent_commit_id=parent_commit_id,
        parent_commit_seq=parent_commit_seq,
        parent_frontier_digest=parent_frontier_digest,
        selected_proposal_ids=selected_ids,
        payload_sha256=payload_sha256,
        weights_hex=weights_hex,
        aggregate_digest=aggregate_digest,
        selection_digest=canonical_digest(plan_body),
    )

