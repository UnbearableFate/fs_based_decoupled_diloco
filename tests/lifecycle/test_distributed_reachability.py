from __future__ import annotations

from fs_diloco.distributed_syncer.layout import DistributedLayout
from fs_diloco.log.acknowledgements import (
    LifecycleAcknowledgementV1,
    publish_acknowledgement,
)
from fs_diloco.log.pins import LifecyclePinV1, publish_pin
from fs_diloco.log.reachability import build_reachability
from tests.distributed_syncer.test_distributed_transition_binding import (
    _initialize,
    _prepare,
    _proposal,
)


def _committed_log(run_id_suffix: str):
    log = _initialize(distributed=True)
    proposal = _proposal(log)
    prepared = _prepare(
        log,
        proposal,
        work_order_id=f"fwo-{run_id_suffix}",
        result_id=f"pfr-{run_id_suffix}",
    )
    log.commit_prepared(prepared)
    return log, prepared


def test_committed_distributed_objects_and_explicit_pins_have_explainable_paths():
    log, prepared = _committed_log("reachability")
    distributed = DistributedLayout(log.layout)
    work_key = distributed.work_order_key(prepared.commit.distributed_work_order_id)
    result_key = distributed.result_key(prepared.commit.prepared_result_id)
    log.backend.put_immutable(work_key, b"{}")
    log.backend.put_immutable(result_key, b"{}")
    pinned_metadata = log.backend.put_immutable(
        distributed.attempt_key("attempt-pinned"), b"pinned evidence"
    )
    pin = LifecyclePinV1.create(
        {
            "kind": "response_loss",
            "owner_id": "committer-session",
            "reason": "CAS response remains ambiguous",
            "object_refs": [pinned_metadata.to_ref().to_dict()],
        }
    )
    publish_pin(log.backend, log.layout, pin)

    report = build_reachability(log)

    assert work_key in report.reachable
    assert result_key in report.reachable
    assert pinned_metadata.key in report.reachable
    path = report.explain(pinned_metadata.key)
    assert path and path[-1].reason == "pin_ref:response_loss"
    reasons = dict(report.retention_reasons)
    assert "committed_work_order" in reasons[work_key]
    assert "committed_prepared_result" in reasons[result_key]


def test_only_known_grace_elapsed_unreachable_objects_become_candidates():
    log, _prepared = _committed_log("candidate")
    distributed = DistributedLayout(log.layout)
    orphan = log.backend.put_immutable(
        distributed.attempt_key("attempt-old-orphan"), b"old orphan"
    )
    unknown = log.backend.put_immutable(
        f"{log.layout.immutable_prefix}future-schema/object.bin", b"unknown"
    )

    report = build_reachability(
        log, grace_eligible_keys={orphan.key, unknown.key}
    )

    assert orphan.key in report.candidates
    assert unknown.key not in report.candidates
    assert unknown.key in report.protected_unknown


def test_no_longer_needs_ack_is_audit_evidence_but_does_not_root_subject_object():
    log, _prepared = _committed_log("ack-release")
    distributed = DistributedLayout(log.layout)
    released = log.backend.put_immutable(
        distributed.attempt_key("attempt-released"), b"released"
    )
    head = log.replay(force_full=True).head_frontier
    acknowledgement = LifecycleAcknowledgementV1.create(
        {
            "role": "executor",
            "subject_id": "executor-0",
            "session_id": "executor-session-0",
            "kind": "no_longer_needs",
            "commit_seq": head.commit_seq,
            "commit_id": head.commit_id,
            "object_refs": [released.to_ref().to_dict()],
        }
    )
    acknowledgement_metadata = publish_acknowledgement(
        log.backend, log.layout, acknowledgement
    )

    report = build_reachability(log, grace_eligible_keys={released.key})

    assert acknowledgement_metadata.key in report.reachable
    assert released.key in report.candidates


def test_capsuled_ack_roots_every_bound_object_ref():
    log, _prepared = _committed_log("ack-capsule")
    distributed = DistributedLayout(log.layout)
    component = log.backend.put_immutable(
        distributed.attempt_key("capsule-component"), b"capsule state"
    )
    head = log.replay(force_full=True).head_frontier
    acknowledgement = LifecycleAcknowledgementV1.create(
        {
            "role": "learner",
            "subject_id": "learner-0",
            "session_id": "learner-session-0",
            "kind": "capsuled",
            "commit_seq": head.commit_seq,
            "commit_id": head.commit_id,
            "object_refs": [component.to_ref().to_dict()],
        }
    )
    publish_acknowledgement(log.backend, log.layout, acknowledgement)

    report = build_reachability(log, grace_eligible_keys={component.key})

    assert component.key in report.reachable
    assert component.key not in report.candidates
