"""Best-effort asynchronous stage recorder with explicit drop/error accounting."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Lock, Thread
import time
from typing import Iterator, Mapping

from .events import StageEventV1


@dataclass(frozen=True)
class RecorderHealth:
    accepted_events: int
    written_events: int
    dropped_events: int
    writer_errors: int

    @property
    def complete(self) -> bool:
        return self.accepted_events == self.written_events and not (
            self.dropped_events or self.writer_errors
        )

    def to_dict(self) -> dict[str, int | bool]:
        return {
            "accepted_events": self.accepted_events,
            "written_events": self.written_events,
            "dropped_events": self.dropped_events,
            "writer_errors": self.writer_errors,
            "complete": self.complete,
        }


class StageRecorder:
    """Telemetry failures are observable but never change authority execution."""

    _STOP = object()

    def __init__(
        self,
        path: str | Path,
        *,
        run_id: str,
        run_generation: int,
        role: str,
        role_session_id: str,
        max_queue: int = 4096,
        health_path: str | Path | None = None,
    ) -> None:
        if max_queue < 1:
            raise ValueError("telemetry queue must be positive")
        self.path = Path(path)
        self.run_id = run_id
        self.run_generation = run_generation
        self.role = role
        self.role_session_id = role_session_id
        self.health_path = Path(health_path) if health_path is not None else None
        self._queue: Queue[StageEventV1 | object] = Queue(maxsize=max_queue)
        self._lock = Lock()
        self._accepted = 0
        self._written = 0
        self._dropped = 0
        self._errors = 0
        self._closed = False
        self._thread = Thread(target=self._writer, name=f"telemetry-{role}", daemon=True)
        self._thread.start()

    def _writer(self) -> None:
        handle = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = self.path.open("a", encoding="utf-8")
            while True:
                item = self._queue.get()
                try:
                    if item is self._STOP:
                        return
                    if not isinstance(item, StageEventV1):
                        with self._lock:
                            self._errors += 1
                        continue
                    try:
                        handle.write(
                            json.dumps(
                                item.to_dict(),
                                ensure_ascii=False,
                                allow_nan=False,
                                sort_keys=True,
                            )
                            + "\n"
                        )
                        handle.flush()
                        with self._lock:
                            self._written += 1
                    except Exception:
                        with self._lock:
                            self._errors += 1
                finally:
                    self._queue.task_done()
        except Exception:
            with self._lock:
                self._errors += 1
            while True:
                try:
                    item = self._queue.get_nowait()
                except Empty:
                    return
                else:
                    if item is not self._STOP:
                        with self._lock:
                            self._dropped += 1
                    self._queue.task_done()
        finally:
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    with self._lock:
                        self._errors += 1

    def record(
        self,
        stage: str,
        *,
        start_ns: int,
        end_ns: int | None = None,
        outcome: str = "pass",
        counters: Mapping[str, int] | None = None,
        attributes: Mapping[str, object] | None = None,
        **identity: object,
    ) -> StageEventV1:
        event = StageEventV1.create(
            {
                "run_id": self.run_id,
                "run_generation": self.run_generation,
                "role": self.role,
                "role_session_id": self.role_session_id,
                "stage": stage,
                "outcome": outcome,
                "monotonic_start_ns": start_ns,
                "monotonic_end_ns": end_ns if end_ns is not None else time.monotonic_ns(),
                "observed_at_utc_ns": time.time_ns(),
                "counters": dict(counters or {}),
                "attributes": dict(attributes or {}),
                **identity,
            }
        )
        with self._lock:
            if self._closed or not self._thread.is_alive():
                self._dropped += 1
                return event
        try:
            self._queue.put_nowait(event)
        except Full:
            with self._lock:
                self._dropped += 1
        else:
            with self._lock:
                self._accepted += 1
        return event

    @contextmanager
    def span(
        self,
        stage: str,
        *,
        counters: Mapping[str, int] | None = None,
        attributes: Mapping[str, object] | None = None,
        **identity: object,
    ) -> Iterator[None]:
        start = time.monotonic_ns()
        try:
            yield
        except BaseException as exc:
            merged = {**dict(attributes or {}), "error_type": type(exc).__name__}
            self.record(
                stage,
                start_ns=start,
                outcome="fail",
                counters=counters,
                attributes=merged,
                **identity,
            )
            raise
        else:
            self.record(
                stage,
                start_ns=start,
                counters=counters,
                attributes=attributes,
                **identity,
            )

    @property
    def health(self) -> RecorderHealth:
        with self._lock:
            return RecorderHealth(
                accepted_events=self._accepted,
                written_events=self._written,
                dropped_events=self._dropped,
                writer_errors=self._errors,
            )

    def close(self, *, timeout: float = 10.0) -> RecorderHealth:
        with self._lock:
            if self._closed:
                return RecorderHealth(
                    accepted_events=self._accepted,
                    written_events=self._written,
                    dropped_events=self._dropped,
                    writer_errors=self._errors,
                )
            self._closed = True
        try:
            self._queue.put(self._STOP, timeout=max(0.0, timeout))
        except Full:
            with self._lock:
                self._dropped += 1
        self._thread.join(timeout=max(0.0, timeout))
        if self._thread.is_alive():
            with self._lock:
                self._errors += 1
        health = self.health
        if self.health_path is not None:
            try:
                self.health_path.parent.mkdir(parents=True, exist_ok=True)
                self.health_path.write_text(
                    json.dumps(health.to_dict(), sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            except Exception:
                with self._lock:
                    self._errors += 1
                health = self.health
        return health
