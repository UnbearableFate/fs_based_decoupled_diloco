"""Content and protocol identity helpers."""

from __future__ import annotations

import hashlib
from typing import Any

from .canonical_json import canonical_bytes, canonical_digest


HEX_DIGITS = frozenset("0123456789abcdef")


def validate_sha256(value: Any, *, field: str = "sha256") -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in HEX_DIGITS for char in value):
        raise ValueError(f"{field} must be 64 lowercase hex characters")
    return value


def content_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def object_id(prefix: str, body: Any) -> str:
    return f"{prefix}-{canonical_digest(body)}"


def proposal_id_for(identity_body: dict[str, Any]) -> str:
    body = dict(identity_body)
    body.pop("proposal_id", None)
    body.pop("created_at", None)
    return object_id("p", body)


def commit_id_for(identity_body: dict[str, Any]) -> str:
    body = dict(identity_body)
    body.pop("commit_id", None)
    body.pop("created_at", None)
    return object_id("c", body)


def frontier_digest_for(identity_body: dict[str, Any]) -> str:
    body = dict(identity_body)
    body.pop("frontier_sha256", None)
    return canonical_digest(body)


def implementation_digest(source_identity: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(source_identity)).hexdigest()
