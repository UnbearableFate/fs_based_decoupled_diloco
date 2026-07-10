"""Strict, backend-neutral DuraLoCo Protocol v2 data boundary."""

from .canonical_json import canonical_bytes, canonical_digest, canonical_text, loads_strict
from .errors import ErrorCategory, ProtocolError, ValidationReport
from .schemas import (
    CommitManifest,
    DropDecision,
    FrontierManifest,
    HeadManifest,
    ObjectRef,
    ProposalManifest,
)

__all__ = [
    "CommitManifest",
    "DropDecision",
    "ErrorCategory",
    "FrontierManifest",
    "HeadManifest",
    "ObjectRef",
    "ProposalManifest",
    "ProtocolError",
    "ValidationReport",
    "canonical_bytes",
    "canonical_digest",
    "canonical_text",
    "loads_strict",
]
