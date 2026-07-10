"""Deterministic replayable faults for any semantic storage backend."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import errno
import hashlib
import json
import random
from typing import Iterable

from .base import BytesLike, DeleteTarget, ObjectMetadata, OperationRecord, StorageBackend
from .errors import InjectedTimeout, IntegrityError, StorageIOError


_FAULT_KINDS = {
    "timeout",
    "eio",
    "short_read",
    "corrupt_read",
    "omit_list",
}


@dataclass(frozen=True)
class FaultEvent:
    operation: str
    timing: str
    occurrence: int
    kind: str

    def __post_init__(self) -> None:
        if not self.operation:
            raise ValueError("fault operation must be non-empty")
        if self.timing not in {"before", "after"}:
            raise ValueError("fault timing must be before or after")
        if type(self.occurrence) is not int or self.occurrence < 1:
            raise ValueError("fault occurrence must be a positive integer")
        if self.kind not in _FAULT_KINDS:
            raise ValueError(f"unsupported fault kind: {self.kind}")
        if self.kind in {"short_read", "corrupt_read", "omit_list"} and self.timing != "after":
            raise ValueError(f"{self.kind} is an after-effect observation fault")


@dataclass(frozen=True)
class FaultSchedule:
    seed: int
    events: tuple[FaultEvent, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "events", tuple(self.events))
        identities = [(event.operation, event.timing, event.occurrence) for event in self.events]
        if len(identities) != len(set(identities)):
            raise ValueError("fault schedule has duplicate operation/timing/occurrence entries")

    @classmethod
    def seeded(
        cls,
        seed: int,
        *,
        operations: Iterable[str],
        probability: float = 0.25,
    ) -> "FaultSchedule":
        if not 0.0 <= probability <= 1.0:
            raise ValueError("probability must be in [0, 1]")
        rng = random.Random(seed)
        events: list[FaultEvent] = []
        for operation in sorted(set(operations)):
            if rng.random() >= probability:
                continue
            timing = rng.choice(("before", "after"))
            allowed = ["timeout", "eio"]
            if timing == "after" and operation in {"get", "range_get"}:
                allowed += ["short_read", "corrupt_read"]
            if timing == "after" and operation == "list_prefix":
                allowed.append("omit_list")
            events.append(FaultEvent(operation, timing, 1, rng.choice(allowed)))
        return cls(seed, tuple(events))

    def to_dict(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "events": [asdict(event) for event in self.events],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, payload: str) -> "FaultSchedule":
        decoded = json.loads(payload)
        if not isinstance(decoded, dict) or set(decoded) != {"seed", "events"}:
            raise ValueError("invalid fault schedule")
        if type(decoded["seed"]) is not int or not isinstance(decoded["events"], list):
            raise ValueError("invalid fault schedule types")
        events = tuple(FaultEvent(**event) for event in decoded["events"])
        return cls(decoded["seed"], events)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()


class FaultInjectingBackend:
    def __init__(self, backend: StorageBackend, schedule: FaultSchedule) -> None:
        self.backend = backend
        self.schedule = schedule
        self._occurrences: dict[tuple[str, str], int] = {}
        self._observed: list[dict[str, object]] = []

    @property
    def capabilities(self):
        return self.backend.capabilities

    @property
    def history(self) -> tuple[OperationRecord, ...]:
        return self.backend.history

    @property
    def fault_history(self) -> tuple[dict[str, object], ...]:
        return tuple(dict(item) for item in self._observed)

    def _event(self, operation: str, timing: str) -> FaultEvent | None:
        identity = (operation, timing)
        occurrence = self._occurrences.get(identity, 0) + 1
        self._occurrences[identity] = occurrence
        for event in self.schedule.events:
            if (
                event.operation == operation
                and event.timing == timing
                and event.occurrence == occurrence
            ):
                self._observed.append(
                    {
                        "operation": operation,
                        "timing": timing,
                        "occurrence": occurrence,
                        "kind": event.kind,
                    }
                )
                return event
        return None

    @staticmethod
    def _raise(event: FaultEvent, operation: str, key: str) -> None:
        if event.kind == "timeout":
            raise InjectedTimeout(operation, event.timing)
        if event.kind == "eio":
            raise StorageIOError(
                f"injected EIO for {operation}",
                operation=operation,
                key=key,
                errno=errno.EIO,
                retryable=True,
            )
        if event.kind in {"short_read", "corrupt_read"}:
            raise IntegrityError(
                f"detected injected {event.kind} for {key}",
                operation=operation,
                key=key,
            )

    def _before(self, operation: str, key: str) -> None:
        event = self._event(operation, "before")
        if event is not None:
            self._raise(event, operation, key)

    def _after(self, operation: str, key: str) -> FaultEvent | None:
        event = self._event(operation, "after")
        if event is not None and event.kind != "omit_list":
            self._raise(event, operation, key)
        return event

    def put_immutable(
        self,
        key: str,
        data: BytesLike,
        *,
        sha256: str | None = None,
    ) -> ObjectMetadata:
        operation = "put_immutable"
        self._before(operation, key)
        result = self.backend.put_immutable(key, data, sha256=sha256)
        self._after(operation, key)
        return result

    def put_if_absent(self, key: str, data: BytesLike) -> ObjectMetadata:
        operation = "put_if_absent"
        self._before(operation, key)
        result = self.backend.put_if_absent(key, data)
        self._after(operation, key)
        return result

    create_if_absent = put_if_absent

    def conditional_replace(
        self,
        key: str,
        *,
        expected_version: str,
        data: BytesLike,
    ) -> ObjectMetadata:
        operation = "conditional_replace"
        self._before(operation, key)
        result = self.backend.conditional_replace(
            key,
            expected_version=expected_version,
            data=data,
        )
        self._after(operation, key)
        return result

    compare_and_swap = conditional_replace

    def get(self, key: str, *, expected_version: str | None = None) -> bytes:
        operation = "get"
        self._before(operation, key)
        result = self.backend.get(key, expected_version=expected_version)
        self._after(operation, key)
        return result

    def head(self, key: str) -> ObjectMetadata:
        operation = "head"
        self._before(operation, key)
        result = self.backend.head(key)
        self._after(operation, key)
        return result

    def range_get(self, key: str, start: int, end: int | None = None) -> bytes:
        operation = "range_get"
        self._before(operation, key)
        result = self.backend.range_get(key, start, end)
        self._after(operation, key)
        return result

    def delete_batch(self, keys: Iterable[DeleteTarget]) -> dict[str, str]:
        operation = "delete_batch"
        targets = tuple(keys)
        self._before(operation, "<batch>")
        result = self.backend.delete_batch(targets)
        self._after(operation, "<batch>")
        return result

    def list_prefix(self, prefix: str) -> tuple[str, ...]:
        operation = "list_prefix"
        self._before(operation, prefix)
        result = self.backend.list_prefix(prefix)
        event = self._after(operation, prefix)
        return () if event is not None and event.kind == "omit_list" else result

