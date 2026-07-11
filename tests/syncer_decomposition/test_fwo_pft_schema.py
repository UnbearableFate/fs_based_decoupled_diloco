from __future__ import annotations

import copy

import pytest

from fs_diloco.protocol.prepared_transition_v1 import (
    PreparedAttemptEnvelopeV1,
    PreparedFragmentResultV1,
)
from fs_diloco.protocol.work_order_v1 import FragmentWorkOrderV1


def _work_order_body() -> dict[str, object]:
    return {
        "schema": "duraloco-fragment-work-order-v1",
        "run_id": "run-test",
        "run_generation": 1,
        "parent_commit_id": "commit-parent",
        "parent_frontier_digest": "a" * 64,
        "fragment_id": 0,
        "committer_fencing_epoch": 2,
        "membership_revision": 0,
        "ownership_digest": "b" * 64,
        "proposals": [
            {
                "proposal_id": "proposal-a",
                "payload_sha256": "c" * 64,
                "target_tokens": 10,
                "base_fragment_version": 0,
                "weight_hex": (1.0).hex(),
            }
        ],
        "aggregation_policy_digest": "d" * 64,
        "outer_optimizer_impl_digest": "e" * 64,
        "execution_backend_digest": "f" * 64,
        "parameter_index_digest": "1" * 64,
        "fragment_layout_digest": "2" * 64,
    }


def test_work_order_round_trip_and_conflicting_identity_fail_closed():
    work_order = FragmentWorkOrderV1.with_computed_id(_work_order_body())
    assert FragmentWorkOrderV1.from_dict(work_order.to_dict()) == work_order
    conflict = work_order.to_dict()
    conflict["fragment_id"] = 1
    with pytest.raises(ValueError, match="work_order_id"):
        FragmentWorkOrderV1.from_dict(conflict)
    unknown = work_order.to_dict()
    unknown["unknown"] = "value"
    with pytest.raises(ValueError, match="field mismatch"):
        FragmentWorkOrderV1.from_dict(unknown)


def test_prepared_result_separates_canonical_result_from_attempt_envelope():
    work_order = FragmentWorkOrderV1.with_computed_id(_work_order_body())
    result = PreparedFragmentResultV1.with_computed_id(
        {
            "schema": "duraloco-prepared-fragment-result-v1",
            "work_order_id": work_order.work_order_id,
            "parent_commit_id": work_order.parent_commit_id,
            "validated_input_digests": ["3" * 64],
            "aggregate_digest": "4" * 64,
            "aggregate_content_sha256": "5" * 64,
            "params_ref": {"key": "params", "sha256": "6" * 64, "size": 8},
            "outer_state_ref": {"key": "outer", "sha256": "7" * 64, "size": 8},
            "state_semantic_digest": "8" * 64,
            "numeric_implementation_digest": "9" * 64,
        }
    )
    envelope_a = PreparedAttemptEnvelopeV1.with_computed_id(
        {
            "schema": "duraloco-prepared-attempt-envelope-v1",
            "prepared_result_id": result.prepared_result_id,
            "work_order_id": work_order.work_order_id,
            "executor_id": "executor-a",
            "executor_session_id": "session-a",
            "attempt_id": "attempt-a",
            "membership_revision": 0,
            "resource_evidence_digest": "a" * 64,
        }
    )
    envelope_b_body = copy.deepcopy(envelope_a.to_dict())
    envelope_b_body.pop("attempt_envelope_id")
    envelope_b_body["executor_id"] = "executor-b"
    envelope_b_body["executor_session_id"] = "session-b"
    envelope_b_body["attempt_id"] = "attempt-b"
    envelope_b = PreparedAttemptEnvelopeV1.with_computed_id(envelope_b_body)
    assert envelope_a.prepared_result_id == envelope_b.prepared_result_id
    assert envelope_a.attempt_envelope_id != envelope_b.attempt_envelope_id
    assert PreparedFragmentResultV1.from_dict(result.to_dict()) == result


def test_null_and_parameter_outer_ref_conflicts_fail_closed():
    body = _work_order_body()
    body["ownership_digest"] = None
    with pytest.raises(ValueError):
        FragmentWorkOrderV1.with_computed_id(body)

