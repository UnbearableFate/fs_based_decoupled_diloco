"""Canonical payload codecs and verified object-reference reads."""

from __future__ import annotations

import hashlib
import math
from typing import Any, Mapping

from fs_diloco.protocol.canonical_json import canonical_bytes, loads_strict
from fs_diloco.protocol.schemas import ObjectRef
from fs_diloco.storage.base import ObjectMetadata, StorageBackend
from fs_diloco.testing.deterministic_reference import (
    ReferenceOptimizerState,
    Vector,
    vector_identity,
)

from .errors import VerificationError


def content_ref(key: str, data: bytes) -> ObjectRef:
    return ObjectRef(key=key, sha256=hashlib.sha256(data).hexdigest(), size=len(data))


def metadata_ref(metadata: ObjectMetadata) -> ObjectRef:
    """Drop backend generation tokens from logical, cross-backend identities."""
    return ObjectRef(key=metadata.key, sha256=metadata.sha256, size=metadata.size)


def verified_get(
    backend: StorageBackend,
    ref: ObjectRef,
    *,
    commit_seq: int | None = None,
) -> bytes:
    try:
        data = backend.get(ref.key)
    except Exception as exc:
        raise VerificationError(
            f"cannot read referenced object {ref.key}: {exc}", commit_seq=commit_seq
        ) from exc
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != ref.size or digest != ref.sha256:
        raise VerificationError(
            f"object reference mismatch for {ref.key}", commit_seq=commit_seq
        )
    return data


def canonical_object(data: bytes, *, commit_seq: int | None = None) -> Mapping[str, Any]:
    try:
        payload = loads_strict(data)
    except Exception as exc:
        raise VerificationError(f"invalid canonical JSON: {exc}", commit_seq=commit_seq) from exc
    if not isinstance(payload, dict):
        raise VerificationError("canonical object must be a mapping", commit_seq=commit_seq)
    if canonical_bytes(payload) != data:
        raise VerificationError("object is not in canonical byte form", commit_seq=commit_seq)
    return payload


def _decode_float(value: Any, field: str) -> float:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a canonical float.hex string")
    try:
        result = float.fromhex(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{field} is not a hexadecimal float") from exc
    if not math.isfinite(result) or result.hex() != value:
        raise ValueError(f"{field} must be finite and canonically spelled")
    return result


def encode_params(values: Vector) -> bytes:
    return canonical_bytes({"kind": "params", "values": vector_identity(tuple(values))})


def decode_params(data: bytes) -> Vector:
    payload = canonical_object(data)
    if set(payload) != {"kind", "values"} or payload["kind"] != "params":
        raise ValueError("invalid params payload")
    values = payload["values"]
    if not isinstance(values, list) or not values:
        raise ValueError("params values must be a non-empty list")
    return tuple(_decode_float(value, "params value") for value in values)


def encode_outer_state(state: ReferenceOptimizerState) -> bytes:
    return canonical_bytes({"kind": "outer_state", "state": state.identity()})


def decode_outer_state(data: bytes) -> ReferenceOptimizerState:
    payload = canonical_object(data)
    if set(payload) != {"kind", "state"} or payload["kind"] != "outer_state":
        raise ValueError("invalid outer-state payload")
    state = payload["state"]
    if not isinstance(state, dict) or set(state) != {
        "step",
        "momentum",
        "exp_avg",
        "exp_avg_sq",
    }:
        raise ValueError("invalid outer-state mapping")
    if type(state["step"]) is not int or state["step"] < 0:
        raise ValueError("outer-state step must be non-negative")
    vectors: dict[str, tuple[float, ...]] = {}
    for field in ("momentum", "exp_avg", "exp_avg_sq"):
        raw = state[field]
        if not isinstance(raw, list):
            raise ValueError(f"outer-state {field} must be a list")
        vectors[field] = tuple(_decode_float(value, field) for value in raw)
    return ReferenceOptimizerState(step=state["step"], **vectors)
