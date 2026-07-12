"""Deterministic in-memory semantic storage backend for the reference model."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from .base import BytesLike, DeleteTarget, ObjectMetadata, OperationRecord, StorageCapabilities
from .errors import InjectedTimeout, ImmutableConflict, NotFound, PreconditionFailed
from .layout import normalize_key, normalize_prefix, normalize_request_id


@dataclass
class FailureRule:
    operation: str
    timing: str
    occurrence: int = 1
    remaining: int = 1

    def __post_init__(self) -> None:
        if self.timing not in {"before", "after"}:
            raise ValueError("failure timing must be before or after")
        if self.occurrence < 1 or self.remaining < 1:
            raise ValueError("occurrence and remaining must be positive")


@dataclass(frozen=True)
class _StoredObject:
    data: bytes
    metadata: ObjectMetadata
    previous_version: str | None
    request_id: str | None


class InMemoryStorageBackend:
    """A backend whose observable semantics are independent of listing order."""

    def __init__(self) -> None:
        self._objects: dict[str, _StoredObject] = {}
        self._version_counter = 0
        self._operation_counter = 0
        self._operation_occurrences: dict[str, int] = {}
        self._failures: list[FailureRule] = []
        self._history: list[OperationRecord] = []

    @property
    def history(self) -> tuple[OperationRecord, ...]:
        return tuple(self._history)

    @property
    def capabilities(self) -> StorageCapabilities:
        return StorageCapabilities(
            backend="memory",
            immutable_create=True,
            conditional_replace=True,
            verified_reads=True,
            range_reads=True,
            batch_delete=True,
            listing=True,
            atomic_replace=True,
            advisory_lock=False,
            cross_node_advisory_lock=False,
            advisory_lock_evidence="not_applicable",
            directory_fsync=False,
        )

    def inject_failure(self, rule: FailureRule) -> None:
        self._failures.append(rule)

    def clear_failures(self) -> None:
        self._failures.clear()

    def _next_version(self, data: bytes) -> str:
        self._version_counter += 1
        return f"v{self._version_counter:08d}-{hashlib.sha256(data).hexdigest()[:16]}"

    @staticmethod
    def _snapshot_bytes(data: BytesLike) -> bytes:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("storage payload must be bytes-like")
        return bytes(data)

    def _metadata(self, key: str, data: bytes, version: str) -> ObjectMetadata:
        return ObjectMetadata(key, len(data), hashlib.sha256(data).hexdigest(), version)

    def _record(self, operation: str, key: str, outcome: str, version: str | None) -> None:
        self._operation_counter += 1
        self._history.append(
            OperationRecord(self._operation_counter, operation, key, outcome, version)
        )

    def _maybe_fail(self, operation: str, timing: str, key: str) -> None:
        occurrence_key = f"{operation}:{timing}"
        self._operation_occurrences[occurrence_key] = self._operation_occurrences.get(
            occurrence_key, 0
        ) + 1
        occurrence = self._operation_occurrences[occurrence_key]
        for rule in self._failures:
            if (
                rule.operation == operation
                and rule.timing == timing
                and occurrence >= rule.occurrence
                and rule.remaining > 0
            ):
                rule.remaining -= 1
                self._record(operation, key, f"timeout_{timing}", None)
                raise InjectedTimeout(operation, timing)

    def put_immutable(
        self,
        key: str,
        data: BytesLike,
        *,
        sha256: str | None = None,
    ) -> ObjectMetadata:
        key = normalize_key(key)
        operation = "put_immutable"
        self._maybe_fail(operation, "before", key)
        data = self._snapshot_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        if sha256 is not None and sha256 != digest:
            self._record(operation, key, "caller_digest_mismatch", None)
            raise ImmutableConflict("caller digest does not match immutable bytes")
        existing = self._objects.get(key)
        if existing is not None:
            if existing.data != data:
                self._record(operation, key, "immutable_conflict", existing.metadata.version)
                raise ImmutableConflict(f"immutable key already contains different bytes: {key}")
            metadata = existing.metadata
            self._record(operation, key, "idempotent", metadata.version)
        else:
            version = self._next_version(data)
            metadata = self._metadata(key, data, version)
            self._objects[key] = _StoredObject(data, metadata, None, None)
            self._record(operation, key, "created", version)
        self._maybe_fail(operation, "after", key)
        return metadata

    def put_if_absent(self, key: str, data: BytesLike) -> ObjectMetadata:
        return self.put_immutable(key, data)

    create_if_absent = put_if_absent

    def conditional_replace(
        self,
        key: str,
        *,
        expected_version: str,
        data: BytesLike,
        request_id: str | None = None,
    ) -> ObjectMetadata:
        key = normalize_key(key)
        request_id = normalize_request_id(request_id)
        operation = "conditional_replace"
        self._maybe_fail(operation, "before", key)
        data = self._snapshot_bytes(data)
        existing = self._objects.get(key)
        if existing is None:
            self._record(operation, key, "missing", None)
            raise NotFound(key)
        if existing.metadata.version != expected_version:
            # A retry after an after-effect timeout is idempotent when it sends
            # the exact same bytes and old version token.
            if (
                request_id is not None
                and existing.previous_version == expected_version
                and existing.request_id == request_id
                and existing.data == data
            ):
                self._record(operation, key, "idempotent_after_effect", existing.metadata.version)
                self._maybe_fail(operation, "after", key)
                return existing.metadata
            self._record(operation, key, "precondition_failed", existing.metadata.version)
            raise PreconditionFailed(
                f"current version {existing.metadata.version} != expected {expected_version}"
            )
        version = self._next_version(data)
        metadata = self._metadata(key, data, version)
        self._objects[key] = _StoredObject(data, metadata, expected_version, request_id)
        self._record(operation, key, "replaced", version)
        self._maybe_fail(operation, "after", key)
        return metadata

    compare_and_swap = conditional_replace

    def get(self, key: str, *, expected_version: str | None = None) -> bytes:
        key = normalize_key(key)
        operation = "get"
        self._maybe_fail(operation, "before", key)
        existing = self._objects.get(key)
        if existing is None:
            self._record(operation, key, "missing", None)
            raise NotFound(key)
        if expected_version is not None and existing.metadata.version != expected_version:
            self._record(operation, key, "version_mismatch", existing.metadata.version)
            raise PreconditionFailed("get expected_version mismatch")
        self._record(operation, key, "read", existing.metadata.version)
        self._maybe_fail(operation, "after", key)
        return bytes(existing.data)

    def head(self, key: str) -> ObjectMetadata:
        key = normalize_key(key)
        operation = "head"
        self._maybe_fail(operation, "before", key)
        existing = self._objects.get(key)
        if existing is None:
            self._record(operation, key, "missing", None)
            raise NotFound(key)
        self._record(operation, key, "read", existing.metadata.version)
        self._maybe_fail(operation, "after", key)
        return existing.metadata

    def range_get(self, key: str, start: int, end: int | None = None) -> bytes:
        key = normalize_key(key)
        if type(start) is not int or start < 0:
            raise ValueError("range start must be a non-negative integer")
        if end is not None and (type(end) is not int or end < start):
            raise ValueError("range end must be an integer >= start")
        return self.get(key)[start:end]

    def delete_batch(self, keys: Iterable[DeleteTarget]) -> dict[str, str]:
        results: dict[str, str] = {}
        for target in keys:
            key = normalize_key(target if isinstance(target, str) else target.key)
            operation = "delete"
            self._maybe_fail(operation, "before", key)
            existing = self._objects.get(key)
            if existing is not None and not isinstance(target, str) and (
                target.version not in {None, existing.metadata.version}
                or target.size != existing.metadata.size
                or target.sha256 != existing.metadata.sha256
            ):
                results[key] = "precondition_failed"
                self._record(operation, key, "precondition_failed", existing.metadata.version)
                self._maybe_fail(operation, "after", key)
                continue
            existing = self._objects.pop(key, None)
            outcome = "deleted" if existing is not None else "missing"
            version = existing.metadata.version if existing is not None else None
            results[key] = outcome
            self._record(operation, key, outcome, version)
            self._maybe_fail(operation, "after", key)
        return results

    def list_prefix(self, prefix: str) -> tuple[str, ...]:
        prefix = normalize_prefix(prefix)
        # Sorted output is convenient for tests, but protocol correctness never
        # consumes this method.
        return tuple(sorted(key for key in self._objects if key.startswith(prefix)))

    def object_count(self) -> int:
        return len(self._objects)
