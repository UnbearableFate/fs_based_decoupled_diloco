"""Bounded, owner/head-scoped prefetch that is always disposable."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from typing import Callable

from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.protocol.schemas import ObjectRef


@dataclass(frozen=True)
class PlanningScope:
    head_commit_id: str
    fencing_epoch: int
    membership_revision: int
    owner_session_id: str

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "head_commit_id": self.head_commit_id,
                "fencing_epoch": self.fencing_epoch,
                "membership_revision": self.membership_revision,
                "owner_session_id": self.owner_session_id,
            }
        )


class PrefetchCancelled(RuntimeError):
    pass


class BoundedPrefetch:
    def __init__(self, *, scope: PlanningScope, max_workers: int, max_bytes: int) -> None:
        if max_workers < 1 or max_bytes < 1:
            raise ValueError("prefetch bounds must be positive")
        self.scope = scope
        self.max_bytes = max_bytes
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="prefetch")
        self._lock = Lock()
        self._inflight_bytes = 0
        self._futures: set[Future[bytes]] = set()
        self._cancelled = False

    def _require_scope(self, scope: PlanningScope) -> None:
        if self._cancelled or scope != self.scope:
            raise PrefetchCancelled("prefetch scope is stale")

    def submit(
        self,
        ref: ObjectRef,
        *,
        scope: PlanningScope,
        load: Callable[[ObjectRef], bytes],
    ) -> Future[bytes]:
        with self._lock:
            self._require_scope(scope)
            if self._inflight_bytes + ref.size > self.max_bytes:
                raise MemoryError("prefetch exceeds its in-flight byte budget")
            self._inflight_bytes += ref.size

        def operation() -> bytes:
            self._require_scope(scope)
            data = load(ref)
            self._require_scope(scope)
            if len(data) != ref.size:
                raise ValueError("prefetched ObjectRef size differs")
            return data

        future = self._pool.submit(operation)
        with self._lock:
            self._futures.add(future)

        def release(done: Future[bytes]) -> None:
            with self._lock:
                self._inflight_bytes -= ref.size
                self._futures.discard(done)

        future.add_done_callback(release)
        return future

    def invalidate(self, observed: PlanningScope) -> bool:
        if observed == self.scope:
            return False
        with self._lock:
            self._cancelled = True
            futures = tuple(self._futures)
        for future in futures:
            future.cancel()
        return True

    def close(self) -> None:
        with self._lock:
            self._cancelled = True
        self._pool.shutdown(wait=True, cancel_futures=True)

    @property
    def inflight_bytes(self) -> int:
        with self._lock:
            return self._inflight_bytes
