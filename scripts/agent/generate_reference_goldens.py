#!/usr/bin/env python3
"""Print reviewable deterministic P02 optimizer and trace golden vectors."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fs_diloco.testing.deterministic_reference import (
    ReferenceOptimizerConfig,
    initial_state,
    optimizer_state_digest,
    outer_step,
    vector_identity,
)
from fs_diloco.testing.model_checker import run_seeded_traces
from fs_diloco.testing.trace import generate_trace, replay_trace


THETA = (1.0, -2.0, 0.5)
GRADIENTS = (
    (0.1, -0.2, 0.3),
    (-0.4, 0.5, 0.2),
    (0.0, -0.1, 0.7),
)


def optimizer_vectors() -> dict[str, object]:
    vectors: dict[str, object] = {}
    for name in ("sgd", "momentum", "nesterov", "adamw"):
        config = ReferenceOptimizerConfig(
            name=name,
            lr=0.03,
            momentum=0.8,
            weight_decay=0.01,
            betas=(0.7, 0.95),
            eps=1.0e-8,
        )
        theta = THETA
        state = initial_state(len(theta), config)
        for gradient in GRADIENTS:
            theta, state = outer_step(theta, gradient, state, config)
        vectors[name] = {
            "config": config.identity(),
            "theta": vector_identity(theta),
            "state": state.identity(),
            "digest": optimizer_state_digest(theta, state, config),
        }
    return vectors


def main() -> int:
    trace = generate_trace(20260710, steps=30)
    payload = {
        "optimizers": optimizer_vectors(),
        "trace": {
            "seed": trace.seed,
            "event_count": len(trace.events),
            "trace_digest": trace.digest,
            "state_digest": replay_trace(trace).state_digest(),
        },
        "suite_100": run_seeded_traces(count=100, steps=10),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
