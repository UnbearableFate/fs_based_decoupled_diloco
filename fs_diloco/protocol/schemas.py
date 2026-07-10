"""Immutable strict Protocol v2 schemas implemented with the standard library."""

from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any, ClassVar, Mapping

from .canonical_json import canonical_bytes, canonical_digest
from .errors import ErrorCategory, ProtocolError
from .identities import commit_id_for, frontier_digest_for, proposal_id_for, validate_sha256


def _error(code: str, message: str, *, fatal: bool = False) -> ProtocolError:
    category = ErrorCategory.FATAL if fatal else ErrorCategory.QUARANTINE
    return ProtocolError(code, message, category=category)


def _strict_fields(payload: Mapping[str, Any], required: set[str], optional: set[str] = set()) -> None:
    if not isinstance(payload, Mapping):
        raise _error("SCHEMA_TYPE", "protocol object must be a mapping")
    found = set(payload)
    missing = required - found
    unknown = found - required - optional
    if missing:
        raise _error("SCHEMA_MISSING_FIELD", f"missing fields: {sorted(missing)}")
    if unknown:
        raise _error("SCHEMA_UNKNOWN_FIELD", f"unknown fields: {sorted(unknown)}")


def _string(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise _error("SCHEMA_TYPE", f"{field} must be a non-empty string")
    return value


def _integer(value: Any, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise _error("SCHEMA_RANGE", f"{field} must be an integer >= {minimum}")
    return value


def _sha(value: Any, field: str) -> str:
    try:
        return validate_sha256(value, field=field)
    except ValueError as exc:
        raise _error("SCHEMA_DIGEST", str(exc)) from exc


def _protocol(value: Any) -> int:
    if value != 2 or type(value) is not int:
        raise _error("UNSUPPORTED_PROTOCOL_VERSION", f"protocol_version must equal 2, got {value!r}")
    return 2


@dataclass(frozen=True)
class ObjectRef:
    key: str
    sha256: str
    size: int
    version: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ObjectRef":
        _strict_fields(payload, {"key", "sha256", "size"}, {"version"})
        version = payload.get("version")
        if version is not None:
            version = _string(version, "version")
        return cls(
            key=_string(payload["key"], "key"),
            sha256=_sha(payload["sha256"], "sha256"),
            size=_integer(payload["size"], "size", minimum=0),
            version=version,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"key": self.key, "sha256": self.sha256, "size": self.size}
        if self.version is not None:
            payload["version"] = self.version
        return payload

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())


@dataclass(frozen=True)
class ProposalManifest:
    MANIFEST_TYPE: ClassVar[str] = "proposal"
    protocol_version: int
    run_id: str
    run_generation: int
    model_revision: str
    proposal_id: str
    learner_id: str
    learner_session_id: str
    sequence: int
    fragment_id: int
    base_commit_id: str
    base_commit_seq: int
    base_fragment_version: int
    base_frontier_digest: str
    previous_interval_proposal_id: str | None
    local_steps_since_base: int
    target_tokens_since_base: int
    payload_kind: str
    payload_key: str
    tensor_key: str
    shape: tuple[int, ...]
    dtype: str
    payload_size: int
    payload_sha256: str
    parameter_index_digest: str
    fragment_layout_digest: str
    outer_optimizer_schema_digest: str
    created_at: str | None = None

    REQUIRED: ClassVar[set[str]] = {
        "manifest_type",
        "protocol_version",
        "run_id",
        "run_generation",
        "model_revision",
        "proposal_id",
        "learner_id",
        "learner_session_id",
        "sequence",
        "fragment_id",
        "base_commit_id",
        "base_commit_seq",
        "base_fragment_version",
        "base_frontier_digest",
        "local_steps_since_base",
        "target_tokens_since_base",
        "payload_kind",
        "payload_key",
        "tensor_key",
        "shape",
        "dtype",
        "payload_size",
        "payload_sha256",
        "parameter_index_digest",
        "fragment_layout_digest",
        "outer_optimizer_schema_digest",
    }
    OPTIONAL: ClassVar[set[str]] = {"previous_interval_proposal_id", "created_at"}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProposalManifest":
        _strict_fields(payload, cls.REQUIRED, cls.OPTIONAL)
        if payload["manifest_type"] != cls.MANIFEST_TYPE:
            raise _error("SCHEMA_ENUM", "manifest_type must be proposal")
        shape = payload["shape"]
        if not isinstance(shape, list) or not shape:
            raise _error("SCHEMA_SHAPE", "shape must be a non-empty list")
        normalized_shape = tuple(_integer(item, "shape item", minimum=1) for item in shape)
        payload_kind = payload["payload_kind"]
        if payload_kind not in {"pseudo_gradient", "local_end_weight"}:
            raise _error("SCHEMA_ENUM", f"unsupported payload_kind: {payload_kind!r}")
        dtype = payload["dtype"]
        if dtype not in {"float32", "float16", "bfloat16", "float64"}:
            raise _error("SCHEMA_ENUM", f"unsupported dtype: {dtype!r}")
        previous = payload.get("previous_interval_proposal_id")
        if previous is not None:
            previous = _string(previous, "previous_interval_proposal_id")
        created_at = payload.get("created_at")
        if created_at is not None:
            created_at = _string(created_at, "created_at")
        instance = cls(
            protocol_version=_protocol(payload["protocol_version"]),
            run_id=_string(payload["run_id"], "run_id"),
            run_generation=_integer(payload["run_generation"], "run_generation"),
            model_revision=_string(payload["model_revision"], "model_revision"),
            proposal_id=_string(payload["proposal_id"], "proposal_id"),
            learner_id=_string(payload["learner_id"], "learner_id"),
            learner_session_id=_string(payload["learner_session_id"], "learner_session_id"),
            sequence=_integer(payload["sequence"], "sequence"),
            fragment_id=_integer(payload["fragment_id"], "fragment_id"),
            base_commit_id=_string(payload["base_commit_id"], "base_commit_id"),
            base_commit_seq=_integer(payload["base_commit_seq"], "base_commit_seq"),
            base_fragment_version=_integer(
                payload["base_fragment_version"], "base_fragment_version"
            ),
            base_frontier_digest=_sha(payload["base_frontier_digest"], "base_frontier_digest"),
            previous_interval_proposal_id=previous,
            local_steps_since_base=_integer(
                payload["local_steps_since_base"], "local_steps_since_base", minimum=1
            ),
            target_tokens_since_base=_integer(
                payload["target_tokens_since_base"], "target_tokens_since_base", minimum=1
            ),
            payload_kind=payload_kind,
            payload_key=_string(payload["payload_key"], "payload_key"),
            tensor_key=_string(payload["tensor_key"], "tensor_key"),
            shape=normalized_shape,
            dtype=dtype,
            payload_size=_integer(payload["payload_size"], "payload_size", minimum=1),
            payload_sha256=_sha(payload["payload_sha256"], "payload_sha256"),
            parameter_index_digest=_sha(
                payload["parameter_index_digest"], "parameter_index_digest"
            ),
            fragment_layout_digest=_sha(
                payload["fragment_layout_digest"], "fragment_layout_digest"
            ),
            outer_optimizer_schema_digest=_sha(
                payload["outer_optimizer_schema_digest"], "outer_optimizer_schema_digest"
            ),
            created_at=created_at,
        )
        expected = proposal_id_for(instance.identity_body())
        if instance.proposal_id != expected:
            raise _error(
                "PROPOSAL_ID_MISMATCH",
                f"proposal_id {instance.proposal_id!r} does not match canonical {expected!r}",
                fatal=True,
            )
        return instance

    @classmethod
    def with_computed_id(cls, payload: Mapping[str, Any]) -> "ProposalManifest":
        body = dict(payload)
        body["proposal_id"] = proposal_id_for(body)
        return cls.from_dict(body)

    def identity_body(self) -> dict[str, Any]:
        body = self.to_dict()
        body.pop("proposal_id")
        body.pop("created_at", None)
        return body

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "manifest_type": self.MANIFEST_TYPE,
            "protocol_version": self.protocol_version,
            "run_id": self.run_id,
            "run_generation": self.run_generation,
            "model_revision": self.model_revision,
            "proposal_id": self.proposal_id,
            "learner_id": self.learner_id,
            "learner_session_id": self.learner_session_id,
            "sequence": self.sequence,
            "fragment_id": self.fragment_id,
            "base_commit_id": self.base_commit_id,
            "base_commit_seq": self.base_commit_seq,
            "base_fragment_version": self.base_fragment_version,
            "base_frontier_digest": self.base_frontier_digest,
            "local_steps_since_base": self.local_steps_since_base,
            "target_tokens_since_base": self.target_tokens_since_base,
            "payload_kind": self.payload_kind,
            "payload_key": self.payload_key,
            "tensor_key": self.tensor_key,
            "shape": list(self.shape),
            "dtype": self.dtype,
            "payload_size": self.payload_size,
            "payload_sha256": self.payload_sha256,
            "parameter_index_digest": self.parameter_index_digest,
            "fragment_layout_digest": self.fragment_layout_digest,
            "outer_optimizer_schema_digest": self.outer_optimizer_schema_digest,
        }
        if self.previous_interval_proposal_id is not None:
            payload["previous_interval_proposal_id"] = self.previous_interval_proposal_id
        if self.created_at is not None:
            payload["created_at"] = self.created_at
        return payload

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())


@dataclass(frozen=True)
class ProposalSelection:
    proposal_id: str
    learner_id: str
    learner_session_id: str
    sequence: int
    base_commit_seq: int
    base_fragment_version: int
    target_tokens: int
    staleness: int
    weight_fp64_hex: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProposalSelection":
        required = {
            "proposal_id",
            "learner_id",
            "learner_session_id",
            "sequence",
            "base_commit_seq",
            "base_fragment_version",
            "target_tokens",
            "staleness",
            "weight_fp64_hex",
        }
        _strict_fields(payload, required)
        weight = _string(payload["weight_fp64_hex"], "weight_fp64_hex")
        try:
            numeric_weight = float.fromhex(weight)
        except ValueError as exc:
            raise _error("SCHEMA_WEIGHT", "weight_fp64_hex is not a hexadecimal float") from exc
        if not math.isfinite(numeric_weight) or numeric_weight <= 0:
            raise _error("SCHEMA_WEIGHT", "proposal weight must be finite and positive")
        if weight != numeric_weight.hex():
            raise _error(
                "SCHEMA_WEIGHT",
                "weight_fp64_hex must use the exact canonical float.hex spelling",
            )
        return cls(
            proposal_id=_string(payload["proposal_id"], "proposal_id"),
            learner_id=_string(payload["learner_id"], "learner_id"),
            learner_session_id=_string(payload["learner_session_id"], "learner_session_id"),
            sequence=_integer(payload["sequence"], "sequence"),
            base_commit_seq=_integer(payload["base_commit_seq"], "base_commit_seq"),
            base_fragment_version=_integer(
                payload["base_fragment_version"], "base_fragment_version"
            ),
            target_tokens=_integer(payload["target_tokens"], "target_tokens", minimum=1),
            staleness=_integer(payload["staleness"], "staleness"),
            weight_fp64_hex=weight,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "learner_id": self.learner_id,
            "learner_session_id": self.learner_session_id,
            "sequence": self.sequence,
            "base_commit_seq": self.base_commit_seq,
            "base_fragment_version": self.base_fragment_version,
            "target_tokens": self.target_tokens,
            "staleness": self.staleness,
            "weight_fp64_hex": self.weight_fp64_hex,
        }


@dataclass(frozen=True)
class CommitManifest:
    MANIFEST_TYPE: ClassVar[str] = "commit"
    protocol_version: int
    run_id: str
    run_generation: int
    commit_seq: int
    commit_id: str
    parent_commit_id: str
    parent_head_version: str
    fencing_epoch: int
    fragment_id: int
    previous_fragment_version: int
    new_fragment_version: int
    selected_proposals: tuple[ProposalSelection, ...]
    aggregate_digest: str
    outer_optimizer_impl_digest: str
    new_params_ref: ObjectRef
    new_outer_state_ref: ObjectRef
    created_at: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CommitManifest":
        required = {
            "manifest_type",
            "protocol_version",
            "run_id",
            "run_generation",
            "commit_seq",
            "commit_id",
            "parent_commit_id",
            "parent_head_version",
            "fencing_epoch",
            "fragment_id",
            "previous_fragment_version",
            "new_fragment_version",
            "selected_proposals",
            "aggregate_digest",
            "outer_optimizer_impl_digest",
            "new_params_ref",
            "new_outer_state_ref",
        }
        _strict_fields(payload, required, {"created_at"})
        if payload["manifest_type"] != cls.MANIFEST_TYPE:
            raise _error("SCHEMA_ENUM", "manifest_type must be commit")
        selected = payload["selected_proposals"]
        if not isinstance(selected, list) or not selected:
            raise _error("SCHEMA_SELECTION", "selected_proposals must be non-empty")
        parent = _string(payload["parent_commit_id"], "parent_commit_id")
        created_at = payload.get("created_at")
        if created_at is not None:
            created_at = _string(created_at, "created_at")
        instance = cls(
            protocol_version=_protocol(payload["protocol_version"]),
            run_id=_string(payload["run_id"], "run_id"),
            run_generation=_integer(payload["run_generation"], "run_generation"),
            commit_seq=_integer(payload["commit_seq"], "commit_seq", minimum=1),
            commit_id=_string(payload["commit_id"], "commit_id"),
            parent_commit_id=parent,
            parent_head_version=_string(payload["parent_head_version"], "parent_head_version"),
            fencing_epoch=_integer(payload["fencing_epoch"], "fencing_epoch"),
            fragment_id=_integer(payload["fragment_id"], "fragment_id"),
            previous_fragment_version=_integer(
                payload["previous_fragment_version"], "previous_fragment_version"
            ),
            new_fragment_version=_integer(payload["new_fragment_version"], "new_fragment_version"),
            selected_proposals=tuple(ProposalSelection.from_dict(item) for item in selected),
            aggregate_digest=_sha(payload["aggregate_digest"], "aggregate_digest"),
            outer_optimizer_impl_digest=_sha(
                payload["outer_optimizer_impl_digest"], "outer_optimizer_impl_digest"
            ),
            new_params_ref=ObjectRef.from_dict(payload["new_params_ref"]),
            new_outer_state_ref=ObjectRef.from_dict(payload["new_outer_state_ref"]),
            created_at=created_at,
        )
        if instance.new_fragment_version != instance.previous_fragment_version + 1:
            raise _error("FRAGMENT_VERSION", "new fragment version must increment by one")
        proposal_ids = [item.proposal_id for item in instance.selected_proposals]
        if len(proposal_ids) != len(set(proposal_ids)):
            raise _error("DUPLICATE_SELECTION", "selected proposal IDs must be unique", fatal=True)
        expected = commit_id_for(instance.identity_body())
        if instance.commit_id != expected:
            raise _error("COMMIT_ID_MISMATCH", "commit_id does not match canonical body", fatal=True)
        return instance

    def identity_body(self) -> dict[str, Any]:
        body = self.to_dict()
        body.pop("commit_id")
        body.pop("created_at", None)
        return body

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "manifest_type": self.MANIFEST_TYPE,
            "protocol_version": self.protocol_version,
            "run_id": self.run_id,
            "run_generation": self.run_generation,
            "commit_seq": self.commit_seq,
            "commit_id": self.commit_id,
            "parent_commit_id": self.parent_commit_id,
            "parent_head_version": self.parent_head_version,
            "fencing_epoch": self.fencing_epoch,
            "fragment_id": self.fragment_id,
            "previous_fragment_version": self.previous_fragment_version,
            "new_fragment_version": self.new_fragment_version,
            "selected_proposals": [item.to_dict() for item in self.selected_proposals],
            "aggregate_digest": self.aggregate_digest,
            "outer_optimizer_impl_digest": self.outer_optimizer_impl_digest,
            "new_params_ref": self.new_params_ref.to_dict(),
            "new_outer_state_ref": self.new_outer_state_ref.to_dict(),
        }
        if self.created_at is not None:
            payload["created_at"] = self.created_at
        return payload


@dataclass(frozen=True)
class FragmentState:
    version: int
    params_ref: ObjectRef
    outer_state_ref: ObjectRef
    producing_commit_id: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FragmentState":
        _strict_fields(
            payload, {"version", "params_ref", "outer_state_ref", "producing_commit_id"}
        )
        return cls(
            version=_integer(payload["version"], "version"),
            params_ref=ObjectRef.from_dict(payload["params_ref"]),
            outer_state_ref=ObjectRef.from_dict(payload["outer_state_ref"]),
            producing_commit_id=_string(payload["producing_commit_id"], "producing_commit_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "params_ref": self.params_ref.to_dict(),
            "outer_state_ref": self.outer_state_ref.to_dict(),
            "producing_commit_id": self.producing_commit_id,
        }


@dataclass(frozen=True)
class FrontierManifest:
    MANIFEST_TYPE: ClassVar[str] = "frontier"
    protocol_version: int
    run_id: str
    run_generation: int
    commit_seq: int
    commit_id: str
    parent_frontier_sha256: str | None
    fencing_epoch: int
    fragments: Mapping[int, FragmentState]
    scheduler_state: Mapping[str, int]
    consumed_proposal_ids: tuple[str, ...]
    frontier_sha256: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FrontierManifest":
        required = {
            "manifest_type",
            "protocol_version",
            "run_id",
            "run_generation",
            "commit_seq",
            "commit_id",
            "parent_frontier_sha256",
            "fencing_epoch",
            "fragments",
            "scheduler_state",
            "consumed_proposal_ids",
            "frontier_sha256",
        }
        _strict_fields(payload, required)
        if payload["manifest_type"] != cls.MANIFEST_TYPE:
            raise _error("SCHEMA_ENUM", "manifest_type must be frontier")
        raw_fragments = payload["fragments"]
        if not isinstance(raw_fragments, dict) or not raw_fragments:
            raise _error("SCHEMA_FRAGMENTS", "fragments must be a non-empty mapping")
        fragments: dict[int, FragmentState] = {}
        for raw_id, state in raw_fragments.items():
            if not isinstance(raw_id, str) or not raw_id.isdigit():
                raise _error("SCHEMA_FRAGMENT_ID", "frontier fragment keys must be decimal strings")
            fragment_id = int(raw_id)
            if fragment_id in fragments:
                raise _error("SCHEMA_FRAGMENT_ID", "duplicate normalized fragment ID")
            fragments[fragment_id] = FragmentState.from_dict(state)
        scheduler = payload["scheduler_state"]
        _strict_fields(scheduler, {"next_fragment_cursor"})
        next_fragment_cursor = _integer(
            scheduler["next_fragment_cursor"], "next_fragment_cursor"
        )
        consumed = payload["consumed_proposal_ids"]
        if not isinstance(consumed, list) or not all(isinstance(item, str) and item for item in consumed):
            raise _error("SCHEMA_TYPE", "consumed_proposal_ids must be a string list")
        if consumed != sorted(set(consumed)):
            raise _error("SCHEMA_ORDER", "consumed_proposal_ids must be unique and sorted")
        parent_digest = payload["parent_frontier_sha256"]
        if parent_digest is not None:
            parent_digest = _sha(parent_digest, "parent_frontier_sha256")
        instance = cls(
            protocol_version=_protocol(payload["protocol_version"]),
            run_id=_string(payload["run_id"], "run_id"),
            run_generation=_integer(payload["run_generation"], "run_generation"),
            commit_seq=_integer(payload["commit_seq"], "commit_seq"),
            commit_id=_string(payload["commit_id"], "commit_id"),
            parent_frontier_sha256=parent_digest,
            fencing_epoch=_integer(payload["fencing_epoch"], "fencing_epoch"),
            fragments=MappingProxyType(dict(fragments)),
            scheduler_state=MappingProxyType(
                {"next_fragment_cursor": next_fragment_cursor}
            ),
            consumed_proposal_ids=tuple(consumed),
            frontier_sha256=_sha(payload["frontier_sha256"], "frontier_sha256"),
        )
        if instance.frontier_sha256 != frontier_digest_for(instance.identity_body()):
            raise _error("FRONTIER_DIGEST_MISMATCH", "frontier digest does not match body", fatal=True)
        return instance

    def identity_body(self) -> dict[str, Any]:
        body = self.to_dict()
        body.pop("frontier_sha256")
        return body

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_type": self.MANIFEST_TYPE,
            "protocol_version": self.protocol_version,
            "run_id": self.run_id,
            "run_generation": self.run_generation,
            "commit_seq": self.commit_seq,
            "commit_id": self.commit_id,
            "parent_frontier_sha256": self.parent_frontier_sha256,
            "fencing_epoch": self.fencing_epoch,
            "fragments": {
                str(key): value.to_dict() for key, value in sorted(self.fragments.items())
            },
            "scheduler_state": dict(self.scheduler_state),
            "consumed_proposal_ids": list(self.consumed_proposal_ids),
            "frontier_sha256": self.frontier_sha256,
        }


@dataclass(frozen=True)
class HeadManifest:
    MANIFEST_TYPE: ClassVar[str] = "head"
    protocol_version: int
    run_id: str
    run_generation: int
    fencing_epoch: int
    commit_seq: int
    commit_id: str
    frontier_ref: ObjectRef

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HeadManifest":
        required = {
            "manifest_type",
            "protocol_version",
            "run_id",
            "run_generation",
            "fencing_epoch",
            "commit_seq",
            "commit_id",
            "frontier_ref",
        }
        _strict_fields(payload, required)
        if payload["manifest_type"] != cls.MANIFEST_TYPE:
            raise _error("SCHEMA_ENUM", "manifest_type must be head")
        return cls(
            protocol_version=_protocol(payload["protocol_version"]),
            run_id=_string(payload["run_id"], "run_id"),
            run_generation=_integer(payload["run_generation"], "run_generation"),
            fencing_epoch=_integer(payload["fencing_epoch"], "fencing_epoch"),
            commit_seq=_integer(payload["commit_seq"], "commit_seq"),
            commit_id=_string(payload["commit_id"], "commit_id"),
            frontier_ref=ObjectRef.from_dict(payload["frontier_ref"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_type": self.MANIFEST_TYPE,
            "protocol_version": self.protocol_version,
            "run_id": self.run_id,
            "run_generation": self.run_generation,
            "fencing_epoch": self.fencing_epoch,
            "commit_seq": self.commit_seq,
            "commit_id": self.commit_id,
            "frontier_ref": self.frontier_ref.to_dict(),
        }


@dataclass(frozen=True)
class DropDecision:
    MANIFEST_TYPE: ClassVar[str] = "drop_decision"
    protocol_version: int
    proposal_id: str
    decision: str
    reason: str
    decided_at_commit_seq: int

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DropDecision":
        required = {
            "manifest_type",
            "protocol_version",
            "proposal_id",
            "decision",
            "reason",
            "decided_at_commit_seq",
        }
        _strict_fields(payload, required)
        if payload["manifest_type"] != cls.MANIFEST_TYPE:
            raise _error("SCHEMA_ENUM", "manifest_type must be drop_decision")
        if payload["decision"] not in {"dropped", "superseded", "quarantined", "expired"}:
            raise _error("SCHEMA_ENUM", f"unsupported decision: {payload['decision']!r}")
        return cls(
            protocol_version=_protocol(payload["protocol_version"]),
            proposal_id=_string(payload["proposal_id"], "proposal_id"),
            decision=payload["decision"],
            reason=_string(payload["reason"], "reason"),
            decided_at_commit_seq=_integer(
                payload["decided_at_commit_seq"], "decided_at_commit_seq"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_type": self.MANIFEST_TYPE,
            "protocol_version": self.protocol_version,
            "proposal_id": self.proposal_id,
            "decision": self.decision,
            "reason": self.reason,
            "decided_at_commit_seq": self.decided_at_commit_seq,
        }


Manifest = ProposalManifest | CommitManifest | FrontierManifest | HeadManifest | DropDecision


def parse_manifest(payload: Mapping[str, Any]) -> Manifest:
    manifest_type = payload.get("manifest_type")
    parsers = {
        "proposal": ProposalManifest.from_dict,
        "commit": CommitManifest.from_dict,
        "frontier": FrontierManifest.from_dict,
        "head": HeadManifest.from_dict,
        "drop_decision": DropDecision.from_dict,
    }
    parser = parsers.get(manifest_type)
    if parser is None:
        raise _error("SCHEMA_MANIFEST_TYPE", f"unknown manifest_type: {manifest_type!r}")
    return parser(payload)


def manifest_digest(manifest: Manifest) -> str:
    return canonical_digest(manifest.to_dict())
