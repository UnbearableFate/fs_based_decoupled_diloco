from __future__ import annotations

import pytest

from fs_diloco.telemetry.interference import compare_gpu_step_seconds


def test_eight_node_interference_uses_factor_one_as_baseline() -> None:
    report = compare_gpu_step_seconds(
        {"factor_one": (1.0, 1.0), "r2": (1.1, 1.1)}
    )

    assert report["schema"] == "duraloco-lfe-interference-v2"
    assert report["baseline_mode"] == "factor_one"
    assert report["factor_one_slowdown"] == 0.0
    assert report["r2_slowdown"] == pytest.approx(0.1)


def test_historical_no_lfe_comparison_remains_readable() -> None:
    report = compare_gpu_step_seconds(
        {"no_lfe": (1.0,), "factor_one": (1.05,), "r2": (1.1,)}
    )

    assert report["schema"] == "duraloco-lfe-interference-v1"
    assert report["baseline_mode"] == "no_lfe"
    assert report["factor_one_slowdown"] == pytest.approx(0.05)


@pytest.mark.parametrize(
    "samples",
    [
        {"factor_one": (1.0,)},
        {"r2": (1.0,)},
        {"factor_one": (1.0,), "r2": (1.0,), "unexpected": (1.0,)},
    ],
)
def test_interference_rejects_incomplete_or_unknown_modes(samples) -> None:
    with pytest.raises(ValueError):
        compare_gpu_step_seconds(samples)
