"""Separate byte identity, state semantics, and numeric comparison evidence."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Mapping

from fs_diloco.protocol.canonical_json import canonical_digest


def content_digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def paired_state_semantic_digest(
    *,
    params_content_sha256: str,
    outer_state_content_sha256: str,
    optimizer_implementation_digest: str,
) -> str:
    return canonical_digest(
        {
            "params_content_sha256": params_content_sha256,
            "outer_state_content_sha256": outer_state_content_sha256,
            "optimizer_implementation_digest": optimizer_implementation_digest,
        }
    )


@dataclass(frozen=True)
class NumericComparisonReport:
    reference_content_sha256: str
    candidate_content_sha256: str
    reference_backend_digest: str
    candidate_backend_digest: str
    atol_hex: str
    rtol_hex: str
    max_abs_error_hex: str
    max_rel_error_hex: str
    equivalent: bool

    def identity(self) -> Mapping[str, object]:
        return {
            "reference_content_sha256": self.reference_content_sha256,
            "candidate_content_sha256": self.candidate_content_sha256,
            "reference_backend_digest": self.reference_backend_digest,
            "candidate_backend_digest": self.candidate_backend_digest,
            "atol": self.atol_hex,
            "rtol": self.rtol_hex,
            "max_abs_error": self.max_abs_error_hex,
            "max_rel_error": self.max_rel_error_hex,
            "equivalent": self.equivalent,
        }

