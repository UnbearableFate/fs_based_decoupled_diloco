"""Typed Protocol v2 validation errors and reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


def freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    return value


def thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value


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
    eligible: bool = False
    validation_level: str = "invalid"
    checks: tuple[str, ...] = ()
    errors: tuple[Mapping[str, Any], ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    @classmethod
    def success(
        cls,
        proposal_id: str,
        *,
        checks: tuple[str, ...],
        metadata: dict[str, Any] | None = None,
        eligible: bool = True,
        validation_level: str = "full",
    ) -> "ValidationReport":
        return cls(
            True,
            proposal_id,
            eligible,
            validation_level,
            checks,
            (),
            freeze_json(metadata or {}),
        )

    @classmethod
    def failure(
        cls,
        proposal_id: str | None,
        error: ProtocolError,
        *,
        checks: tuple[str, ...] = (),
    ) -> "ValidationReport":
        return cls(
            False,
            proposal_id,
            False,
            "invalid",
            checks,
            (freeze_json(error.to_dict()),),
            MappingProxyType({}),
        )
