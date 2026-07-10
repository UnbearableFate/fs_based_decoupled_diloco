"""Typed Protocol v2 validation errors and reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorCategory(str, Enum):
    RETRYABLE = "retryable"
    QUARANTINE = "quarantine"
    FATAL = "fatal"


class ProtocolError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        category: ErrorCategory = ErrorCategory.QUARANTINE,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.category = category
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "category": self.category.value,
            "details": self.details,
        }


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    proposal_id: str | None
    checks: tuple[str, ...] = ()
    errors: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def success(
        cls,
        proposal_id: str,
        *,
        checks: tuple[str, ...],
        metadata: dict[str, Any] | None = None,
    ) -> "ValidationReport":
        return cls(True, proposal_id, checks, (), metadata or {})

    @classmethod
    def failure(
        cls,
        proposal_id: str | None,
        error: ProtocolError,
        *,
        checks: tuple[str, ...] = (),
    ) -> "ValidationReport":
        return cls(False, proposal_id, checks, (error.to_dict(),), {})
