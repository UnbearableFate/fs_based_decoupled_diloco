"""Verified POSIX backend with immutable publication and single-key CAS."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import struct
import tempfile
import time
from typing import Callable, Iterable, Iterator

from fs_diloco.protocol.schemas import ObjectRef

from .base import BytesLike, DeleteTarget, ObjectMetadata, OperationRecord, StorageCapabilities
from .errors import (
    CapabilityError,
    ImmutableConflict,
    IntegrityError,
    LockTimeout,
    NotFound,
    PreconditionFailed,
    StorageError,
    StorageIOError,
)
from .layout import (
    RESERVED_ROOT,
    contained_path,
    normalize_key,
    normalize_prefix,
    normalize_request_id,
)


_MAGIC = b"FSDILOCO-STORAGE-V1\n"
_HEADER_LENGTH = struct.Struct(">Q")
_HEADER_DIGEST_BYTES = 32
_MAX_HEADER_BYTES = 64 * 1024


@dataclass(frozen=True)
class _DecodedObject:
    data: bytes
    metadata: ObjectMetadata
    previous_version: str | None
    request_id: str | None


class PosixStorageBackend:
    """Semantic backend rooted at one isolated POSIX namespace.

    Mutations are serialized per logical key using a stable advisory-lock file.
    The visible object is one checksummed envelope, so payload and opaque
    version token change atomically rather than through a sidecar file.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        require_directory_fsync: bool = True,
        lock_timeout_seconds: float = 30.0,
        stage_hook: Callable[[str], None] | None = None,
    ) -> None:
        if lock_timeout_seconds <= 0:
            raise ValueError("lock_timeout_seconds must be positive")
        try:
            self.root = Path(root).expanduser().resolve(strict=False)
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageIOError.from_oserror(exc, operation="initialize_root", key=".") from exc
        if self.root.is_symlink() or not self.root.is_dir():
            raise CapabilityError("POSIX backend root must be a real directory")
        self._lock_root = self.root / RESERVED_ROOT
        try:
            self._lock_root.mkdir(mode=0o700, exist_ok=True)
        except OSError as exc:
            raise StorageIOError.from_oserror(
                exc,
                operation="initialize_lock_root",
                key=RESERVED_ROOT,
            ) from exc
        self._lock_timeout_seconds = float(lock_timeout_seconds)
        self._stage_hook = stage_hook
        self._history: list[OperationRecord] = []
        self._operation_counter = 0
        self._directory_fsync_supported = self._probe_directory_fsync()
        if require_directory_fsync and not self._directory_fsync_supported:
            raise CapabilityError("parent directory fsync is required but unsupported")
        self.require_directory_fsync = require_directory_fsync

    @property
    def history(self) -> tuple[OperationRecord, ...]:
        return tuple(self._history)

    @property
    def capabilities(self) -> StorageCapabilities:
        return StorageCapabilities(
            backend="posix",
            immutable_create=True,
            conditional_replace=True,
            verified_reads=True,
            range_reads=True,
            batch_delete=True,
            listing=True,
            atomic_replace=True,
            advisory_lock=True,
            directory_fsync=self._directory_fsync_supported,
        )

    @staticmethod
    def _snapshot_bytes(data: BytesLike) -> bytes:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("storage payload must be bytes-like")
        return bytes(data)

    def _record(self, operation: str, key: str, outcome: str, version: str | None) -> None:
        self._operation_counter += 1
        self._history.append(
            OperationRecord(self._operation_counter, operation, key, outcome, version)
        )

    def _stage(self, name: str) -> None:
        if self._stage_hook is not None:
            self._stage_hook(name)

    def _probe_directory_fsync(self) -> bool:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        try:
            fd = os.open(self.root, flags)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            if exc.errno in {errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP}:
                return False
            raise StorageIOError.from_oserror(exc, operation="probe_directory_fsync", key=".")
        return True

    def _fsync_directory(self, directory: Path) -> None:
        if not self._directory_fsync_supported:
            if self.require_directory_fsync:
                raise CapabilityError("directory fsync capability was lost")
            return
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        try:
            fd = os.open(directory, flags)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            raise StorageIOError.from_oserror(
                exc,
                operation="fsync_parent",
                key=str(directory.relative_to(self.root)),
            ) from exc

    def _ensure_parent(self, path: Path) -> None:
        relative = path.parent.relative_to(self.root)
        current = self.root
        for part in relative.parts:
            child = current / part
            try:
                if child.exists():
                    if child.is_symlink() or not child.is_dir():
                        raise CapabilityError(
                            f"object parent is not a real directory: {child}"
                        )
                else:
                    child.mkdir(mode=0o755)
                    self._fsync_directory(current)
            except FileExistsError:
                if child.is_symlink() or not child.is_dir():
                    raise CapabilityError(
                        f"object parent raced with non-directory: {child}"
                    )
            except StorageError:
                raise
            except OSError as exc:
                key = path.relative_to(self.root).as_posix()
                raise StorageIOError.from_oserror(
                    exc,
                    operation="ensure_parent",
                    key=key,
                ) from exc
            current = child

    def _lock_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._lock_root / f"{digest}.lock"

    @contextmanager
    def _locked(self, key: str) -> Iterator[None]:
        lock_path = self._lock_path(key)
        try:
            descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        except OSError as exc:
            raise StorageIOError.from_oserror(exc, operation="open_lock", key=key) from exc
        deadline = time.monotonic() + self._lock_timeout_seconds
        acquired = False
        try:
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise LockTimeout(
                            f"timed out acquiring storage lock for {key}",
                            operation="lock",
                            key=key,
                        ) from exc
                    time.sleep(0.01)
                except OSError as exc:
                    raise StorageIOError.from_oserror(
                        exc,
                        operation="acquire_lock",
                        key=key,
                    ) from exc
            yield
        finally:
            try:
                if acquired:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError as exc:
                raise StorageIOError.from_oserror(
                    exc,
                    operation="release_lock",
                    key=key,
                ) from exc
            finally:
                try:
                    os.close(descriptor)
                except OSError as exc:
                    raise StorageIOError.from_oserror(
                        exc,
                        operation="close_lock",
                        key=key,
                    ) from exc

    @staticmethod
    def _new_version() -> str:
        return "pv1-" + secrets.token_hex(16)

    @staticmethod
    def _encode(
        data: bytes,
        *,
        version: str,
        previous_version: str | None,
        request_id: str | None,
    ) -> bytes:
        header = json.dumps(
            {
                "previous_version": previous_version,
                "request_id": request_id,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "version": version,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        return (
            _MAGIC
            + _HEADER_LENGTH.pack(len(header))
            + hashlib.sha256(header).digest()
            + header
            + data
        )

    def _read_path(self, path: Path, key: str) -> _DecodedObject:
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
            with os.fdopen(descriptor, "rb") as handle:
                magic = handle.read(len(_MAGIC))
                raw_length = handle.read(_HEADER_LENGTH.size)
                if magic != _MAGIC or len(raw_length) != _HEADER_LENGTH.size:
                    raise IntegrityError(f"invalid storage envelope prefix: {key}", key=key)
                header_length = _HEADER_LENGTH.unpack(raw_length)[0]
                if header_length < 2 or header_length > _MAX_HEADER_BYTES:
                    raise IntegrityError(f"invalid storage envelope header size: {key}", key=key)
                header_digest = handle.read(_HEADER_DIGEST_BYTES)
                if len(header_digest) != _HEADER_DIGEST_BYTES:
                    raise IntegrityError(f"short storage envelope header digest: {key}", key=key)
                header_bytes = handle.read(header_length)
                if len(header_bytes) != header_length:
                    raise IntegrityError(f"short storage envelope header: {key}", key=key)
                if hashlib.sha256(header_bytes).digest() != header_digest:
                    raise IntegrityError(
                        f"storage envelope header checksum mismatch: {key}",
                        key=key,
                    )
                data = handle.read()
        except FileNotFoundError as exc:
            raise NotFound(key, operation="read", key=key, errno=exc.errno) from exc
        except StorageError:
            raise
        except OSError as exc:
            raise StorageIOError.from_oserror(exc, operation="read", key=key) from exc
        try:
            header = json.loads(header_bytes.decode("ascii"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IntegrityError(f"invalid storage envelope JSON: {key}", key=key) from exc
        if not isinstance(header, dict) or set(header) != {
            "previous_version",
            "request_id",
            "sha256",
            "size",
            "version",
        }:
            raise IntegrityError(f"invalid storage envelope fields: {key}", key=key)
        version = header["version"]
        previous_version = header["previous_version"]
        request_id = header["request_id"]
        size = header["size"]
        digest = header["sha256"]
        if (
            not isinstance(version, str)
            or not version.startswith("pv1-")
            or (previous_version is not None and not isinstance(previous_version, str))
            or (request_id is not None and not isinstance(request_id, str))
            or type(size) is not int
            or size < 0
            or not isinstance(digest, str)
            or len(digest) != 64
        ):
            raise IntegrityError(f"invalid storage envelope metadata: {key}", key=key)
        observed_digest = hashlib.sha256(data).hexdigest()
        if len(data) != size or observed_digest != digest:
            raise IntegrityError(f"storage object size/hash mismatch: {key}", key=key)
        return _DecodedObject(
            data=data,
            metadata=ObjectMetadata(key, size, digest, version),
            previous_version=previous_version,
            request_id=request_id,
        )

    def _read(self, key: str) -> _DecodedObject:
        key = normalize_key(key)
        return self._read_path(contained_path(self.root, key), key)

    def _publish(self, path: Path, envelope: bytes, *, replace: bool) -> None:
        key = str(path.relative_to(self.root))
        try:
            self._ensure_parent(path)
            descriptor, temp_name = tempfile.mkstemp(
                prefix=f".{path.name}.",
                suffix=".duraloco-tmp",
                dir=path.parent,
            )
        except StorageError:
            raise
        except OSError as exc:
            raise StorageIOError.from_oserror(
                exc,
                operation="create_temp",
                key=key,
            ) from exc
        temp_path = Path(temp_name)
        published = False
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(envelope)
                handle.flush()
                self._stage("after_temp_write")
                os.fchmod(handle.fileno(), 0o644)
                os.fsync(handle.fileno())
                self._stage("after_file_fsync")
            self._stage("before_publish")
            if replace:
                os.replace(temp_path, path)
            else:
                os.link(temp_path, path)
                temp_path.unlink()
            published = True
            self._stage("after_publish")
            self._stage("before_parent_fsync")
            self._fsync_directory(path.parent)
            self._stage("after_parent_fsync")
        except OSError as exc:
            raise StorageIOError.from_oserror(
                exc,
                operation="replace" if replace else "create",
                key=key,
            ) from exc
        finally:
            if not published or temp_path.exists():
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def put_immutable(
        self,
        key: str,
        data: BytesLike,
        *,
        sha256: str | None = None,
    ) -> ObjectMetadata:
        operation = "put_immutable"
        key = normalize_key(key)
        data = self._snapshot_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        if sha256 is not None and sha256 != digest:
            self._record(operation, key, "caller_digest_mismatch", None)
            raise ImmutableConflict("caller digest does not match immutable bytes", key=key)
        path = contained_path(self.root, key)
        with self._locked(key):
            try:
                existing = self._read_path(path, key)
            except NotFound:
                existing = None
            if existing is not None:
                if existing.data != data:
                    self._record(operation, key, "immutable_conflict", existing.metadata.version)
                    raise ImmutableConflict(
                        f"immutable key already contains different bytes: {key}",
                        key=key,
                    )
                self._record(operation, key, "idempotent", existing.metadata.version)
                return existing.metadata
            version = self._new_version()
            envelope = self._encode(
                data,
                version=version,
                previous_version=None,
                request_id=None,
            )
            try:
                self._publish(path, envelope, replace=False)
            except StorageIOError as exc:
                if exc.errno == errno.EEXIST:
                    observed = self._read_path(path, key)
                    if observed.data == data:
                        self._record(operation, key, "idempotent_race", observed.metadata.version)
                        return observed.metadata
                    raise ImmutableConflict(
                        f"immutable key raced with different bytes: {key}", key=key
                    ) from exc
                raise
            metadata = ObjectMetadata(key, len(data), digest, version)
            self._record(operation, key, "created", version)
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
        operation = "conditional_replace"
        key = normalize_key(key)
        if not isinstance(expected_version, str) or not expected_version:
            raise ValueError("expected_version must be a non-empty string")
        request_id = normalize_request_id(request_id)
        data = self._snapshot_bytes(data)
        path = contained_path(self.root, key)
        with self._locked(key):
            existing = self._read_path(path, key)
            if existing.metadata.version != expected_version:
                if (
                    request_id is not None
                    and existing.previous_version == expected_version
                    and existing.request_id == request_id
                    and existing.data == data
                ):
                    self._record(
                        operation,
                        key,
                        "idempotent_after_effect",
                        existing.metadata.version,
                    )
                    return existing.metadata
                self._record(operation, key, "precondition_failed", existing.metadata.version)
                raise PreconditionFailed(
                    f"current version {existing.metadata.version} != expected {expected_version}",
                    operation=operation,
                    key=key,
                )
            version = self._new_version()
            envelope = self._encode(
                data,
                version=version,
                previous_version=expected_version,
                request_id=request_id,
            )
            self._publish(path, envelope, replace=True)
            metadata = ObjectMetadata(key, len(data), hashlib.sha256(data).hexdigest(), version)
            self._record(operation, key, "replaced", version)
            return metadata

    compare_and_swap = conditional_replace

    def get(self, key: str, *, expected_version: str | None = None) -> bytes:
        operation = "get"
        key = normalize_key(key)
        decoded = self._read(key)
        if expected_version is not None and decoded.metadata.version != expected_version:
            self._record(operation, key, "version_mismatch", decoded.metadata.version)
            raise PreconditionFailed(
                "get expected_version mismatch",
                operation=operation,
                key=key,
            )
        self._record(operation, key, "read", decoded.metadata.version)
        return decoded.data

    def head(self, key: str) -> ObjectMetadata:
        operation = "head"
        key = normalize_key(key)
        metadata = self._read(key).metadata
        self._record(operation, key, "read", metadata.version)
        return metadata

    def range_get(self, key: str, start: int, end: int | None = None) -> bytes:
        if type(start) is not int or start < 0:
            raise ValueError("range start must be a non-negative integer")
        if end is not None and (type(end) is not int or end < start):
            raise ValueError("range end must be an integer >= start")
        return self.get(key)[start:end]

    def delete_batch(self, keys: Iterable[DeleteTarget]) -> dict[str, str]:
        results: dict[str, str] = {}
        for target in keys:
            key = normalize_key(target if isinstance(target, str) else target.key)
            path = contained_path(self.root, key)
            with self._locked(key):
                try:
                    current = self._read_path(path, key)
                except NotFound:
                    results[key] = "missing"
                    self._record("delete", key, "missing", None)
                    continue
                if isinstance(target, ObjectRef) and (
                    target.version not in {None, current.metadata.version}
                    or target.size != current.metadata.size
                    or target.sha256 != current.metadata.sha256
                ):
                    results[key] = "precondition_failed"
                    self._record("delete", key, "precondition_failed", current.metadata.version)
                    continue
                try:
                    path.unlink()
                    self._fsync_directory(path.parent)
                except FileNotFoundError:
                    results[key] = "missing"
                    self._record("delete", key, "missing", None)
                except OSError as exc:
                    raise StorageIOError.from_oserror(exc, operation="delete", key=key) from exc
                else:
                    results[key] = "deleted"
                    self._record("delete", key, "deleted", current.metadata.version)
        return results

    def list_prefix(self, prefix: str) -> tuple[str, ...]:
        prefix = normalize_prefix(prefix)
        keys: list[str] = []
        for path in self.root.rglob("*"):
            if not path.is_file() or self._lock_root in path.parents:
                continue
            if path.name.endswith(".duraloco-tmp"):
                continue
            key = path.relative_to(self.root).as_posix()
            if not key.startswith(prefix):
                continue
            try:
                self._read_path(path, key)
            except (NotFound, IntegrityError, StorageIOError):
                continue
            keys.append(key)
        return tuple(sorted(keys))

    def stale_lock_file_count(self) -> int:
        """Persistent lock inodes are harmless; ownership lives in `flock`."""

        return sum(1 for path in self._lock_root.iterdir() if path.is_file())
