"""Idempotent typed quarantine records for invalid Protocol v2 inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .canonical_json import canonical_digest
from .errors import ErrorCategory, ProtocolError, freeze_json, thaw_json


@dataclass(frozen=True)
class QuarantineRecord:
    record_id: str
    observed_identity: str | None
    content_sha256: str
    error_code: str
    category: str
    details: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "observed_identity": self.observed_identity,
            "content_sha256": self.content_sha256,
            "error_code": self.error_code,
            "category": self.category,
            "details": thaw_json(self.details),
        }


@dataclass
class QuarantineRegistry:
    records: dict[str, QuarantineRecord] = field(default_factory=dict)
    identities: dict[str, str] = field(default_factory=dict)

    def record(
        self,
        *,
        observed_identity: str | None,
        content_sha256: str,
        error: ProtocolError,
    ) -> QuarantineRecord:
        if observed_identity:
            previous = self.identities.get(observed_identity)
            if previous is not None and previous != content_sha256:
                raise ProtocolError(
                    "IDENTITY_CONTENT_CONFLICT",
                    f"quarantined identity {observed_identity} maps to different content",
                    category=ErrorCategory.FATAL,
                    details={"first": previous, "second": content_sha256},
                )
            self.identities[observed_identity] = content_sha256
        body = {
            "observed_identity": observed_identity,
            "content_sha256": content_sha256,
            "error_code": error.code,
            "category": error.category.value,
            "details": error.details,
        }
        record_id = "q-" + canonical_digest(body)
        record = QuarantineRecord(
            record_id=record_id,
            observed_identity=observed_identity,
            content_sha256=content_sha256,
            error_code=error.code,
            category=error.category.value,
            details=freeze_json(error.details),
        )
        return self.records.setdefault(record_id, record)
