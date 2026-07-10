"""Backend-neutral storage error taxonomy."""

from __future__ import annotations

import errno as errno_module


class StorageError(RuntimeError):
    code = "STORAGE_ERROR"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        key: str | None = None,
        errno: int | None = None,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.key = key
        self.errno = errno


class NotFound(StorageError):
    code = "NOT_FOUND"
    retryable = True


class ImmutableConflict(StorageError):
    code = "IMMUTABLE_CONFLICT"


class PreconditionFailed(StorageError):
    code = "PRECONDITION_FAILED"


class IntegrityError(StorageError):
    code = "INTEGRITY_ERROR"


class InvalidKey(StorageError):
    code = "INVALID_KEY"


class CapabilityError(StorageError):
    code = "CAPABILITY_ERROR"


class LockTimeout(StorageError):
    code = "LOCK_TIMEOUT"
    retryable = True


class StorageIOError(StorageError):
    code = "STORAGE_IO_ERROR"

    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        key: str | None = None,
        errno: int | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message, operation=operation, key=key, errno=errno)
        if retryable is None:
            retryable = errno in {errno_module.EIO, errno_module.ESTALE}
        self.retryable = retryable

    @classmethod
    def from_oserror(cls, exc: OSError, *, operation: str, key: str) -> "StorageIOError":
        retryable = exc.errno in {errno_module.EIO, errno_module.ESTALE}
        return cls(
            f"{operation} failed for {key}: {exc}",
            operation=operation,
            key=key,
            errno=exc.errno,
            retryable=retryable,
        )


class InjectedTimeout(StorageError):
    code = "INJECTED_TIMEOUT"
    retryable = True

    def __init__(self, operation: str, timing: str) -> None:
        super().__init__(
            f"injected {timing}-effect timeout for {operation}",
            operation=operation,
        )
        self.timing = timing

