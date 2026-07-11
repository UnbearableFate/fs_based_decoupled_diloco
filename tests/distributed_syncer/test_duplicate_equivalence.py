from __future__ import annotations

from itertools import permutations

import pytest

from fs_diloco.distributed_syncer.duplicate_validation import (
    DivergentPreparedResult,
    PreparedResultObservation,
    decide_duplicate_results,
)


def _observation(executor: str, result: str = "pfr-same") -> PreparedResultObservation:
    return PreparedResultObservation(
        work_order_id="fwo-one",
        prepared_result_id=result,
        attempt_envelope_id=f"attempt-{executor}",
        executor_id=executor,
    )


def test_equivalent_duplicate_arrival_order_cannot_change_decision():
    rows = (_observation("primary"), _observation("backup"))
    decisions = {
        decide_duplicate_results("fwo-one", tuple(order), required_attempts=2)
        for order in permutations(rows)
    }
    assert len(decisions) == 1
    decision = decisions.pop()
    assert decision.prepared_result_id == "pfr-same"
    assert decision.attempt_envelope_ids == ("attempt-backup", "attempt-primary")


def test_same_fwo_divergence_blocks_and_preserves_both_identities():
    with pytest.raises(DivergentPreparedResult) as error:
        decide_duplicate_results(
            "fwo-one",
            (_observation("primary", "pfr-left"), _observation("backup", "pfr-right")),
            required_attempts=2,
        )
    assert "pfr-left" in str(error.value) and "pfr-right" in str(error.value)


def test_different_work_order_is_not_deduplicated_by_payload_or_result_id():
    foreign = PreparedResultObservation(
        work_order_id="fwo-other",
        prepared_result_id="pfr-same",
        attempt_envelope_id="attempt-foreign",
        executor_id="foreign",
    )
    with pytest.raises(ValueError, match="work order"):
        decide_duplicate_results(
            "fwo-one", (_observation("primary"), foreign), required_attempts=2
        )


def test_duplicate_decision_requires_distinct_attempt_and_executor_ids():
    with pytest.raises(ValueError, match="distinct"):
        decide_duplicate_results(
            "fwo-one", (_observation("same"), _observation("same")), required_attempts=2
        )
