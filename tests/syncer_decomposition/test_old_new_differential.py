from __future__ import annotations

import pytest
import torch

from fs_diloco.log.production_codec import (
    encode_production_outer_state,
    encode_production_params,
    production_optimizer_digest,
)
from fs_diloco.outer_optim import OuterOptimizerConfig, outer_optimizer_step
from fs_diloco.syncer_core import (
    PlanningCandidate,
    apply_outer_transition,
    build_fragment_plan,
    build_transition_attempt,
    reduce_fragment,
)
from fs_diloco.testing.deterministic_reference import ReferenceWeightingConfig, normalized_weights


def _archive_inline_step(
    current: torch.Tensor,
    state: dict[str, torch.Tensor],
    proposals: dict[str, torch.Tensor],
    tokens: dict[str, int],
    config: OuterOptimizerConfig,
) -> tuple[torch.Tensor, dict[str, torch.Tensor], torch.Tensor, dict[str, float]]:
    weights = normalized_weights(tokens, config=ReferenceWeightingConfig())
    ordered = sorted(proposals)
    aggregate = proposals[ordered[0]].mul(weights[ordered[0]])
    for proposal_id in ordered[1:]:
        aggregate = aggregate.add(proposals[proposal_id], alpha=weights[proposal_id])
    new_params, new_state = outer_optimizer_step(current, current - aggregate, state, config)
    return new_params, new_state, aggregate, weights


@pytest.mark.parametrize("optimizer", ["sgd", "momentum", "nesterov", "adamw"])
def test_decomposed_kernel_is_byte_exact_to_archive_inline_path(optimizer):
    config = OuterOptimizerConfig(name=optimizer, lr=0.2, momentum=0.7, weight_decay=0.01)
    current = torch.tensor([1.0, -2.0, 0.5], dtype=torch.float32)
    state: dict[str, torch.Tensor] = {"step": torch.tensor(2, dtype=torch.int64)}
    if optimizer == "adamw":
        state.update(exp_avg=torch.zeros_like(current), exp_avg_sq=torch.zeros_like(current))
    else:
        state["momentum"] = torch.zeros_like(current)
    proposals = {
        "proposal-a": torch.tensor([0.8, -1.7, 0.1]),
        "proposal-b": torch.tensor([1.3, -2.2, 0.9]),
    }
    tokens = {"proposal-a": 10, "proposal-b": 30}
    expected_params, expected_state, expected_aggregate, expected_weights = _archive_inline_step(
        current, state, proposals, tokens, config
    )
    plan = build_fragment_plan(
        (
            PlanningCandidate(
                proposal_id=proposal_id,
                learner_id=f"learner-{index}",
                sequence=1,
                fragment_id=0,
                target_tokens=tokens[proposal_id],
                base_fragment_version=0,
                payload_sha256=str(index + 1) * 64,
            )
            for index, proposal_id in enumerate(sorted(proposals))
        ),
        fragment_id=0,
        current_fragment_version=0,
        parent_commit_id="parent",
        parent_commit_seq=0,
        parent_frontier_digest="f" * 64,
        quorum_max=2,
        weighting_config=ReferenceWeightingConfig(),
    )
    aggregate = reduce_fragment(plan=plan, proposal_tensors=proposals, current_params=current)
    implementation_digest = production_optimizer_digest(
        {
            "name": optimizer,
            "lr": config.lr.hex(),
            "momentum": config.momentum.hex(),
            "weight_decay": config.weight_decay.hex(),
            "betas": [value.hex() for value in config.betas],
            "eps": config.eps.hex(),
        }
    )
    computation = apply_outer_transition(
        aggregate=aggregate,
        current_params=current,
        current_outer_state=state,
        optimizer_config=config,
        optimizer_implementation_digest=implementation_digest,
    )
    attempt = build_transition_attempt(
        plan=plan,
        computation=computation,
        owner_id="owner-a",
        owner_session_id="session-a",
        fencing_epoch=1,
        outer_optimizer_impl_digest=implementation_digest,
    )
    assert torch.equal(aggregate, expected_aggregate)
    assert plan.weights_hex == tuple(expected_weights[key].hex() for key in sorted(proposals))
    assert encode_production_params(computation.new_params) == encode_production_params(
        expected_params
    )
    assert attempt.new_outer_state == encode_production_outer_state(expected_state)


def test_parameter_outer_state_mismatch_fails_closed():
    config = OuterOptimizerConfig(name="nesterov")
    plan = build_fragment_plan(
        (
            PlanningCandidate(
                proposal_id="proposal-a",
                learner_id="learner-a",
                sequence=1,
                fragment_id=0,
                target_tokens=1,
                base_fragment_version=0,
                payload_sha256="a" * 64,
            ),
        ),
        fragment_id=0,
        current_fragment_version=0,
        parent_commit_id="parent",
        parent_commit_seq=0,
        parent_frontier_digest="f" * 64,
        quorum_max=1,
        weighting_config=ReferenceWeightingConfig(),
    )
    current = torch.ones(3)
    aggregate = reduce_fragment(
        plan=plan,
        proposal_tensors={"proposal-a": torch.ones(3)},
        current_params=current,
    )
    with pytest.raises(ValueError, match="does not match parameter fragment"):
        apply_outer_transition(
            aggregate=aggregate,
            current_params=current,
            current_outer_state={
                "step": torch.tensor(0, dtype=torch.int64),
                "momentum": torch.zeros(2),
            },
            optimizer_config=config,
            optimizer_implementation_digest="a" * 64,
        )

