"""Pre-registered, evidence-only P08 multi-FWO trigger evaluation."""

from __future__ import annotations

import math
from typing import Mapping, Sequence


REQUIRED_MODES = ("factor_one", "r2")


def evaluate_bundle_gate(
    *,
    wait_fractions: Mapping[str, Sequence[float]],
    optimistic_e2e_improvements: Mapping[str, float],
    measured_penalty_fraction: float = 0.0,
    wait_threshold: float = 0.25,
    required_transitions: int = 8,
    expected_transitions: int = 10,
    improvement_threshold: float = 0.15,
) -> dict[str, object]:
    """Evaluate D-0807 without creating any protocol or authority object.

    The E2E projection is deliberately an optimistic upper bound before the
    measured penalty. A below-threshold result rejects bundling; an
    above-threshold result only opens the schema gate.
    """

    if set(wait_fractions) != set(REQUIRED_MODES) or set(
        optimistic_e2e_improvements
    ) != set(REQUIRED_MODES):
        raise ValueError("bundle gate requires matched factor_one and r2 evidence")
    if not math.isfinite(measured_penalty_fraction) or measured_penalty_fraction < 0:
        raise ValueError("measured bundle penalty must be finite and non-negative")

    counts: dict[str, int] = {}
    normalized: dict[str, list[float]] = {}
    projected: dict[str, float] = {}
    for mode in REQUIRED_MODES:
        values = [float(value) for value in wait_fractions[mode]]
        if len(values) != expected_transitions or any(
            not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in values
        ):
            raise ValueError(
                f"{mode} must provide {expected_transitions} finite wait fractions"
            )
        raw_projection = float(optimistic_e2e_improvements[mode])
        if not math.isfinite(raw_projection) or not 0.0 <= raw_projection <= 1.0:
            raise ValueError(f"invalid E2E projection for {mode}")
        normalized[mode] = values
        counts[mode] = sum(value >= wait_threshold for value in values)
        projected[mode] = max(0.0, raw_projection - measured_penalty_fraction)

    wait_crossed = all(counts[mode] >= required_transitions for mode in REQUIRED_MODES)
    conservative_projection = min(projected.values())
    improvement_crossed = conservative_projection >= improvement_threshold
    triggered = wait_crossed and improvement_crossed
    return {
        "schema": "duraloco-bundle-gate-v1",
        "status": "PASS",
        "triggered": triggered,
        "conclusion": "implement_bounded_bundle" if triggered else "retain_single_fwo",
        "maximum_speculative_window": 2,
        "thresholds": {
            "wait_fraction": wait_threshold,
            "required_transitions": required_transitions,
            "expected_transitions": expected_transitions,
            "projected_e2e_improvement": improvement_threshold,
        },
        "wait_fractions": normalized,
        "transitions_crossing_wait_threshold": counts,
        "optimistic_e2e_improvements": {
            mode: float(optimistic_e2e_improvements[mode]) for mode in REQUIRED_MODES
        },
        "measured_penalty_fraction": measured_penalty_fraction,
        "penalty_adjusted_e2e_improvements": projected,
        "conservative_projected_e2e_improvement": conservative_projection,
        "wait_threshold_crossed": wait_crossed,
        "improvement_threshold_crossed": improvement_crossed,
        "authority_objects_written": 0,
    }
