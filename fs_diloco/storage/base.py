"""Semantic storage API shared by memory, POSIX, and future object backends."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Protocol, runtime_checkable

from fs_diloco.protocol.schemas import ObjectRef


BytesLike = bytes | bytearray | memoryview
DeleteTarget = str | ObjectRef


@dataclass(frozen=True)
class ObjectMetadata:
    key: str
    size: int
    sha256: str
    version: str

    def to_ref(self) -> ObjectRef:
        return ObjectRef(
            key=self.key,
            size=self.size,
            sha256=self.sha256,
            version=self.version,
        )


@dataclass(frozen=True)
class OperationRecord:
    sequence: int
    operation: str
    key: str
    outcome: str
    version: str | None


@dataclass(frozen=True)
class StorageCapabilities:
    backend: str
    immutable_create: bool
    conditional_replace: bool
    verified_reads: bool
    range_reads: bool
    batch_delete: bool
    listing: bool
    atomic_replace: bool
    advisory_lock: bool
    directory_fsync: bool

    def to_dict(self) -> dict[str, bool | str]:
        return asdict(self)


@runtime_checkable
class StorageBackend(Protocol):
    @property
    def capabilities(self) -> StorageCapabilities: ...

    @property
    def history(self) -> tuple[OperationRecord, ...]: ...

    def put_immutable(
        self,
        key: str,
        data: BytesLike,
        *,
        sha256: str | None = None,
    ) -> ObjectMetadata: ...

    def put_if_absent(self, key: str, data: BytesLike) -> ObjectMetadata: ...

    def conditional_replace(
        self,
        key: str,
        *,
        expected_version: str,
        data: BytesLike,
        request_id: str | None = None,
    ) -> ObjectMetadata: ...

    def get(self, key: str, *, expected_version: str | None = None) -> bytes: ...

    def head(self, key: str) -> ObjectMetadata: ...

    def range_get(self, key: str, start: int, end: int | None = None) -> bytes: ...

    def delete_batch(self, keys: Iterable[DeleteTarget]) -> dict[str, str]: ...

    def list_prefix(self, prefix: str) -> tuple[str, ...]: ...
