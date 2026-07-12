"""Strict observational event schema for reconstructing P08 critical paths."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any, Mapping


SCHEMA = "duraloco-stage-event-v1"
OUTCOMES = {"pass", "fail", "cancelled", "inconclusive"}


def _nonempty(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _optional_nonempty(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _nonempty(value, field_name)


def _counter_map(value: Mapping[str, int] | None) -> tuple[tuple[str, int], ...]:
    result: list[tuple[str, int]] = []
    for key, raw in sorted((value or {}).items()):
        if not isinstance(key, str) or not key:
            raise ValueError("counter name must be non-empty")
        if type(raw) is not int or raw < 0:
            raise ValueError(f"counter {key} must be a non-negative integer")
        result.append((key, raw))
    return tuple(result)


@dataclass(frozen=True)
class StageEventV1:
    run_id: str
    run_generation: int
    role: str
    role_session_id: str
    stage: str
    outcome: str
    monotonic_start_ns: int
    monotonic_end_ns: int
    observed_at_utc_ns: int
    event_id: str
    commit_seq: int | None = None
    transition_id: str | None = None
    work_order_id: str | None = None
    attempt_id: str | None = None
    proposal_id: str | None = None
    head_commit_id: str | None = None
    fencing_epoch: int | None = None
    membership_revision: int | None = None
    parent_event_id: str | None = None
    counters: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    attributes: tuple[tuple[str, object], ...] = field(default_factory=tuple)

    @classmethod
    def create(cls, payload: Mapping[str, Any]) -> "StageEventV1":
        body = dict(payload)
        body.pop("event_id", None)
        body["schema"] = SCHEMA
        event_id = event_identity(body)
        return cls.from_dict({**body, "event_id": event_id})

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StageEventV1":
        required = {
            "schema",
            "run_id",
            "run_generation",
            "role",
            "role_session_id",
            "stage",
            "outcome",
            "monotonic_start_ns",
            "monotonic_end_ns",
            "observed_at_utc_ns",
            "event_id",
            "counters",
            "attributes",
        }
        optional = {
            "commit_seq",
            "transition_id",
            "work_order_id",
            "attempt_id",
            "proposal_id",
            "head_commit_id",
            "fencing_epoch",
            "membership_revision",
            "parent_event_id",
        }
        if not isinstance(payload, Mapping) or not required <= set(payload) or (
            set(payload) - required - optional
        ):
            raise ValueError("stage event fields differ from contract")
        if payload["schema"] != SCHEMA:
            raise ValueError("unsupported stage event schema")
        for field_name in (
            "run_generation",
            "monotonic_start_ns",
            "monotonic_end_ns",
            "observed_at_utc_ns",
        ):
            value = payload[field_name]
            if type(value) is not int or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if payload["monotonic_end_ns"] < payload["monotonic_start_ns"]:
            raise ValueError("stage event ends before it starts")
        for field_name in (
            "commit_seq",
            "fencing_epoch",
            "membership_revision",
        ):
            value = payload.get(field_name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{field_name} must be a non-negative integer")
        outcome = _nonempty(payload["outcome"], "outcome")
        if outcome not in OUTCOMES:
            raise ValueError("unsupported stage event outcome")
        raw_counters = payload["counters"]
        if not isinstance(raw_counters, Mapping):
            raise ValueError("stage event counters must be a mapping")
        raw_attributes = payload["attributes"]
        if not isinstance(raw_attributes, Mapping):
            raise ValueError("stage event attributes must be a mapping")
        attributes = tuple(sorted(raw_attributes.items()))
        for key, value in attributes:
            if not isinstance(key, str) or not key:
                raise ValueError("attribute name must be non-empty")
            if not isinstance(value, (str, int, float, bool, type(None), list, dict)):
                raise ValueError(f"unsupported telemetry attribute type: {key}")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"telemetry attribute is non-finite: {key}")
        instance = cls(
            run_id=_nonempty(payload["run_id"], "run_id"),
            run_generation=payload["run_generation"],
            role=_nonempty(payload["role"], "role"),
            role_session_id=_nonempty(payload["role_session_id"], "role_session_id"),
            stage=_nonempty(payload["stage"], "stage"),
            outcome=outcome,
            monotonic_start_ns=payload["monotonic_start_ns"],
            monotonic_end_ns=payload["monotonic_end_ns"],
            observed_at_utc_ns=payload["observed_at_utc_ns"],
            event_id=_nonempty(payload["event_id"], "event_id"),
            commit_seq=payload.get("commit_seq"),
            transition_id=_optional_nonempty(payload.get("transition_id"), "transition_id"),
            work_order_id=_optional_nonempty(payload.get("work_order_id"), "work_order_id"),
            attempt_id=_optional_nonempty(payload.get("attempt_id"), "attempt_id"),
            proposal_id=_optional_nonempty(payload.get("proposal_id"), "proposal_id"),
            head_commit_id=_optional_nonempty(payload.get("head_commit_id"), "head_commit_id"),
            fencing_epoch=payload.get("fencing_epoch"),
            membership_revision=payload.get("membership_revision"),
            parent_event_id=_optional_nonempty(payload.get("parent_event_id"), "parent_event_id"),
            counters=_counter_map(raw_counters),
            attributes=attributes,
        )
        body = instance.to_dict()
        supplied = body.pop("event_id")
        if supplied != event_identity(body):
            raise ValueError("stage event identity differs")
        return instance

    @property
    def duration_ns(self) -> int:
        return self.monotonic_end_ns - self.monotonic_start_ns

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema": SCHEMA,
            "run_id": self.run_id,
            "run_generation": self.run_generation,
            "role": self.role,
            "role_session_id": self.role_session_id,
            "stage": self.stage,
            "outcome": self.outcome,
            "monotonic_start_ns": self.monotonic_start_ns,
            "monotonic_end_ns": self.monotonic_end_ns,
            "observed_at_utc_ns": self.observed_at_utc_ns,
            "event_id": self.event_id,
            "counters": dict(self.counters),
            "attributes": dict(self.attributes),
        }
        for field_name in (
            "commit_seq",
            "transition_id",
            "work_order_id",
            "attempt_id",
            "proposal_id",
            "head_commit_id",
            "fencing_epoch",
            "membership_revision",
            "parent_event_id",
        ):
            value = getattr(self, field_name)
            if value is not None:
                payload[field_name] = value
        return payload


def event_identity(payload: Mapping[str, object]) -> str:
    body = dict(payload)
    body.pop("event_id", None)
    encoded = json.dumps(
        body,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "stage-" + hashlib.sha256(encoded).hexdigest()
