"""Pure builder for the one authoritative production-log prepare call."""

from __future__ import annotations

from fs_diloco.log.production_codec import (
    encode_production_outer_state,
    encode_production_params,
)
from fs_diloco.protocol.canonical_json import canonical_digest

from .types import FragmentComputation, FragmentPlan, TransitionAttempt


def build_transition_attempt(
    *,
    plan: FragmentPlan,
    computation: FragmentComputation,
    owner_id: str,
    owner_session_id: str,
    fencing_epoch: int,
    outer_optimizer_impl_digest: str,
) -> TransitionAttempt:
    request_id = "optimizer-" + canonical_digest(
        {
            "owner_id": owner_id,
            "owner_session_id": owner_session_id,
            "fencing_epoch": fencing_epoch,
            "parent_commit_id": plan.parent_commit_id,
            "selected_proposal_ids": list(plan.selected_proposal_ids),
        }
    )
    new_params = encode_production_params(computation.new_params)
    new_outer_state = encode_production_outer_state(dict(computation.new_outer_state))
    semantic_digest = canonical_digest(
        {
            "fragment_id": plan.fragment_id,
            "parent_commit_id": plan.parent_commit_id,
            "selected_proposal_ids": list(plan.selected_proposal_ids),
            "aggregate_digest": plan.aggregate_digest,
            "params_content_sha256": computation.params_content_sha256,
            "outer_state_content_sha256": computation.outer_state_content_sha256,
            "outer_optimizer_impl_digest": outer_optimizer_impl_digest,
        }
    )
    return TransitionAttempt(
        fragment_id=plan.fragment_id,
        selected_proposal_ids=plan.selected_proposal_ids,
        new_params=new_params,
        new_outer_state=new_outer_state,
        aggregate_digest=plan.aggregate_digest,
        outer_optimizer_impl_digest=outer_optimizer_impl_digest,
        request_id=request_id,
        semantic_digest=semantic_digest,
    )

