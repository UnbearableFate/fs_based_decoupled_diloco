"""Volatile learner-liveness views derived from heartbeat observations."""

from __future__ import annotations

from dataclasses import dataclass
import time
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .atomic_io import safe_read_json
from .constants import (
    FORMAT_VERSION,
    LEARNER_STATUS_ACTIVE,
    LEARNER_STATUS_DEAD,
    LEARNER_STATUS_STOPPED,
    LEARNER_STATUS_STALE,
    learner_id_from_index,
)


@dataclass(frozen=True)
class LivenessView:
    learners: Mapping[str, Mapping[str, Any]]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "learners",
            MappingProxyType(
                {key: MappingProxyType(dict(value)) for key, value in self.learners.items()}
            ),
        )


def valid_learner_ids(num_learners: int) -> set[str]:
    return {learner_id_from_index(i) for i in range(num_learners)}


def validate_heartbeat(
    payload: dict[str, Any],
    *,
    run_id: str,
    run_generation: int,
    num_learners: int,
) -> tuple[bool, str | None]:
    if payload.get("format_version") != FORMAT_VERSION:
        return False, "format_version"
    if payload.get("run_id") != run_id:
        return False, "run_id"
    if payload.get("run_generation") != run_generation:
        return False, "run_generation"
    if payload.get("learner_id") not in valid_learner_ids(num_learners):
        return False, "learner_id"
    if not isinstance(payload.get("timestamp"), (int, float)):
        return False, "timestamp"
    return True, None


def classify_liveness(
    *,
    now: float,
    last_seen: float | None,
    current_status: str,
    stale_after_seconds: float,
    dead_after_seconds: float,
) -> tuple[str, str | None]:
    if current_status == LEARNER_STATUS_STOPPED:
        return LEARNER_STATUS_STOPPED, "stopped"
    if last_seen is None:
        return LEARNER_STATUS_DEAD, "never_seen"
    age = now - last_seen
    if age <= stale_after_seconds:
        return LEARNER_STATUS_ACTIVE, None
    if age <= dead_after_seconds:
        return LEARNER_STATUS_STALE, f"heartbeat_age={age:.1f}s"
    return LEARNER_STATUS_DEAD, f"heartbeat_age={age:.1f}s"


def build_liveness_view(
    heartbeat_dir: str | Path,
    *,
    run_id: str,
    run_generation: int,
    num_learners: int,
    stale_after_seconds: float,
    dead_after_seconds: float,
    now: float | None = None,
) -> LivenessView:
    observed_at = time.time() if now is None else now
    learners: dict[str, dict[str, Any]] = {}
    for path in sorted(Path(heartbeat_dir).glob("learner_*.json")):
        payload = safe_read_json(path)
        if not isinstance(payload, dict):
            continue
        valid, _ = validate_heartbeat(
            payload,
            run_id=run_id,
            run_generation=run_generation,
            num_learners=num_learners,
        )
        if not valid:
            continue
        status, reason = classify_liveness(
            now=observed_at,
            last_seen=float(payload["timestamp"]),
            current_status=str(payload.get("status") or LEARNER_STATUS_ACTIVE),
            stale_after_seconds=stale_after_seconds,
            dead_after_seconds=dead_after_seconds,
        )
        learners[str(payload["learner_id"])] = {
            **payload,
            "status": status,
            "status_reason": reason,
            "heartbeat_path": str(path),
        }
    return LivenessView(learners)


def liveness_counts(view: LivenessView) -> dict[str, int]:
    counts = {
        LEARNER_STATUS_ACTIVE: 0,
        LEARNER_STATUS_STALE: 0,
        LEARNER_STATUS_DEAD: 0,
        LEARNER_STATUS_STOPPED: 0,
    }
    for learner in view.learners.values():
        status = str(learner["status"])
        counts[status] = counts.get(status, 0) + 1
    return counts


def no_progress_timed_out(
    last_progress_time: float,
    timeout_seconds: float,
    now: float | None = None,
) -> bool:
    observed_at = time.time() if now is None else now
    return observed_at - last_progress_time > timeout_seconds
