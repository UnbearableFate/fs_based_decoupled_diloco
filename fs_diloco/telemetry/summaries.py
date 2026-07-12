"""Fail-closed reducers for P08 stage-event evidence."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from typing import Iterable

from .events import StageEventV1


class TelemetryContractError(ValueError):
    pass


COMMITTER_REQUIRED = {
    "catalog_discovery",
    "proposal_validation",
    "work_order_publication",
    "prepared_visibility",
    "winner_validation",
    "successor_publication",
    "head_cas",
    "materialization",
}
EXECUTOR_REQUIRED = {
    "executor_input_read",
    "streaming_reduction",
    "outer_step",
    "prepared_publication",
}


def load_events(paths: Iterable[str | Path]) -> tuple[StageEventV1, ...]:
    events: list[StageEventV1] = []
    for raw in paths:
        path = Path(raw)
        if not path.is_file():
            raise TelemetryContractError(f"telemetry file is missing: {path}")
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                payload = json.loads(line)
                events.append(StageEventV1.from_dict(payload))
            except Exception as exc:
                raise TelemetryContractError(
                    f"invalid telemetry at {path}:{line_number}: {exc}"
                ) from exc
    identities = [event.event_id for event in events]
    if len(identities) != len(set(identities)):
        raise TelemetryContractError("duplicate stage event identity")
    return tuple(events)


def summarize_events(
    events: Iterable[StageEventV1],
    *,
    recorder_health: Iterable[dict[str, object]] = (),
) -> dict[str, object]:
    materialized = tuple(events)
    health = tuple(recorder_health)
    if any(item.get("complete") is not True for item in health):
        raise TelemetryContractError("telemetry recorder health is incomplete")
    by_work: dict[str, list[StageEventV1]] = defaultdict(list)
    for event in materialized:
        if event.work_order_id is not None:
            by_work[event.work_order_id].append(event)
    if not by_work:
        raise TelemetryContractError("no work-order telemetry was observed")
    timelines: list[dict[str, object]] = []
    for work_order_id, items in sorted(by_work.items()):
        stages = {item.stage for item in items if item.outcome == "pass"}
        missing = sorted((COMMITTER_REQUIRED | EXECUTOR_REQUIRED) - stages)
        if missing:
            raise TelemetryContractError(
                f"work order {work_order_id} is missing stages: {missing}"
            )
        attempts = sorted({item.attempt_id for item in items if item.attempt_id})
        if not attempts:
            raise TelemetryContractError(f"work order {work_order_id} has no attempt lineage")
        roles = sorted({item.role for item in items})
        timeline_events = sorted(
            items,
            key=lambda item: (
                item.role,
                item.role_session_id,
                item.monotonic_start_ns,
                item.event_id,
            ),
        )
        timelines.append(
            {
                "work_order_id": work_order_id,
                "roles": roles,
                "attempt_ids": attempts,
                "stages": sorted(stages),
                "events": [item.to_dict() for item in timeline_events],
                "duration_by_role_ns": {
                    role: sum(item.duration_ns for item in items if item.role == role)
                    for role in roles
                },
            }
        )
    return {
        "schema": "duraloco-stage-summary-v1",
        "status": "PASS",
        "event_count": len(materialized),
        "work_order_count": len(timelines),
        "timelines": timelines,
        "clock_claim": "causal-local-monotonic-spans-only",
    }
