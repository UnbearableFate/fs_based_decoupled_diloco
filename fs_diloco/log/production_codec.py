"""Safetensors codecs for production fragment parameters and outer state."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Mapping

import torch
from safetensors.torch import load as load_bytes
from safetensors.torch import save as save_bytes

from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.protocol.errors import ProtocolError
from fs_diloco.protocol.safetensors_validation import parse_safetensors

from .errors import VerificationError


PARAMS_TENSOR_KEY = "params"
PRODUCTION_CODEC = "safetensors-flat-v1"
PRODUCTION_CODEC_DIGEST = canonical_digest(
    {
        "codec": PRODUCTION_CODEC,
        "params_tensor_key": PARAMS_TENSOR_KEY,
        "outer_state": "named-tensors-with-step-v1",
        "numeric_storage": "float32",
    }
)

_PROTOCOL_TORCH_DTYPES = {
    "float16": torch.float16,
    "bfloat16": torch.bfloat16,
    "float32": torch.float32,
    "float64": torch.float64,
}


@dataclass(frozen=True)
class ValidatedProductionPayload:
    data: bytes
    sha256: str
    tensor_key: str
    shape: tuple[int, ...]
    dtype: str
    finite_checked: bool


def _cpu_contiguous(tensor: torch.Tensor, *, dtype: torch.dtype | None = None) -> torch.Tensor:
    result = tensor.detach().to(device="cpu")
    if dtype is not None:
        result = result.to(dtype=dtype)
    return result.contiguous()


def _require_finite(tensor: torch.Tensor, field: str) -> None:
    if tensor.is_floating_point() and not bool(torch.isfinite(tensor).all().item()):
        raise ValueError(f"{field} contains non-finite values")


def validate_production_tensor_payload(
    payload: bytes,
    *,
    tensor_key: str,
    shape: tuple[int, ...],
    dtype: str,
    require_finite: bool = True,
) -> ValidatedProductionPayload:
    """Strictly validate a large production tensor with vectorized finiteness."""

    try:
        headers, _ = parse_safetensors(payload)
        if set(headers) != {tensor_key}:
            raise ProtocolError(
                "PAYLOAD_TENSOR_KEY",
                f"payload keys {sorted(headers)} do not equal expected [{tensor_key!r}]",
            )
        header = headers[tensor_key]
        if header.shape != shape:
            raise ProtocolError("PAYLOAD_SHAPE", f"shape {header.shape} != expected {shape}")
        expected_dtype = _PROTOCOL_TORCH_DTYPES.get(dtype)
        if expected_dtype is None:
            raise ProtocolError("PAYLOAD_DTYPE", f"unsupported protocol dtype: {dtype}")
        tensor = load_bytes(payload)[tensor_key]
        if tensor.dtype != expected_dtype:
            raise ProtocolError(
                "PAYLOAD_DTYPE", f"dtype {tensor.dtype} != expected {expected_dtype}"
            )
        if require_finite and not bool(torch.isfinite(tensor).all().item()):
            raise ProtocolError("PAYLOAD_NONFINITE", "payload contains non-finite values")
        return ValidatedProductionPayload(
            data=payload,
            sha256=hashlib.sha256(payload).hexdigest(),
            tensor_key=tensor_key,
            shape=shape,
            dtype=dtype,
            finite_checked=require_finite,
        )
    except ProtocolError:
        raise
    except Exception as exc:
        raise ProtocolError("PAYLOAD_INVALID", f"invalid production tensor: {exc}") from exc


def encode_production_params(values: torch.Tensor) -> bytes:
    flat = _cpu_contiguous(values.reshape(-1), dtype=torch.float32)
    if flat.numel() < 1:
        raise ValueError("production params must be non-empty")
    _require_finite(flat, "params")
    return save_bytes({PARAMS_TENSOR_KEY: flat})


def decode_production_params(data: bytes, *, device: torch.device | str = "cpu") -> torch.Tensor:
    try:
        headers, _ = parse_safetensors(data)
        if set(headers) != {PARAMS_TENSOR_KEY}:
            raise ValueError("production params must contain exactly the params tensor")
        tensors = load_bytes(data)
        result = tensors[PARAMS_TENSOR_KEY].detach().to(device=device, dtype=torch.float32)
        if result.ndim != 1 or result.numel() < 1:
            raise ValueError("production params tensor must be a non-empty flat vector")
        _require_finite(result, "params")
        return result.contiguous()
    except VerificationError:
        raise
    except Exception as exc:
        raise VerificationError(f"invalid production params payload: {exc}") from exc


def encode_production_outer_state(state: Mapping[str, torch.Tensor]) -> bytes:
    if "step" not in state:
        raise ValueError("outer state must contain step")
    tensors: dict[str, torch.Tensor] = {}
    for key, value in sorted(state.items()):
        if not isinstance(key, str) or not key or not isinstance(value, torch.Tensor):
            raise TypeError("outer state must map non-empty names to tensors")
        dtype = None if key == "step" else torch.float32
        tensor = _cpu_contiguous(value, dtype=dtype)
        if key == "step":
            if tensor.numel() != 1 or tensor.is_floating_point() or int(tensor.item()) < 0:
                raise ValueError("outer state step must be one non-negative integer")
        else:
            if tensor.ndim != 1 or tensor.numel() < 1:
                raise ValueError(f"outer state {key} must be a non-empty flat vector")
            _require_finite(tensor, f"outer state {key}")
        tensors[key] = tensor
    return save_bytes(tensors)


def decode_production_outer_state(
    data: bytes,
    *,
    device: torch.device | str = "cpu",
) -> dict[str, torch.Tensor]:
    try:
        headers, _ = parse_safetensors(data)
        if "step" not in headers or len(headers) < 2:
            raise ValueError("outer state must contain step and optimizer state")
        raw = load_bytes(data)
        result: dict[str, torch.Tensor] = {}
        vector_size: int | None = None
        for key, value in sorted(raw.items()):
            tensor = value.detach().to(device=device)
            if key == "step":
                if tensor.numel() != 1 or tensor.is_floating_point() or int(tensor.item()) < 0:
                    raise ValueError("outer state step is invalid")
            else:
                tensor = tensor.to(dtype=torch.float32).reshape(-1).contiguous()
                _require_finite(tensor, f"outer state {key}")
                if vector_size is None:
                    vector_size = int(tensor.numel())
                elif int(tensor.numel()) != vector_size:
                    raise ValueError("outer state vectors differ in size")
            result[key] = tensor
        return result
    except VerificationError:
        raise
    except Exception as exc:
        raise VerificationError(f"invalid production outer-state payload: {exc}") from exc


def tensor_content_digest(tensor: torch.Tensor) -> str:
    data = encode_production_params(tensor)
    return hashlib.sha256(data).hexdigest()


def production_optimizer_digest(config_identity: Mapping[str, object]) -> str:
    return canonical_digest(
        {
            "implementation": "torch-flat-outer-optimizer-v1",
            "config": dict(config_identity),
            "payload_codec_digest": PRODUCTION_CODEC_DIGEST,
        }
    )


def tensors_close(
    left: torch.Tensor,
    right: torch.Tensor,
    *,
    absolute: float = 1e-7,
    relative: float = 1e-6,
) -> bool:
    if left.shape != right.shape:
        return False
    if not (math.isfinite(absolute) and math.isfinite(relative)):
        return False
    return bool(torch.allclose(left, right, atol=absolute, rtol=relative))
