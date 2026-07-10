from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
from typing import Iterable

from fs_diloco.protocol.schemas import ProposalManifest


DIGEST = "d" * 64


def safetensors_bytes(
    values: Iterable[float],
    *,
    key: str = "fragment_0000",
    dtype: str = "F32",
    shape: list[int] | None = None,
) -> bytes:
    values = list(values)
    if dtype == "F32":
        data = b"".join(struct.pack("<f", value) for value in values)
    elif dtype == "F16":
        data = b"".join(struct.pack("<e", value) for value in values)
    elif dtype == "BF16":
        words = [struct.unpack("<I", struct.pack("<f", value))[0] >> 16 for value in values]
        data = b"".join(struct.pack("<H", word) for word in words)
    else:
        raise ValueError(dtype)
    header = json.dumps(
        {
            key: {
                "dtype": dtype,
                "shape": shape or [len(values)],
                "data_offsets": [0, len(data)],
            }
        },
        separators=(",", ":"),
    ).encode()
    header += b" " * ((8 - len(header) % 8) % 8)
    return struct.pack("<Q", len(header)) + header + data


def write_payload(
    root: Path,
    values: Iterable[float] = (1.0, -2.0),
    *,
    key: str = "fragment_0000",
    dtype: str = "F32",
    shape: list[int] | None = None,
    relative: str = "immutable/proposals/payload.safetensors",
) -> tuple[Path, bytes]:
    payload = safetensors_bytes(values, key=key, dtype=dtype, shape=shape)
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path, payload


def proposal_dict(
    root: Path,
    *,
    payload: bytes | None = None,
    relative: str = "immutable/proposals/payload.safetensors",
    **overrides: object,
) -> dict:
    if payload is None:
        _path, payload = write_payload(root, relative=relative)
    data = {
        "manifest_type": "proposal",
        "protocol_version": 2,
        "run_id": "run-test",
        "run_generation": 0,
        "model_revision": "synthetic-model-v1",
        "learner_id": "learner-000",
        "learner_session_id": "session-000",
        "sequence": 1,
        "fragment_id": 0,
        "base_commit_id": "genesis",
        "base_commit_seq": 0,
        "base_fragment_version": 0,
        "base_frontier_digest": "a" * 64,
        "local_steps_since_base": 10,
        "target_tokens_since_base": 100,
        "payload_kind": "pseudo_gradient",
        "payload_key": relative,
        "tensor_key": "fragment_0000",
        "shape": [2],
        "dtype": "float32",
        "payload_size": len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "parameter_index_digest": "b" * 64,
        "fragment_layout_digest": "c" * 64,
        "outer_optimizer_schema_digest": "d" * 64,
    }
    data.update(overrides)
    return data


def make_proposal(root: Path, **overrides: object) -> ProposalManifest:
    data = proposal_dict(root, **overrides)
    return ProposalManifest.with_computed_id(data)
