"""Matched no-LFE/factor-one/R2 interference comparison."""

from __future__ import annotations

import math
from typing import Mapping


def compare_gpu_step_seconds(
    samples: Mapping[str, tuple[float, ...]],
) -> dict[str, object]:
    required = {"no_lfe", "factor_one", "r2"}
    if set(samples) != required:
        raise ValueError("interference comparison requires matched no_lfe/factor_one/r2 samples")
    means: dict[str, float] = {}
    for mode, values in samples.items():
        if not values or any(not math.isfinite(value) or value <= 0 for value in values):
            raise ValueError(f"invalid GPU step samples for {mode}")
        means[mode] = sum(values) / len(values)
    baseline = means["no_lfe"]
    return {
        "schema": "duraloco-lfe-interference-v1",
        "means": means,
        "factor_one_slowdown": means["factor_one"] / baseline - 1.0,
        "r2_slowdown": means["r2"] / baseline - 1.0,
        "sample_counts": {key: len(value) for key, value in samples.items()},
    }
