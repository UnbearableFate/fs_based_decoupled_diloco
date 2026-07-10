"""Dependency-free safetensors structural and finite-value validation."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import struct
from typing import Any, Iterator

from .errors import ProtocolError


DTYPE_BYTES = {"F16": 2, "BF16": 2, "F32": 4, "F64": 8}
PROTOCOL_TO_SAFE = {
    "float16": "F16",
    "bfloat16": "BF16",
    "float32": "F32",
    "float64": "F64",
}


@dataclass(frozen=True)
class TensorHeader:
    key: str
    dtype: str
    shape: tuple[int, ...]
    start: int
    end: int


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError("SAFETENSORS_DUPLICATE_KEY", f"duplicate header key: {key}")
        result[key] = value
    return result


def parse_safetensors(payload: bytes) -> tuple[dict[str, TensorHeader], bytes]:
    if len(payload) < 8:
        raise ProtocolError("PAYLOAD_TRUNCATED", "safetensors payload is shorter than 8 bytes")
    header_size = struct.unpack("<Q", payload[:8])[0]
    if header_size < 2 or header_size > len(payload) - 8:
        raise ProtocolError("SAFETENSORS_HEADER", "invalid safetensors header length")
    header_bytes = payload[8 : 8 + header_size]
    try:
        raw = json.loads(header_bytes, object_pairs_hook=_pairs_no_duplicates)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProtocolError("SAFETENSORS_HEADER", f"invalid header JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ProtocolError("SAFETENSORS_HEADER", "header root must be an object")
    data = payload[8 + header_size :]
    tensors: dict[str, TensorHeader] = {}
    ranges: list[tuple[int, int, str]] = []
    for key, value in raw.items():
        if key == "__metadata__":
            if not isinstance(value, dict):
                raise ProtocolError("SAFETENSORS_HEADER", "__metadata__ must be an object")
            continue
        if not isinstance(value, dict) or set(value) != {"dtype", "shape", "data_offsets"}:
            raise ProtocolError("SAFETENSORS_HEADER", f"invalid tensor descriptor for {key}")
        dtype = value["dtype"]
        if dtype not in DTYPE_BYTES:
            raise ProtocolError("PAYLOAD_DTYPE", f"unsupported safetensors dtype: {dtype}")
        shape = value["shape"]
        if not isinstance(shape, list) or not all(type(item) is int and item >= 0 for item in shape):
            raise ProtocolError("PAYLOAD_SHAPE", f"invalid shape for {key}")
        offsets = value["data_offsets"]
        if (
            not isinstance(offsets, list)
            or len(offsets) != 2
            or not all(type(item) is int for item in offsets)
        ):
            raise ProtocolError("SAFETENSORS_OFFSETS", f"invalid offsets for {key}")
        start, end = offsets
        if start < 0 or end < start or end > len(data):
            raise ProtocolError("PAYLOAD_TRUNCATED", f"tensor {key} offsets escape payload")
        expected = math.prod(shape) * DTYPE_BYTES[dtype]
        if end - start != expected:
            raise ProtocolError(
                "PAYLOAD_SIZE",
                f"tensor {key} has {end - start} data bytes, expected {expected}",
            )
        tensors[key] = TensorHeader(key, dtype, tuple(shape), start, end)
        ranges.append((start, end, key))
    ranges.sort()
    cursor = 0
    for start, end, key in ranges:
        if start != cursor:
            raise ProtocolError("SAFETENSORS_OFFSETS", f"gap/overlap before tensor {key}")
        cursor = end
    if cursor != len(data):
        raise ProtocolError("PAYLOAD_EXTRA_BYTES", "unreferenced bytes follow safetensors tensors")
    return tensors, data


def _values(dtype: str, data: bytes) -> Iterator[float]:
    if dtype == "F16":
        for (value,) in struct.iter_unpack("<e", data):
            yield float(value)
    elif dtype == "F32":
        for (value,) in struct.iter_unpack("<f", data):
            yield float(value)
    elif dtype == "F64":
        for (value,) in struct.iter_unpack("<d", data):
            yield value
    elif dtype == "BF16":
        for (bits,) in struct.iter_unpack("<H", data):
            yield struct.unpack("<f", struct.pack("<I", bits << 16))[0]
    else:  # pragma: no cover - parse_safetensors prevents this
        raise AssertionError(dtype)


def validate_tensor_payload(
    path: str | Path,
    *,
    tensor_key: str,
    shape: tuple[int, ...],
    dtype: str,
    require_finite: bool = True,
) -> dict[str, Any]:
    payload = Path(path).read_bytes()
    tensors, data = parse_safetensors(payload)
    if set(tensors) != {tensor_key}:
        raise ProtocolError(
            "PAYLOAD_TENSOR_KEY",
            f"payload keys {sorted(tensors)} do not equal expected [{tensor_key!r}]",
        )
    header = tensors[tensor_key]
    if header.shape != shape:
        raise ProtocolError("PAYLOAD_SHAPE", f"shape {header.shape} != expected {shape}")
    expected_dtype = PROTOCOL_TO_SAFE[dtype]
    if header.dtype != expected_dtype:
        raise ProtocolError("PAYLOAD_DTYPE", f"dtype {header.dtype} != expected {expected_dtype}")
    if require_finite:
        tensor_data = data[header.start : header.end]
        for index, value in enumerate(_values(header.dtype, tensor_data)):
            if not math.isfinite(value):
                raise ProtocolError("PAYLOAD_NONFINITE", f"non-finite value at flat index {index}")
    return {
        "tensor_key": tensor_key,
        "shape": list(shape),
        "dtype": dtype,
        "numel": math.prod(shape),
        "finite_checked": require_finite,
    }
