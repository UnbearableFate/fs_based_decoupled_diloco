"""Matched eight-node factor-one/R2 interference comparison."""

from __future__ import annotations

import math
from typing import Mapping


def compare_gpu_step_seconds(
    samples: Mapping[str, tuple[float, ...]],
) -> dict[str, object]:
    modes = set(samples)
    required = {"factor_one", "r2"}
    if not required.issubset(modes) or not modes.issubset({"no_lfe", *required}):
        raise ValueError(
            "interference comparison requires matched factor_one/r2 samples "
            "and accepts no_lfe only as a historical optional baseline"
        )
    means: dict[str, float] = {}
    for mode, values in samples.items():
        if not values or any(not math.isfinite(value) or value <= 0 for value in values):
            raise ValueError(f"invalid GPU step samples for {mode}")
        means[mode] = sum(values) / len(values)
    baseline_mode = "no_lfe" if "no_lfe" in means else "factor_one"
    baseline = means[baseline_mode]
    return {
        "schema": (
            "duraloco-lfe-interference-v1"
            if baseline_mode == "no_lfe"
            else "duraloco-lfe-interference-v2"
        ),
        "baseline_mode": baseline_mode,
        "means": means,
        "factor_one_slowdown": means["factor_one"] / baseline - 1.0,
        "r2_slowdown": means["r2"] / baseline - 1.0,
        "sample_counts": {key: len(value) for key, value in samples.items()},
    }
