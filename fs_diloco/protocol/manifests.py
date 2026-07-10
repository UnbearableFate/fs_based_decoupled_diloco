"""Strict manifest parsing and canonical serialization."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical_json import canonical_bytes, loads_strict
from .errors import ProtocolError
from .schemas import Manifest, parse_manifest


def load_manifest_bytes(payload: bytes) -> Manifest:
    value = loads_strict(payload)
    if not isinstance(value, dict):
        raise ProtocolError("SCHEMA_ROOT", "manifest root must be an object")
    return parse_manifest(value)


def load_manifest(path: str | Path) -> Manifest:
    return load_manifest_bytes(Path(path).read_bytes())


def dump_manifest(manifest: Manifest) -> bytes:
    return canonical_bytes(manifest.to_dict())


def manifest_example(manifest: Manifest) -> dict[str, Any]:
    """Return a detached JSON-shaped example for docs/inspection."""
    return loads_strict(dump_manifest(manifest))
