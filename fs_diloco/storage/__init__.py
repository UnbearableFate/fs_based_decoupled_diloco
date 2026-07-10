"""Semantic storage backends introduced by the DuraLoCo phase plan."""

from .base import ObjectMetadata, OperationRecord, StorageBackend, StorageCapabilities
from .errors import (
    CapabilityError,
    ImmutableConflict,
    IntegrityError,
    InjectedTimeout,
    InvalidKey,
    LockTimeout,
    NotFound,
    PreconditionFailed,
    StorageError,
    StorageIOError,
)
from .fault_injection import FaultEvent, FaultInjectingBackend, FaultSchedule
from .memory import FailureRule, InMemoryStorageBackend
from .object_ref import ObjectRef
from .posix import PosixStorageBackend

__all__ = [
    "CapabilityError",
    "FailureRule",
    "FaultEvent",
    "FaultInjectingBackend",
    "FaultSchedule",
    "ImmutableConflict",
    "InMemoryStorageBackend",
    "IntegrityError",
    "InjectedTimeout",
    "InvalidKey",
    "LockTimeout",
    "NotFound",
    "ObjectMetadata",
    "ObjectRef",
    "OperationRecord",
    "PreconditionFailed",
    "PosixStorageBackend",
    "StorageBackend",
    "StorageCapabilities",
    "StorageError",
    "StorageIOError",
]
