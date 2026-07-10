"""Read-only legacy update parser and explicit v1-to-v2 conversion helper."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Mapping

from .errors import ProtocolError
from .schemas import ProposalManifest


@dataclass(frozen=True)
class LegacyProposal:
    run_id: str
    update_id: str
    learner_id: str
    fragment_id: int
    base_fragment_version: int
    base_global_sequence: int
    local_step_start: int
    local_step_end: int
    target_tokens: int
    file_path: str
    file_size: int
    sha256: str | None


def parse_v1_manifest(payload: Mapping[str, Any]) -> LegacyProposal:
    if not isinstance(payload, Mapping):
        raise ProtocolError("V1_SCHEMA", "legacy manifest root must be a mapping")
    required = {"run_id", "update_id", "learner_id", "file_path", "file_size_bytes"}
    missing = required - payload.keys()
    if missing:
        raise ProtocolError("V1_MISSING_FIELD", f"legacy manifest is missing {sorted(missing)}")
    try:
        is_fragment = payload.get("update_kind") == "fragment"
        fragment_id = int(payload.get("fragment_id", 0))
        base_fragment = int(
            payload.get("base_fragment_version", payload.get("base_global_version", 0))
        )
        base_global = int(
            payload.get("base_global_merge_event", payload.get("base_global_version", 0))
        )
        token_key = "tokens_since_fragment_load" if is_fragment else "tokens_since_global_load"
        target_tokens = int(payload.get(token_key, payload.get("tokens_this_update", 0)))
        local_step_start = int(payload.get("local_step_start", 0))
        local_step_end = int(payload.get("local_step_end", 0))
        file_size = int(payload["file_size_bytes"])
    except (TypeError, ValueError) as exc:
        raise ProtocolError("V1_SCHEMA", f"legacy numeric field is invalid: {exc}") from exc
    if min(
        fragment_id,
        base_fragment,
        base_global,
        target_tokens,
        local_step_start,
        local_step_end,
        file_size,
    ) < 0:
        raise ProtocolError("V1_SCHEMA", "legacy numeric fields must be non-negative")
    return LegacyProposal(
        run_id=str(payload["run_id"]),
        update_id=str(payload["update_id"]),
        learner_id=str(payload["learner_id"]),
        fragment_id=fragment_id,
        base_fragment_version=base_fragment,
        base_global_sequence=base_global,
        local_step_start=local_step_start,
        local_step_end=local_step_end,
        target_tokens=target_tokens,
        file_path=str(payload["file_path"]),
        file_size=file_size,
        sha256=str(payload["sha256"]) if payload.get("sha256") else None,
    )


def convert_v1_read_only(
    legacy: LegacyProposal,
    *,
    run_generation: int,
    model_revision: str,
    learner_session_id: str,
    sequence: int,
    base_commit_id: str,
    base_frontier_digest: str,
    namespace_root: Path,
    parameter_index_digest: str,
    fragment_layout_digest: str,
    outer_optimizer_schema_digest: str,
    tensor_key: str,
    shape: list[int],
    dtype: str,
) -> ProposalManifest:
    """Construct, but never publish, a v2 proposal in an explicit new context."""
    path = Path(legacy.file_path).resolve(strict=False)
    root = namespace_root.resolve(strict=False)
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ProtocolError("PAYLOAD_PATH_ESCAPE", "legacy file is outside conversion namespace") from exc
    digest = legacy.sha256
    if digest is None:
        if not path.is_file():
            raise ProtocolError("PAYLOAD_MISSING", "legacy payload is missing")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    payload = {
        "manifest_type": "proposal",
        "protocol_version": 2,
        "run_id": legacy.run_id,
        "run_generation": run_generation,
        "model_revision": model_revision,
        "learner_id": legacy.learner_id,
        "learner_session_id": learner_session_id,
        "sequence": sequence,
        "fragment_id": legacy.fragment_id,
        "base_commit_id": base_commit_id,
        "base_commit_seq": legacy.base_global_sequence,
        "base_fragment_version": legacy.base_fragment_version,
        "base_frontier_digest": base_frontier_digest,
        "local_steps_since_base": max(1, legacy.local_step_end - legacy.local_step_start),
        "target_tokens_since_base": max(1, legacy.target_tokens),
        "payload_kind": "local_end_weight",
        "payload_key": relative,
        "tensor_key": tensor_key,
        "shape": shape,
        "dtype": dtype,
        "payload_size": legacy.file_size,
        "payload_sha256": digest,
        "parameter_index_digest": parameter_index_digest,
        "fragment_layout_digest": fragment_layout_digest,
        "outer_optimizer_schema_digest": outer_optimizer_schema_digest,
    }
    return ProposalManifest.with_computed_id(payload)


def write_v2_authority(*_args: object, **_kwargs: object) -> None:
    raise ProtocolError(
        "V1_ADAPTER_READ_ONLY",
        "the Protocol v1 adapter cannot write Protocol v2 authority",
    )
