"""Re-entrant proposal discovery over non-authoritative directory listings."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Iterable

from fs_diloco.atomic_io import atomic_write_json, safe_read_json
from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.protocol.errors import ErrorCategory, ProtocolError
from fs_diloco.protocol.quarantine import QuarantineRegistry
from fs_diloco.protocol.safetensors_validation import parse_safetensors
from fs_diloco.protocol.schemas import ProposalManifest
from fs_diloco.protocol.validation import ValidationContext, validate_causal, validate_metadata

from .runtime_view import RuntimeView
from .log.production_codec import validate_production_tensor_payload


_SAFE_TO_PROTOCOL = {"F16": "float16", "BF16": "bfloat16", "F32": "float32", "F64": "float64"}


@dataclass(frozen=True)
class CatalogEntry:
    manifest: ProposalManifest
    metadata_path: Path
    payload_path: Path
    metadata_sha256: str

    @property
    def proposal_id(self) -> str:
        return self.manifest.proposal_id

    def selection_row(self) -> dict[str, object]:
        return {
            "update_id": self.manifest.proposal_id,
            "proposal_id": self.manifest.proposal_id,
            "learner_id": self.manifest.learner_id,
            "learner_session_id": self.manifest.learner_session_id,
            "sequence": self.manifest.sequence,
            "fragment_id": self.manifest.fragment_id,
            "base_commit_id": self.manifest.base_commit_id,
            "base_commit_seq": self.manifest.base_commit_seq,
            "base_fragment_version": self.manifest.base_fragment_version,
            "local_step_end": self.manifest.sequence,
            "tokens_this_update": self.manifest.target_tokens_since_base,
            "committed_at": self.manifest.created_at or "",
            "file_path": str(self.payload_path),
        }


class ProposalCatalog:
    """Full rescans are safe; listing order, duplicates, and omissions are hints only."""

    def __init__(self, *, namespace_root: Path, quarantine_root: Path) -> None:
        self.namespace_root = namespace_root.resolve(strict=False)
        self.quarantine_root = quarantine_root
        self._quarantine = QuarantineRegistry()

    def _persist_error(
        self,
        *,
        source: Path,
        content: bytes,
        observed_identity: str | None,
        error: ProtocolError,
    ) -> None:
        if error.category == ErrorCategory.RETRYABLE:
            return
        record = self._quarantine.record(
            observed_identity=observed_identity,
            content_sha256=hashlib.sha256(content).hexdigest(),
            error=error,
        )
        payload = record.to_dict()
        payload["source"] = str(source)
        atomic_write_json(self.quarantine_root / f"{record.record_id}.json", payload)

    def _contained_payload(self, raw: object) -> Path:
        if not isinstance(raw, str) or not raw:
            raise ProtocolError("PAYLOAD_PATH", "proposal payload path must be non-empty")
        try:
            path = Path(raw).resolve(strict=False)
            path.relative_to(self.namespace_root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ProtocolError("PAYLOAD_PATH_ESCAPE", "proposal payload escapes run root") from exc
        return path

    def _candidate(
        self,
        *,
        metadata_path: Path,
        metadata_bytes: bytes,
        metadata: dict[str, object],
        log,
        view: RuntimeView,
    ) -> CatalogEntry:
        payload_path = self._contained_payload(metadata.get("file_path"))
        fragment_id = int(metadata.get("fragment_id", 0))
        base_fragment_version = int(
            metadata.get("base_fragment_version", metadata.get("base_global_version", -1))
        )
        learner_id = metadata.get("learner_id")
        learner_session_id = metadata.get("learner_session_id")
        base_commit_id = metadata.get("base_commit_id")
        interval_base = (
            learner_id,
            learner_session_id,
            fragment_id,
            base_commit_id,
            base_fragment_version,
        )
        if interval_base in view.consumed_interval_bases:
            raise ProtocolError(
                "INTERVAL_ALREADY_CONSUMED",
                "a proposal from this learner interval is already committed",
            )
        try:
            payload = payload_path.read_bytes()
        except OSError as exc:
            raise ProtocolError(
                "PAYLOAD_READ",
                f"cannot read proposal payload: {exc}",
                category=ErrorCategory.RETRYABLE,
            ) from exc
        payload_sha256 = hashlib.sha256(payload).hexdigest()
        headers, _ = parse_safetensors(payload)
        if len(headers) != 1:
            raise ProtocolError("PAYLOAD_TENSOR_KEY", "proposal payload must contain one tensor")
        tensor_key, header = next(iter(headers.items()))
        expected_key = "fragment_params" if metadata.get("update_kind") == "fragment" else "local_params"
        if tensor_key != expected_key:
            raise ProtocolError("PAYLOAD_TENSOR_KEY", f"expected {expected_key}, found {tensor_key}")
        dtype = _SAFE_TO_PROTOCOL[header.dtype]
        validate_production_tensor_payload(
            payload,
            tensor_key=tensor_key,
            shape=header.shape,
            dtype=dtype,
            require_finite=True,
        )
        local_start = int(metadata.get("local_step_start", -1))
        local_end = int(metadata.get("local_step_end", -1))
        if local_start < 0 or local_end <= local_start:
            raise ProtocolError("INTERVAL", "local step interval must be positive and monotonic")
        created_at = metadata.get("created_at")
        body = {
            "manifest_type": "proposal",
            "protocol_version": 2,
            "run_id": view.run_id,
            "run_generation": view.run_generation,
            "model_revision": log.spec.model_revision,
            "learner_id": metadata.get("learner_id"),
            "learner_session_id": metadata.get("learner_session_id"),
            "sequence": int(metadata.get("proposal_sequence", local_end)),
            "fragment_id": fragment_id,
            "base_commit_id": metadata.get("base_commit_id"),
            "base_commit_seq": int(metadata.get("base_commit_seq", -1)),
            "base_fragment_version": base_fragment_version,
            "base_frontier_digest": metadata.get("base_frontier_digest"),
            "local_steps_since_base": local_end - local_start,
            "target_tokens_since_base": int(metadata.get("tokens_this_update", 0)),
            "payload_kind": "local_end_weight",
            "payload_key": log.layout.proposal_payload_key(payload_sha256),
            "tensor_key": tensor_key,
            "shape": list(header.shape),
            "dtype": dtype,
            "payload_size": len(payload),
            "payload_sha256": payload_sha256,
            "parameter_index_digest": log.spec.parameter_index_digest,
            "fragment_layout_digest": log.spec.fragment_layout_digest,
            "outer_optimizer_schema_digest": log.spec.outer_optimizer_schema_digest,
        }
        if created_at is not None:
            body["created_at"] = str(created_at)
        previous = metadata.get("previous_interval_proposal_id")
        if previous is not None:
            body["previous_interval_proposal_id"] = previous
        manifest = ProposalManifest.with_computed_id(body)
        context = ValidationContext(
            run_id=view.run_id,
            run_generation=view.run_generation,
            model_revision=log.spec.model_revision,
            current_commit_id=view.commit_id,
            current_commit_seq=view.commit_seq,
            ancestor_commit_ids=view.ancestor_commit_ids,
            commit_sequences_by_id=view.commit_sequences_by_id,
            fragment_versions=view.fragment_versions,
            parameter_index_digest=log.spec.parameter_index_digest,
            fragment_layout_digest=log.spec.fragment_layout_digest,
            outer_optimizer_schema_digest=log.spec.outer_optimizer_schema_digest,
            frontier_digests_by_commit=view.frontier_digests_by_commit,
            fragment_versions_by_commit=view.fragment_versions_by_commit,
            payload_kind="local_end_weight",
            max_global_staleness=log.spec.max_global_staleness,
            max_fragment_staleness=log.spec.max_fragment_staleness,
            highest_sequences=dict(view.last_committed_sequences),
        )
        validate_metadata(manifest, context)
        validate_causal(manifest, context)
        if manifest.proposal_id in view.consumed_proposal_ids:
            raise ProtocolError("ALREADY_CONSUMED", "proposal is already committed")
        return CatalogEntry(
            manifest=manifest,
            metadata_path=metadata_path,
            payload_path=payload_path,
            metadata_sha256=hashlib.sha256(metadata_bytes).hexdigest(),
        )

    def scan(
        self,
        *,
        metadata_paths: Iterable[Path],
        log,
        view: RuntimeView,
    ) -> tuple[CatalogEntry, ...]:
        entries: dict[str, CatalogEntry] = {}
        sequence_identities: dict[tuple[str, str, int, int], str] = {}
        for path in sorted(set(metadata_paths), key=lambda item: item.as_posix()):
            try:
                content = path.read_bytes()
            except OSError:
                continue
            metadata = safe_read_json(path)
            if not isinstance(metadata, dict):
                self._persist_error(
                    source=path,
                    content=content,
                    observed_identity=None,
                    error=ProtocolError("MALFORMED_METADATA", "proposal metadata is not valid JSON"),
                )
                continue
            observed = metadata.get("proposal_id")
            observed_identity = observed if isinstance(observed, str) else None
            try:
                entry = self._candidate(
                    metadata_path=path,
                    metadata_bytes=content,
                    metadata=metadata,
                    log=log,
                    view=view,
                )
                key = (
                    entry.manifest.learner_id,
                    entry.manifest.learner_session_id,
                    entry.manifest.fragment_id,
                    entry.manifest.sequence,
                )
                prior = sequence_identities.get(key)
                if prior is not None and prior != entry.proposal_id:
                    raise ProtocolError(
                        "SEQUENCE_CONTENT_CONFLICT",
                        "one lineage sequence maps to different proposal content",
                        category=ErrorCategory.FATAL,
                    )
                sequence_identities[key] = entry.proposal_id
                entries.setdefault(entry.proposal_id, entry)
            except ProtocolError as exc:
                self._persist_error(
                    source=path,
                    content=content,
                    observed_identity=observed_identity,
                    error=exc,
                )
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                self._persist_error(
                    source=path,
                    content=content,
                    observed_identity=observed_identity,
                    error=ProtocolError("MALFORMED_METADATA", str(exc)),
                )
        return tuple(entries[key] for key in sorted(entries))

    @staticmethod
    def select(
        entries: Iterable[CatalogEntry],
        *,
        fragment_id: int,
        quorum_max: int,
    ) -> tuple[CatalogEntry, ...]:
        by_learner: dict[str, CatalogEntry] = {}
        for entry in entries:
            if entry.manifest.fragment_id != fragment_id:
                continue
            current = by_learner.get(entry.manifest.learner_id)
            key = (entry.manifest.sequence, entry.proposal_id)
            if current is None or key < (current.manifest.sequence, current.proposal_id):
                by_learner[entry.manifest.learner_id] = entry
        selected = sorted(by_learner.values(), key=lambda item: item.proposal_id)
        return tuple(selected[:quorum_max])

    @staticmethod
    def load_payload(entry: CatalogEntry) -> bytes:
        payload = entry.payload_path.read_bytes()
        if (
            len(payload) != entry.manifest.payload_size
            or hashlib.sha256(payload).hexdigest() != entry.manifest.payload_sha256
        ):
            raise ProtocolError("PAYLOAD_CHANGED", "proposal payload changed after validation")
        validate_production_tensor_payload(
            payload,
            tensor_key=entry.manifest.tensor_key,
            shape=entry.manifest.shape,
            dtype=entry.manifest.dtype,
            require_finite=True,
        )
        return payload
