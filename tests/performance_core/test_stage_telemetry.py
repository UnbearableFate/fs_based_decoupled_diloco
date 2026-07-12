from __future__ import annotations

import time

import pytest

from fs_diloco.telemetry import (
    StageEventV1,
    StageRecorder,
    TelemetryContractError,
    summarize_events,
)
from fs_diloco.telemetry.summaries import COMMITTER_REQUIRED, EXECUTOR_REQUIRED, load_events


def _event(stage: str, role: str, *, index: int) -> StageEventV1:
    now = 1000 + index * 10
    return StageEventV1.create(
        {
            "run_id": "telemetry-run",
            "run_generation": 0,
            "role": role,
            "role_session_id": f"{role}-session",
            "stage": stage,
            "outcome": "pass",
            "monotonic_start_ns": now,
            "monotonic_end_ns": now + 5,
            "observed_at_utc_ns": 1_000_000 + now,
            "work_order_id": "fwo-test",
            "attempt_id": "attempt-test" if role == "executor" else None,
            "transition_id": "commit-test" if stage == "head_cas" else None,
            "head_commit_id": "parent",
            "fencing_epoch": 1,
            "membership_revision": 0,
            "counters": {"bytes": index},
            "attributes": {"fixture": True},
        }
    )


def test_event_identity_and_local_monotonic_contract_are_strict():
    event = _event("head_cas", "committer", index=1)
    assert StageEventV1.from_dict(event.to_dict()) == event
    changed = event.to_dict()
    changed["stage"] = "other"
    with pytest.raises(ValueError, match="identity"):
        StageEventV1.from_dict(changed)
    reversed_time = event.to_dict()
    reversed_time["monotonic_end_ns"] = reversed_time["monotonic_start_ns"] - 1
    with pytest.raises(ValueError, match="ends before"):
        StageEventV1.create(reversed_time)


def test_recorder_failure_never_raises_into_authority_path(tmp_path):
    recorder = StageRecorder(
        tmp_path,
        run_id="telemetry-run",
        run_generation=0,
        role="committer",
        role_session_id="session",
    )
    time.sleep(0.05)
    recorder.record("head_cas", start_ns=time.monotonic_ns())
    health = recorder.close()
    assert not health.complete
    assert health.writer_errors >= 1 or health.dropped_events >= 1


def test_summary_reconstructs_complete_committer_and_executor_timeline(tmp_path):
    events = []
    index = 0
    for stage in sorted(COMMITTER_REQUIRED):
        events.append(_event(stage, "committer", index=index))
        index += 1
    for stage in sorted(EXECUTOR_REQUIRED):
        events.append(_event(stage, "executor", index=index))
        index += 1
    path = tmp_path / "events.jsonl"
    path.write_text("".join(f"{event.to_dict()}\n" for event in ()), encoding="utf-8")
    # Exercise the actual JSON reader separately from direct reduction.
    import json

    path.write_text(
        "".join(json.dumps(event.to_dict(), sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )
    loaded = load_events([path])
    report = summarize_events(
        loaded,
        recorder_health=[
            {
                "accepted_events": len(events),
                "written_events": len(events),
                "dropped_events": 0,
                "writer_errors": 0,
                "complete": True,
            }
        ],
    )
    assert report["status"] == "PASS"
    assert report["work_order_count"] == 1
    assert report["clock_claim"] == "causal-local-monotonic-spans-only"


def test_summary_fails_closed_on_missing_stage_or_recorder_drop():
    events = [_event(stage, "committer", index=index) for index, stage in enumerate(COMMITTER_REQUIRED)]
    with pytest.raises(TelemetryContractError, match="missing stages"):
        summarize_events(events)
    with pytest.raises(TelemetryContractError, match="health"):
        summarize_events(
            [
                *events,
                *(
                    _event(stage, "executor", index=100 + index)
                    for index, stage in enumerate(EXECUTOR_REQUIRED)
                ),
            ],
            recorder_health=[{"complete": False}],
        )


def test_summary_cannot_hide_an_incomplete_loser_attempt():
    events = []
    index = 0
    for stage in sorted(COMMITTER_REQUIRED):
        events.append(_event(stage, "committer", index=index))
        index += 1
    for stage in sorted(EXECUTOR_REQUIRED):
        events.append(_event(stage, "executor", index=index))
        index += 1
    incomplete = _event("executor_input_read", "executor", index=index).to_dict()
    incomplete["attempt_id"] = "attempt-loser"
    events.append(StageEventV1.create(incomplete))
    with pytest.raises(TelemetryContractError, match="incomplete without terminal"):
        summarize_events(events)

    failed = incomplete.copy()
    failed["outcome"] = "fail"
    failed["monotonic_start_ns"] += 1
    failed["monotonic_end_ns"] += 1
    events.append(StageEventV1.create(failed))
    report = summarize_events(events)
    attempts = report["timelines"][0]["attempts"]
    assert {item["attempt_id"]: item["outcome"] for item in attempts} == {
        "attempt-loser": "fail",
        "attempt-test": "pass",
    }
