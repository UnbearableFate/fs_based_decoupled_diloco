from __future__ import annotations

import pytest

from fs_diloco.telemetry.bundle_gate import evaluate_bundle_gate


def test_gate_retains_single_fwo_when_optimistic_e2e_bound_is_below_threshold():
    report = evaluate_bundle_gate(
        wait_fractions={"factor_one": [0.5] * 10, "r2": [0.4] * 10},
        optimistic_e2e_improvements={"factor_one": 0.14, "r2": 0.12},
    )
    assert report["status"] == "PASS"
    assert report["triggered"] is False
    assert report["conclusion"] == "retain_single_fwo"
    assert report["authority_objects_written"] == 0


def test_gate_requires_both_matched_modes_to_cross_both_thresholds():
    report = evaluate_bundle_gate(
        wait_fractions={
            "factor_one": [0.3] * 10,
            "r2": [0.3] * 7 + [0.2] * 3,
        },
        optimistic_e2e_improvements={"factor_one": 0.2, "r2": 0.2},
    )
    assert report["transitions_crossing_wait_threshold"] == {
        "factor_one": 10,
        "r2": 7,
    }
    assert report["triggered"] is False


def test_gate_opens_only_after_penalty_adjusted_projection_crosses():
    report = evaluate_bundle_gate(
        wait_fractions={"factor_one": [0.3] * 10, "r2": [0.3] * 10},
        optimistic_e2e_improvements={"factor_one": 0.2, "r2": 0.19},
        measured_penalty_fraction=0.03,
    )
    assert report["triggered"] is True
    assert report["maximum_speculative_window"] == 2


def test_gate_rejects_incomplete_or_unmatched_evidence():
    with pytest.raises(ValueError, match="10 finite wait fractions"):
        evaluate_bundle_gate(
            wait_fractions={"factor_one": [0.3] * 9, "r2": [0.3] * 10},
            optimistic_e2e_improvements={"factor_one": 0.2, "r2": 0.2},
        )
