"""Typed failures for the durable transactional log."""

from __future__ import annotations


class LogError(RuntimeError):
    """Base class for P04 log failures."""


class RunInitializationError(LogError):
    """A run generation cannot be initialized or reopened safely."""


class CommitConflict(LogError):
    """A prepared transition lost the head CAS or no longer validates."""


class VerificationError(LogError):
    """The committed chain cannot be verified."""

    def __init__(self, message: str, *, commit_seq: int | None = None) -> None:
        self.commit_seq = commit_seq
        prefix = "" if commit_seq is None else f"commit_seq={commit_seq}: "
        super().__init__(prefix + message)


class InjectedLogCrash(LogError):
    """Deterministic process-crash surrogate used by the P04 crash matrix."""

    def __init__(self, point: str) -> None:
        self.point = point
        super().__init__(f"injected log crash at {point}")
