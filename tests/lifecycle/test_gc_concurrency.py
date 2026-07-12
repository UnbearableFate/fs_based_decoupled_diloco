from __future__ import annotations

import pytest

from fs_diloco.coordination import OwnerToken
from fs_diloco.distributed_syncer.layout import DistributedLayout
from fs_diloco.log.gc import apply_gc, approval_token_for, create_gc_mark
from fs_diloco.log.pins import LifecyclePinV1, publish_pin
from fs_diloco.protocol.canonical_json import canonical_bytes
from fs_diloco.storage import FailureRule, InjectedTimeout
from tests.coordination.test_production_fencing import _initialize


def _synthetic_log(name: str):
    _backend, log = _initialize(f"synthetic-{name}")
    log.activate_owner(
        token=OwnerToken("syncer-a", "session-a", 1), request_id="activate-a"
    )
    return log


def _orphans(log):
    distributed = DistributedLayout(log.layout)
    result = log.backend.put_immutable(
        distributed.result_key("pfr-orphan"), b"orphan result"
    )
    attempt = log.backend.put_immutable(
        distributed.attempt_key("attempt-orphan"), b"orphan attempt"
    )
    marker = log.backend.put_immutable(
        distributed.marker_key("fwo-orphan", "attempt-orphan"), b"invalid marker"
    )
    return result, attempt, marker


def test_gc_defaults_to_mark_only_and_requires_namespace_bound_approval():
    log = _synthetic_log("gc-approval")
    refs = _orphans(log)
    eligible = {item.key for item in refs}
    mark, report = create_gc_mark(log, grace_eligible_keys=eligible)

    assert set(report.candidates) == {item.key for item in refs[:2]}
    assert refs[2].key in report.reachable  # malformed marker is quarantined
    assert all(log.backend.head(item.key) for item in refs)
    with pytest.raises(PermissionError, match="approval token"):
        apply_gc(
            log,
            mark,
            approval_token="wrong",
            namespace="synthetic",
            grace_eligible_keys=eligible,
            request_id="delete-a",
        )


def test_gc_apply_revalidates_and_deletes_markers_last():
    log = _synthetic_log("gc-marker-last")
    distributed = DistributedLayout(log.layout)
    result = log.backend.put_immutable(
        distributed.result_key("pfr-old"), b"result"
    )
    attempt = log.backend.put_immutable(
        distributed.attempt_key("attempt-old"), b"attempt"
    )
    marker = log.backend.put_immutable(
        distributed.marker_key("fwo-old", "attempt-old"),
        canonical_bytes(
            {
                "schema": "duraloco-prepared-attempt-marker-v1",
                "work_order_id": "fwo-old",
                "prepared_result_ref": result.to_ref().to_dict(),
                "attempt_envelope_ref": attempt.to_ref().to_dict(),
            }
        ),
    )
    eligible = {result.key, attempt.key, marker.key}
    mark, report = create_gc_mark(log, grace_eligible_keys=eligible)
    assert set(report.candidates) == eligible
    history_start = len(log.backend.history)
    applied = apply_gc(
        log,
        mark,
        approval_token=approval_token_for(mark, namespace="synthetic"),
        namespace="synthetic",
        grace_eligible_keys=eligible,
        request_id="delete-marker-last",
    )
    delete_keys = [
        record.key
        for record in log.backend.history[history_start:]
        if record.operation == "delete"
    ]
    assert set(applied.deleted) == eligible
    assert delete_keys[-1] == marker.key


def test_concurrent_pin_or_head_advance_invalidates_gc_mark():
    log = _synthetic_log("gc-revalidate")
    result, _attempt, _marker = _orphans(log)
    eligible = {result.key}
    mark, _report = create_gc_mark(log, grace_eligible_keys=eligible)
    pin = LifecyclePinV1.create(
        {
            "kind": "restore_point",
            "owner_id": "operator",
            "reason": "restore is starting",
            "object_refs": [result.to_ref().to_dict()],
        }
    )
    publish_pin(log.backend, log.layout, pin)
    with pytest.raises(RuntimeError, match="became reachable"):
        apply_gc(
            log,
            mark,
            approval_token=approval_token_for(mark, namespace="synthetic"),
            namespace="synthetic",
            grace_eligible_keys=eligible,
            request_id="delete-pinned",
        )

    other = _synthetic_log("gc-head-advance")
    result, _attempt, _marker = _orphans(other)
    mark, _report = create_gc_mark(other, grace_eligible_keys={result.key})
    other.commit_snapshot(request_id="snapshot-after-mark")
    with pytest.raises(RuntimeError, match="stale"):
        apply_gc(
            other,
            mark,
            approval_token=approval_token_for(mark, namespace="synthetic"),
            namespace="synthetic",
            grace_eligible_keys={result.key},
            request_id="delete-stale",
        )


def test_delete_response_loss_reconciles_by_request_and_object_identity():
    log = _synthetic_log("gc-response-loss")
    result, attempt, _marker = _orphans(log)
    eligible = {result.key, attempt.key}
    mark, report = create_gc_mark(log, grace_eligible_keys=eligible)
    assert {result.key, attempt.key} <= set(report.candidates)
    token = approval_token_for(mark, namespace="synthetic")
    log.backend.inject_failure(FailureRule("delete", "after"))
    with pytest.raises(InjectedTimeout):
        apply_gc(
            log,
            mark,
            approval_token=token,
            namespace="synthetic",
            grace_eligible_keys=eligible,
            request_id="delete-response-loss",
        )
    log.backend.clear_failures()

    recovered = apply_gc(
        log,
        mark,
        approval_token=token,
        namespace="synthetic",
        grace_eligible_keys=eligible,
        request_id="delete-response-loss",
    )
    repeated = apply_gc(
        log,
        mark,
        approval_token=token,
        namespace="synthetic",
        grace_eligible_keys=eligible,
        request_id="delete-response-loss",
    )

    assert recovered == repeated
    assert set(recovered.deleted) | set(recovered.already_missing) == eligible
    assert log.load_head().manifest == mark.head
