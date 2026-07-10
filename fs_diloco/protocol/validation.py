"""Layered metadata, causal, namespace, and tensor payload validation."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path, PurePosixPath
from typing import Mapping

from .canonical_json import CanonicalJSONError
from .errors import ErrorCategory, ProtocolError, ValidationReport, thaw_json
from .invariants import IdentityRegistry
from .manifests import load_manifest_bytes
from .quarantine import QuarantineRecord, QuarantineRegistry
from .safetensors_validation import validate_tensor_payload
from .schemas import ProposalManifest


@dataclass
class ValidationContext:
    run_id: str
    run_generation: int
    model_revision: str
    current_commit_id: str
    current_commit_seq: int
    ancestor_commit_ids: frozenset[str]
    commit_sequences_by_id: Mapping[str, int]
    fragment_versions: Mapping[int, int]
    parameter_index_digest: str
    fragment_layout_digest: str
    outer_optimizer_schema_digest: str
    frontier_digests_by_commit: Mapping[str, str]
    fragment_versions_by_commit: Mapping[str, Mapping[int, int]]
    payload_kind: str = "pseudo_gradient"
    max_global_staleness: int = 64
    max_fragment_staleness: int = 4
    namespace_root: Path | None = None
    identity_registry: IdentityRegistry = field(default_factory=IdentityRegistry)
    highest_sequences: dict[tuple[str, str, int], int] = field(default_factory=dict)
    sequence_identities: dict[tuple[str, str, int, int], str] = field(default_factory=dict)


def validate_metadata(proposal: ProposalManifest, context: ValidationContext) -> tuple[str, ...]:
    checks = ["schema", "canonical_identity"]
    if proposal.run_id != context.run_id:
        raise ProtocolError("RUN_MISMATCH", "proposal belongs to a different run")
    if proposal.run_generation != context.run_generation:
        raise ProtocolError("GENERATION_MISMATCH", "proposal belongs to a different generation")
    if proposal.model_revision != context.model_revision:
        raise ProtocolError("MODEL_REVISION_MISMATCH", "proposal model revision mismatch")
    if proposal.parameter_index_digest != context.parameter_index_digest:
        raise ProtocolError("PARAMETER_INDEX_MISMATCH", "parameter index digest mismatch")
    if proposal.fragment_layout_digest != context.fragment_layout_digest:
        raise ProtocolError("FRAGMENT_LAYOUT_MISMATCH", "fragment layout digest mismatch")
    if proposal.outer_optimizer_schema_digest != context.outer_optimizer_schema_digest:
        raise ProtocolError("OUTER_SCHEMA_MISMATCH", "outer optimizer schema digest mismatch")
    if proposal.payload_kind != context.payload_kind:
        raise ProtocolError("PAYLOAD_KIND_MISMATCH", "payload kind differs from run contract")
    checks.append("run_contract")
    context.identity_registry.check(proposal)
    sequence_key = (proposal.learner_id, proposal.learner_session_id, proposal.fragment_id)
    sequence_identity_key = (*sequence_key, proposal.sequence)
    existing_identity = context.sequence_identities.get(sequence_identity_key)
    if existing_identity is not None and existing_identity != proposal.proposal_id:
        raise ProtocolError(
            "SEQUENCE_CONTENT_CONFLICT",
            "one learner/session/fragment sequence maps to different proposal content",
            category=ErrorCategory.FATAL,
        )
    highest = context.highest_sequences.get(sequence_key)
    if highest is not None and proposal.sequence < highest:
        raise ProtocolError("SEQUENCE_ROLLBACK", f"sequence {proposal.sequence} is below {highest}")
    checks.append("identity_uniqueness")
    return tuple(checks)


def validate_causal(proposal: ProposalManifest, context: ValidationContext) -> tuple[str, ...]:
    if proposal.base_commit_seq > context.current_commit_seq:
        raise ProtocolError("FUTURE_BASE", "proposal base commit sequence is in the future")
    if proposal.base_commit_id not in context.ancestor_commit_ids:
        raise ProtocolError("UNKNOWN_BASE", "proposal base is not a current committed ancestor")
    expected_sequence = context.commit_sequences_by_id.get(proposal.base_commit_id)
    if expected_sequence is None or proposal.base_commit_seq != expected_sequence:
        raise ProtocolError(
            "BASE_SEQUENCE_MISMATCH",
            "proposal base commit ID and sequence do not name the same commit",
        )
    expected_frontier = context.frontier_digests_by_commit.get(proposal.base_commit_id)
    if expected_frontier is None:
        raise ProtocolError(
            "UNKNOWN_BASE_FRONTIER",
            "proposal base commit has no authoritative frontier digest",
        )
    if proposal.base_frontier_digest != expected_frontier:
        raise ProtocolError(
            "BASE_FRONTIER_MISMATCH",
            "proposal base frontier digest does not match its base commit",
        )
    if proposal.fragment_id not in context.fragment_versions:
        raise ProtocolError("UNKNOWN_FRAGMENT", "proposal names an unknown fragment")
    current_fragment_version = context.fragment_versions[proposal.fragment_id]
    if proposal.base_fragment_version > current_fragment_version:
        raise ProtocolError("FUTURE_FRAGMENT_BASE", "fragment base version is in the future")
    base_versions = context.fragment_versions_by_commit.get(proposal.base_commit_id)
    if base_versions is None or proposal.fragment_id not in base_versions:
        raise ProtocolError(
            "BASE_FRAGMENT_CONTEXT_MISSING",
            "proposal base frontier has no authoritative version for the fragment",
        )
    if proposal.base_fragment_version != base_versions[proposal.fragment_id]:
        raise ProtocolError(
            "BASE_FRAGMENT_VERSION_MISMATCH",
            "proposal fragment base version does not match its named base frontier",
        )
    global_staleness = context.current_commit_seq - proposal.base_commit_seq
    if global_staleness > context.max_global_staleness:
        raise ProtocolError("STALE_BASE", "proposal exceeds global staleness bound")
    fragment_staleness = current_fragment_version - proposal.base_fragment_version
    if fragment_staleness > context.max_fragment_staleness:
        raise ProtocolError("STALE_FRAGMENT_BASE", "proposal exceeds fragment staleness bound")
    return ("causal_ancestry", "staleness")


def resolve_payload_path(proposal: ProposalManifest, namespace_root: Path) -> Path:
    pure = PurePosixPath(proposal.payload_key)
    if (
        pure.is_absolute()
        or not pure.parts
        or proposal.payload_key != pure.as_posix()
        or any(ord(char) < 32 or ord(char) == 127 for char in proposal.payload_key)
        or "\\" in proposal.payload_key
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise ProtocolError("PAYLOAD_PATH_ESCAPE", "payload key is not a safe relative key")
    try:
        root = namespace_root.resolve(strict=False)
        path = (root / Path(*pure.parts)).resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProtocolError("PAYLOAD_PATH_ESCAPE", "payload key cannot be resolved safely") from exc
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ProtocolError("PAYLOAD_PATH_ESCAPE", "payload path escapes namespace") from exc
    return path


def validate_payload(
    proposal: ProposalManifest,
    context: ValidationContext,
    *,
    require_finite: bool = True,
) -> tuple[tuple[str, ...], dict[str, object]]:
    if context.namespace_root is None:
        raise ProtocolError(
            "PAYLOAD_NAMESPACE_UNAVAILABLE",
            "validation context has no namespace root",
            category=ErrorCategory.RETRYABLE,
        )
    path = resolve_payload_path(proposal, context.namespace_root)
    if not path.is_file():
        raise ProtocolError(
            "PAYLOAD_MISSING",
            f"payload does not exist: {proposal.payload_key}",
            category=ErrorCategory.RETRYABLE,
        )
    try:
        payload = path.read_bytes()
    except (OSError, ValueError) as exc:
        raise ProtocolError(
            "PAYLOAD_READ",
            f"payload could not be read: {proposal.payload_key}",
            category=ErrorCategory.RETRYABLE,
        ) from exc
    size = len(payload)
    if size != proposal.payload_size:
        raise ProtocolError("PAYLOAD_SIZE", f"payload size {size} != {proposal.payload_size}")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != proposal.payload_sha256:
        raise ProtocolError("PAYLOAD_HASH", "payload SHA-256 mismatch")
    metadata = validate_tensor_payload(
        payload,
        tensor_key=proposal.tensor_key,
        shape=proposal.shape,
        dtype=proposal.dtype,
        require_finite=require_finite,
    )
    checks = ("path_containment", "size", "sha256", "safetensors")
    if require_finite:
        checks += ("finite",)
    return checks, metadata


def validate_proposal(
    proposal: ProposalManifest,
    context: ValidationContext,
    *,
    validate_tensor: bool = True,
    require_finite: bool = True,
) -> ValidationReport:
    checks: tuple[str, ...] = ()
    try:
        checks += validate_metadata(proposal, context)
        checks += validate_causal(proposal, context)
        metadata: dict[str, object] = {}
        if validate_tensor:
            payload_checks, metadata = validate_payload(
                proposal, context, require_finite=require_finite
            )
            checks += payload_checks
        sequence_key = (
            proposal.learner_id,
            proposal.learner_session_id,
            proposal.fragment_id,
        )
        eligible = validate_tensor and require_finite
        if eligible:
            validation_level = "full"
        elif validate_tensor:
            validation_level = "payload_without_finite"
        else:
            validation_level = "metadata_causal"
        if eligible:
            context.identity_registry.observe(proposal)
            previous = context.highest_sequences.get(sequence_key, -1)
            context.highest_sequences[sequence_key] = max(proposal.sequence, previous)
            context.sequence_identities[
                (*sequence_key, proposal.sequence)
            ] = proposal.proposal_id
        return ValidationReport.success(
            proposal.proposal_id,
            checks=checks,
            metadata=metadata,
            eligible=eligible,
            validation_level=validation_level,
        )
    except ProtocolError as exc:
        return ValidationReport.failure(proposal.proposal_id, exc, checks=checks)


def validate_or_raise(
    proposal: ProposalManifest,
    context: ValidationContext,
    *,
    validate_tensor: bool = True,
    require_finite: bool = True,
) -> ValidationReport:
    report = validate_proposal(
        proposal,
        context,
        validate_tensor=validate_tensor,
        require_finite=require_finite,
    )
    if report.valid and not report.eligible:
        raise ProtocolError(
            "INCOMPLETE_VALIDATION",
            f"validation level {report.validation_level} cannot enter eligibility",
        )
    if not report.valid:
        error = report.errors[0]
        raise ProtocolError(
            error["code"],
            error["message"],
            category=ErrorCategory(error["category"]),
            details=thaw_json(error.get("details") or {}),
        )
    return report


def validate_candidate_bytes(
    payload: bytes,
    context: ValidationContext,
    quarantine: QuarantineRegistry,
    *,
    validate_tensor: bool = True,
    require_finite: bool = True,
) -> tuple[ValidationReport, QuarantineRecord | None]:
    """Turn arbitrary scanner input into a report/quarantine record, never KeyError."""
    content_sha256 = hashlib.sha256(payload).hexdigest()
    observed_identity: str | None = None
    try:
        manifest = load_manifest_bytes(payload)
        if not isinstance(manifest, ProposalManifest):
            raise ProtocolError("WRONG_MANIFEST_TYPE", "candidate is not a proposal manifest")
        observed_identity = manifest.proposal_id
        report = validate_proposal(
            manifest,
            context,
            validate_tensor=validate_tensor,
            require_finite=require_finite,
        )
        if report.valid:
            return report, None
        item = report.errors[0]
        error = ProtocolError(
            item["code"],
            item["message"],
            category=ErrorCategory(item["category"]),
            details=thaw_json(item.get("details") or {}),
        )
    except CanonicalJSONError as exc:
        error = ProtocolError("MALFORMED_MANIFEST", str(exc))
    except ProtocolError as exc:
        error = exc
    report = ValidationReport.failure(observed_identity, error)
    if error.category == ErrorCategory.RETRYABLE:
        return report, None
    record = quarantine.record(
        observed_identity=observed_identity,
        content_sha256=content_sha256,
        error=error,
    )
    return report, record
