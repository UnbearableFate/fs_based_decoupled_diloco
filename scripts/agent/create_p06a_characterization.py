#!/usr/bin/env python3
"""Create a deterministic archive-vs-decomposed CRS characterization trace."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform

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


ARCHIVE_COMMIT = "06e3ca2299d5eb1a720c1d8f9107af5223095525"
VERIFIED_IMPLEMENTATION = "2581a4d6286c7d0666f76aa3cc9d8122e66f6d25"
CHECKER_COMMIT = "030129e045c4e5a2abb80eb100a0e28fb78d384d"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    torch.manual_seed(0)
    current = torch.tensor([1.0, -2.0, 0.5, 3.0], dtype=torch.float32)
    proposals = {
        "proposal-a": torch.tensor([0.8, -1.7, 0.1, 2.5], dtype=torch.float32),
        "proposal-b": torch.tensor([1.3, -2.2, 0.9, 3.4], dtype=torch.float32),
    }
    tokens = {"proposal-a": 10, "proposal-b": 30}
    config = OuterOptimizerConfig(name="nesterov", lr=0.2, momentum=0.7)
    state = {"step": torch.tensor(2, dtype=torch.int64), "momentum": torch.zeros_like(current)}

    archive_weights = normalized_weights(tokens, config=ReferenceWeightingConfig())
    archive_aggregate = proposals["proposal-a"].mul(archive_weights["proposal-a"])
    archive_aggregate = archive_aggregate.add(
        proposals["proposal-b"], alpha=archive_weights["proposal-b"]
    )
    archive_params, archive_state = outer_optimizer_step(
        current, current - archive_aggregate, state, config
    )

    candidates = tuple(
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
    )
    plan = build_fragment_plan(
        reversed(candidates),
        fragment_id=0,
        current_fragment_version=0,
        parent_commit_id="commit-parent",
        parent_commit_seq=0,
        parent_frontier_digest="f" * 64,
        quorum_max=2,
        weighting_config=ReferenceWeightingConfig(),
    )
    optimizer_identity = {
        "name": config.name,
        "lr": config.lr.hex(),
        "momentum": config.momentum.hex(),
        "weight_decay": config.weight_decay.hex(),
        "betas": [value.hex() for value in config.betas],
        "eps": config.eps.hex(),
    }
    implementation_digest = production_optimizer_digest(optimizer_identity)
    aggregate = reduce_fragment(plan=plan, proposal_tensors=proposals, current_params=current)
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
    archive_params_bytes = encode_production_params(archive_params)
    archive_state_bytes = encode_production_outer_state(archive_state)
    if not torch.equal(archive_aggregate, aggregate):
        raise RuntimeError("archive and decomposed aggregate differ")
    if archive_params_bytes != attempt.new_params or archive_state_bytes != attempt.new_outer_state:
        raise RuntimeError("archive and decomposed parameter/state bytes differ")

    trace = {
        "schema": "duraloco-p06a-crs-characterization-v1",
        "archive_commit": ARCHIVE_COMMIT,
        "verified_dependency_implementation": VERIFIED_IMPLEMENTATION,
        "verified_dependency_checker_commit": CHECKER_COMMIT,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "device": "cpu",
            "dtype": "float32",
            "threads": torch.get_num_threads(),
            "reduction_order": "proposal_id-ascending-left-fold-v1",
        },
        "input": {
            "parent_commit_id": plan.parent_commit_id,
            "parent_frontier_digest": plan.parent_frontier_digest,
            "selected_proposal_ids": list(plan.selected_proposal_ids),
            "payload_sha256": list(plan.payload_sha256),
            "weights_hex": list(plan.weights_hex),
            "optimizer_identity": optimizer_identity,
        },
        "archive_output": {
            "aggregate_content_sha256": computation.aggregate_content_sha256,
            "params_content_sha256": computation.params_content_sha256,
            "outer_state_content_sha256": computation.outer_state_content_sha256,
        },
        "decomposed_output": {
            "selection_digest": plan.selection_digest,
            "aggregate_digest": plan.aggregate_digest,
            "aggregate_content_sha256": computation.aggregate_content_sha256,
            "params_content_sha256": computation.params_content_sha256,
            "outer_state_content_sha256": computation.outer_state_content_sha256,
            "state_semantic_digest": computation.state_semantic_digest,
            "transition_attempt_semantic_digest": attempt.semantic_digest,
        },
        "equivalence": {
            "selected_ids_exact": True,
            "weights_exact": True,
            "aggregate_bytes_exact": True,
            "params_bytes_exact": True,
            "outer_state_bytes_exact": True,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
