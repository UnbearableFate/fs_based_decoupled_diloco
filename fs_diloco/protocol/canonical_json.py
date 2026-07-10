"""Canonical JSON for Protocol v2 identities.

Identity-bearing JSON is deliberately smaller than general JSON: keys and
strings are NFC normalized, floats are forbidden, duplicate keys are rejected,
and output is UTF-8 with sorted keys and no insignificant whitespace.
"""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from typing import Any


class CanonicalJSONError(ValueError):
    pass


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalJSONError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise CanonicalJSONError(f"non-finite JSON number is forbidden: {value}")


def _normalize(value: Any, *, path: str = "$") -> Any:
    if value is None or type(value) is bool or type(value) is int:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise CanonicalJSONError(f"non-finite float at {path}")
        raise CanonicalJSONError(f"JSON floats are forbidden in canonical identity at {path}")
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, (list, tuple)):
        return [_normalize(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                raise CanonicalJSONError(f"non-string object key at {path}: {raw_key!r}")
            key = unicodedata.normalize("NFC", raw_key)
            if key in normalized:
                raise CanonicalJSONError(f"key collision after Unicode normalization at {path}: {key!r}")
            normalized[key] = _normalize(item, path=f"{path}.{key}")
        return normalized
    raise CanonicalJSONError(f"unsupported canonical JSON value at {path}: {type(value).__name__}")


def canonical_text(value: Any) -> str:
    try:
        normalized = _normalize(value)
    except RecursionError as exc:
        raise CanonicalJSONError("canonical JSON nesting exceeds the supported depth") from exc
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_bytes(value: Any) -> bytes:
    return canonical_text(value).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def loads_strict(payload: str | bytes | bytearray) -> Any:
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
        )
    except CanonicalJSONError:
        raise
    except (UnicodeDecodeError, RecursionError, ValueError) as exc:
        raise CanonicalJSONError(str(exc)) from exc
    try:
        return _normalize(value)
    except RecursionError as exc:
        raise CanonicalJSONError("canonical JSON nesting exceeds the supported depth") from exc
