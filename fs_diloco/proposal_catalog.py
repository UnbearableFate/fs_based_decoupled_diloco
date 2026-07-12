"""Re-entrant proposal discovery over non-authoritative directory listings."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from threading import Lock
from typing import Iterable

from fs_diloco.atomic_io import atomic_write_json
from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.protocol.errors import ErrorCategory, ProtocolError
from fs_diloco.protocol.quarantine import QuarantineRegistry
from fs_diloco.protocol.safetensors_validation import parse_safetensors
from fs_diloco.protocol.schemas import ObjectRef, ProposalManifest
from fs_diloco.protocol.validation import ValidationContext, validate_causal, validate_metadata

from .runtime_view import RuntimeView
from .syncer_core.planning import PlanningCandidate, select_candidate_ids
from .log.production_codec import (
    ValidatedProductionPayload,
    validate_production_tensor_payload,
)


_SAFE_TO_PROTOCOL = {"F16": "float16", "BF16": "bfloat16", "F32": "float32", "F64": "float64"}


@dataclass(frozen=True)
class CatalogEntry:
    manifest: ProposalManifest
    metadata_path: Path
    payload_path: Path | None
    payload_ref: ObjectRef
    metadata_sha256: str
    payload: ValidatedProductionPayload

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
            "file_path": (
                str(self.payload_path) if self.payload_path is not None else self.payload_ref.key
            ),
        }


@dataclass(frozen=True)
class PayloadValidationToken:
    proposal_id: str
    metadata_sha256: str
    payload_ref: ObjectRef
    observation_fingerprint: str
    validation_scope_digest: str
    payload: ValidatedProductionPayload


class ProposalCatalog:
    """Full rescans are safe; listing order, duplicates, and omissions are hints only."""

    def __init__(
        self,
        *,
        namespace_root: Path,
        quarantine_root: Path,
        validation_device: object | None = None,
    ) -> None:
        self.namespace_root = namespace_root.resolve(strict=False)
        self.quarantine_root = quarantine_root
        self.validation_device = validation_device
        self._quarantine = QuarantineRegistry()
        self._quarantine_lock = Lock()
        self._validation_tokens: dict[
            tuple[str, str, str, int, str, str], PayloadValidationToken
        ] = {}
        self._token_lock = Lock()
        self._active_scope_digest: str | None = None
        self.last_scan_counters: dict[str, int] = {}

    @staticmethod
    def _scope_digest(log, view: RuntimeView) -> str:
        return canonical_digest(
            {
                "run_id": view.run_id,
                "run_generation": view.run_generation,
                "head_commit_id": view.commit_id,
                "fencing_epoch": view.fencing_epoch,
                "membership_revision": (
                    view.membership.revision if view.membership is not None else -1
                ),
                "owner_id": view.owner_id or "",
                "owner_session_id": view.owner_session_id or "",
                "parameter_index_digest": log.spec.parameter_index_digest,
                "fragment_layout_digest": log.spec.fragment_layout_digest,
                "outer_optimizer_schema_digest": log.spec.outer_optimizer_schema_digest,
            }
        )

    @staticmethod
    def _increment(counters: dict[str, int], lock: Lock, key: str, amount: int = 1) -> None:
        with lock:
            counters[key] = counters.get(key, 0) + amount

    def clear_validation_tokens(self) -> None:
        with self._token_lock:
            self._validation_tokens.clear()
            self._active_scope_digest = None

    def _activate_scope(self, scope_digest: str) -> None:
        with self._token_lock:
            if self._active_scope_digest != scope_digest:
                self._validation_tokens.clear()
                self._active_scope_digest = scope_digest

    @staticmethod
    def _cheap_validate(metadata: dict[str, object], view: RuntimeView, spec) -> None:
        if metadata.get("run_id") != view.run_id:
            raise ProtocolError("RUN_MISMATCH", "proposal belongs to another run")
        if int(metadata.get("run_generation", -1)) != view.run_generation:
            raise ProtocolError("GENERATION_MISMATCH", "proposal belongs to another generation")
        fragment_id = int(metadata.get("fragment_id", 0))
        base_commit_id = metadata.get("base_commit_id")
        base_commit_seq = int(metadata.get("base_commit_seq", -1))
        if not isinstance(base_commit_id, str) or base_commit_id not in view.ancestor_commit_ids:
            raise ProtocolError("CAUSAL_BASE", "proposal base is not a committed ancestor")
        if view.commit_sequences_by_id.get(base_commit_id) != base_commit_seq:
            raise ProtocolError("CAUSAL_SEQUENCE", "proposal base sequence differs")
        if view.commit_seq - base_commit_seq > spec.max_global_staleness:
            raise ProtocolError("GLOBAL_STALENESS", "proposal exceeds global staleness")
        base_versions = view.fragment_versions_by_commit.get(base_commit_id)
        if base_versions is None or fragment_id not in base_versions:
            raise ProtocolError("FRAGMENT_BASE", "proposal base has no fragment version")
        base_fragment_version = int(
            metadata.get("base_fragment_version", metadata.get("base_global_version", -1))
        )
        if base_versions[fragment_id] != base_fragment_version:
            raise ProtocolError("FRAGMENT_BASE", "proposal fragment base differs")
        current_version = view.fragment_versions.get(fragment_id)
        if current_version is None or (
            current_version - base_fragment_version > spec.max_fragment_staleness
        ):
            raise ProtocolError("FRAGMENT_STALENESS", "proposal exceeds fragment staleness")

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
        with self._quarantine_lock:
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
        counters: dict[str, int],
        counter_lock: Lock,
    ) -> CatalogEntry:
        try:
            self._cheap_validate(metadata, view, log.spec)
        except ProtocolError:
            self._increment(counters, counter_lock, "cheap_rejections")
            raise
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
            self._increment(counters, counter_lock, "cheap_rejections")
            raise ProtocolError(
                "INTERVAL_ALREADY_CONSUMED",
                "a proposal from this learner interval is already committed",
            )
        raw_ref = metadata.get("payload_ref")
        payload_path: Path | None
        if raw_ref is not None:
            try:
                payload_ref = ObjectRef.from_dict(raw_ref)
            except Exception as exc:
                raise ProtocolError("PAYLOAD_REF", f"invalid payload ObjectRef: {exc}") from exc
            if payload_ref.key != log.layout.proposal_payload_key(payload_ref.sha256):
                raise ProtocolError("PAYLOAD_REF", "payload ObjectRef key is not canonical")
            observed = log.backend.head(payload_ref.key)
            if observed.size != payload_ref.size or observed.sha256 != payload_ref.sha256:
                raise ProtocolError("PAYLOAD_REF", "payload ObjectRef observation differs")
            observation = canonical_digest(
                {
                    "kind": "authority",
                    "key": payload_ref.key,
                    "version": observed.version,
                    "size": observed.size,
                    "sha256": observed.sha256,
                }
            )
            payload_path = None

            def read_payload() -> bytes:
                return log.backend.get(payload_ref.key)

        else:
            payload_path = self._contained_payload(metadata.get("file_path"))
            try:
                stat = payload_path.stat()
            except OSError as exc:
                raise ProtocolError(
                    "PAYLOAD_READ",
                    f"cannot stat proposal payload: {exc}",
                    category=ErrorCategory.RETRYABLE,
                ) from exc
            raw_sha = metadata.get("sha256")
            raw_size = metadata.get("file_size_bytes")
            if not isinstance(raw_sha, str) or len(raw_sha) != 64:
                raise ProtocolError("PAYLOAD_REF", "legacy payload SHA-256 is invalid")
            if type(raw_size) is not int or raw_size < 1:
                raise ProtocolError("PAYLOAD_REF", "legacy payload size is invalid")
            payload_ref = ObjectRef(
                key=log.layout.proposal_payload_key(raw_sha),
                sha256=raw_sha,
                size=raw_size,
            )
            observation = canonical_digest(
                {
                    "kind": "legacy-path",
                    "path": str(payload_path),
                    "device": stat.st_dev,
                    "inode": stat.st_ino,
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "declared_sha256": raw_sha,
                }
            )

            def read_payload() -> bytes:
                return payload_path.read_bytes()

        metadata_sha256 = hashlib.sha256(metadata_bytes).hexdigest()
        scope_digest = self._scope_digest(log, view)
        self._activate_scope(scope_digest)
        token_key = (
            metadata_sha256,
            payload_ref.key,
            payload_ref.sha256,
            payload_ref.size,
            observation,
            scope_digest,
        )
        with self._token_lock:
            token = self._validation_tokens.get(token_key)
        validated_payload: ValidatedProductionPayload
        payload_bytes: bytes | None = None
        if token is not None:
            validated_payload = token.payload
            self._increment(counters, counter_lock, "validation_token_hits")
        else:
            try:
                payload = read_payload()
                payload_bytes = payload
            except OSError as exc:
                raise ProtocolError(
                    "PAYLOAD_READ",
                    f"cannot read proposal payload: {exc}",
                    category=ErrorCategory.RETRYABLE,
                ) from exc
            self._increment(counters, counter_lock, "payload_reads")
            headers, _ = parse_safetensors(payload)
            if len(headers) != 1:
                raise ProtocolError(
                    "PAYLOAD_TENSOR_KEY", "proposal payload must contain one tensor"
                )
            tensor_key, header = next(iter(headers.items()))
            expected_key = (
                "fragment_params"
                if metadata.get("update_kind") == "fragment"
                else "local_params"
            )
            if tensor_key != expected_key:
                raise ProtocolError(
                    "PAYLOAD_TENSOR_KEY", f"expected {expected_key}, found {tensor_key}"
                )
            try:
                dtype = _SAFE_TO_PROTOCOL[header.dtype]
            except KeyError as exc:
                raise ProtocolError(
                    "PAYLOAD_DTYPE",
                    f"unsupported proposal payload dtype: {header.dtype}",
                ) from exc
            validated_payload = validate_production_tensor_payload(
                payload,
                tensor_key=tensor_key,
                shape=header.shape,
                dtype=dtype,
                require_finite=True,
                validation_device=self.validation_device,
            ).without_data()
            self._increment(counters, counter_lock, "sha_checks")
            self._increment(counters, counter_lock, "finite_checks")
            if (
                validated_payload.sha256 != payload_ref.sha256
                or validated_payload.size != payload_ref.size
            ):
                raise ProtocolError("PAYLOAD_REF", "payload bytes differ from ObjectRef")
            if raw_ref is None:
                assert payload_bytes is not None
                log.backend.put_immutable(
                    payload_ref.key,
                    payload_bytes,
                    sha256=payload_ref.sha256,
                )
        tensor_key = validated_payload.tensor_key
        dtype = validated_payload.dtype
        shape = validated_payload.shape
        payload_sha256 = validated_payload.sha256
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
            "shape": list(shape),
            "dtype": dtype,
            "payload_size": validated_payload.size,
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
        if token is None:
            token = PayloadValidationToken(
                proposal_id=manifest.proposal_id,
                metadata_sha256=metadata_sha256,
                payload_ref=payload_ref,
                observation_fingerprint=observation,
                validation_scope_digest=scope_digest,
                payload=validated_payload,
            )
            with self._token_lock:
                self._validation_tokens[token_key] = token
        elif token.proposal_id != manifest.proposal_id:
            raise ProtocolError(
                "VALIDATION_TOKEN_CONFLICT",
                "cached validation token maps to another proposal identity",
                category=ErrorCategory.FATAL,
            )
        return CatalogEntry(
            manifest=manifest,
            metadata_path=metadata_path,
            payload_path=payload_path,
            payload_ref=payload_ref,
            metadata_sha256=metadata_sha256,
            payload=validated_payload,
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
        paths = sorted(set(metadata_paths), key=lambda item: item.as_posix())
        counters: dict[str, int] = {
            "listed_count": len(paths),
            "metadata_reads": 0,
            "observed_count": 0,
            "payload_reads": 0,
            "sha_checks": 0,
            "finite_checks": 0,
            "validation_token_hits": 0,
            "cheap_rejections": 0,
        }
        counter_lock = Lock()

        def scan_path(path: Path) -> CatalogEntry | None:
            try:
                content = path.read_bytes()
            except OSError:
                return None
            self._increment(counters, counter_lock, "metadata_reads")
            try:
                metadata = json.loads(content)
            except (UnicodeDecodeError, json.JSONDecodeError):
                metadata = None
            if not isinstance(metadata, dict):
                self._persist_error(
                    source=path,
                    content=content,
                    observed_identity=None,
                    error=ProtocolError("MALFORMED_METADATA", "proposal metadata is not valid JSON"),
                )
                return None
            self._increment(counters, counter_lock, "observed_count")
            observed = metadata.get("proposal_id")
            observed_identity = observed if isinstance(observed, str) else None
            try:
                return self._candidate(
                    metadata_path=path,
                    metadata_bytes=content,
                    metadata=metadata,
                    log=log,
                    view=view,
                    counters=counters,
                    counter_lock=counter_lock,
                )
            except ProtocolError as exc:
                self._persist_error(
                    source=path,
                    content=content,
                    observed_identity=observed_identity,
                    error=exc,
                )
                return None
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                self._persist_error(
                    source=path,
                    content=content,
                    observed_identity=observed_identity,
                    error=ProtocolError("MALFORMED_METADATA", str(exc)),
                )
                return None

        with ThreadPoolExecutor(max_workers=max(1, min(8, len(paths)))) as executor:
            candidates = executor.map(scan_path, paths)
            for entry in candidates:
                if entry is None:
                    continue
                key = (
                    entry.manifest.learner_id,
                    entry.manifest.learner_session_id,
                    entry.manifest.fragment_id,
                    entry.manifest.sequence,
                )
                prior = sequence_identities.get(key)
                if prior is not None and prior != entry.proposal_id:
                    try:
                        conflict_content = entry.metadata_path.read_bytes()
                    except OSError:
                        continue
                    self._persist_error(
                        source=entry.metadata_path,
                        content=conflict_content,
                        observed_identity=entry.proposal_id,
                        error=ProtocolError(
                            "SEQUENCE_CONTENT_CONFLICT",
                            "one lineage sequence maps to different proposal content",
                            category=ErrorCategory.FATAL,
                        ),
                    )
                    continue
                sequence_identities[key] = entry.proposal_id
                entries.setdefault(entry.proposal_id, entry)
        self.last_scan_counters = dict(counters)
        return tuple(entries[key] for key in sorted(entries))

    @staticmethod
    def select(
        entries: Iterable[CatalogEntry],
        *,
        fragment_id: int,
        quorum_max: int,
    ) -> tuple[CatalogEntry, ...]:
        materialized = tuple(entries)
        by_id = {entry.proposal_id: entry for entry in materialized}
        selected_ids = select_candidate_ids(
            (
                PlanningCandidate(
                    proposal_id=entry.proposal_id,
                    learner_id=entry.manifest.learner_id,
                    sequence=entry.manifest.sequence,
                    fragment_id=entry.manifest.fragment_id,
                    target_tokens=entry.manifest.target_tokens_since_base,
                    base_fragment_version=entry.manifest.base_fragment_version,
                    payload_sha256=entry.manifest.payload_sha256,
                )
                for entry in materialized
            ),
            fragment_id=fragment_id,
            quorum_max=quorum_max,
        )
        return tuple(by_id[proposal_id] for proposal_id in selected_ids)

    @staticmethod
    def publish_entry(log, entry: CatalogEntry) -> ObjectRef:
        return log.publish_validated_proposal_reference(
            entry.manifest, entry.payload, entry.payload_ref
        )

    @staticmethod
    def load_payload(entry: CatalogEntry, *, backend) -> bytes:
        data = backend.get(entry.payload_ref.key)
        if len(data) != entry.payload_ref.size or (
            hashlib.sha256(data).hexdigest() != entry.payload_ref.sha256
        ):
            raise ProtocolError("PAYLOAD_REF", "selected payload ObjectRef differs")
        return data
