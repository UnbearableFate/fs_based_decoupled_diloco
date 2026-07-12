"""Marker-last exact learner capsule manifests and component publication."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping

from fs_diloco.log.codec import canonical_object
from fs_diloco.protocol.canonical_json import canonical_bytes, canonical_digest
from fs_diloco.protocol.schemas import ObjectRef


REQUIRED_COMPONENTS = {
    "model",
    "inner_optimizer",
    "scheduler",
    "scaler",
    "rng",
    "data_source",
    "interval",
    "frontier",
}


@dataclass(frozen=True)
class LearnerCapsuleV1:
    run_id: str
    run_generation: int
    learner_id: str
    learner_session_id: str
    sequence: int
    consistency_point: str
    frontier_commit_seq: int
    frontier_commit_id: str
    pending_proposal_ids: tuple[str, ...]
    components: tuple[tuple[str, ObjectRef], ...]
    capsule_id: str

    @classmethod
    def create(cls, payload: Mapping[str, Any]) -> "LearnerCapsuleV1":
        body = dict(payload)
        body["schema"] = "duraloco-learner-capsule-v1"
        body["capsule_id"] = "capsule-" + canonical_digest(body)
        return cls.from_dict(body)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LearnerCapsuleV1":
        required = {
            "schema",
            "run_id",
            "run_generation",
            "learner_id",
            "learner_session_id",
            "sequence",
            "consistency_point",
            "frontier_commit_seq",
            "frontier_commit_id",
            "pending_proposal_ids",
            "components",
            "capsule_id",
        }
        if not isinstance(payload, Mapping) or set(payload) != required:
            raise ValueError("capsule fields differ from contract")
        if payload["schema"] != "duraloco-learner-capsule-v1":
            raise ValueError("unsupported capsule schema")
        for field in ("run_id", "learner_id", "learner_session_id", "frontier_commit_id"):
            if not isinstance(payload[field], str) or not payload[field]:
                raise ValueError(f"capsule {field} must be non-empty")
        for field in ("run_generation", "frontier_commit_seq"):
            if type(payload[field]) is not int or payload[field] < 0:
                raise ValueError(f"capsule {field} must be non-negative")
        if type(payload["sequence"]) is not int or payload["sequence"] < 1:
            raise ValueError("capsule sequence must be positive")
        if payload["consistency_point"] not in {"interval_boundary", "mid_interval"}:
            raise ValueError("unsupported capsule consistency point")
        pending = payload["pending_proposal_ids"]
        if (
            not isinstance(pending, list)
            or any(not isinstance(item, str) or not item for item in pending)
            or pending != sorted(set(pending))
        ):
            raise ValueError("capsule pending proposal IDs are not canonical")
        raw_components = payload["components"]
        if not isinstance(raw_components, Mapping) or set(raw_components) != REQUIRED_COMPONENTS:
            raise ValueError("capsule is missing exact-recovery components")
        components = tuple(
            (kind, ObjectRef.from_dict(raw_components[kind]))
            for kind in sorted(raw_components)
        )
        body = dict(payload)
        capsule_id = body.pop("capsule_id")
        if capsule_id != "capsule-" + canonical_digest(body):
            raise ValueError("capsule identity differs")
        return cls(
            run_id=payload["run_id"],
            run_generation=payload["run_generation"],
            learner_id=payload["learner_id"],
            learner_session_id=payload["learner_session_id"],
            sequence=payload["sequence"],
            consistency_point=payload["consistency_point"],
            frontier_commit_seq=payload["frontier_commit_seq"],
            frontier_commit_id=payload["frontier_commit_id"],
            pending_proposal_ids=tuple(pending),
            components=components,
            capsule_id=capsule_id,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "duraloco-learner-capsule-v1",
            "run_id": self.run_id,
            "run_generation": self.run_generation,
            "learner_id": self.learner_id,
            "learner_session_id": self.learner_session_id,
            "sequence": self.sequence,
            "consistency_point": self.consistency_point,
            "frontier_commit_seq": self.frontier_commit_seq,
            "frontier_commit_id": self.frontier_commit_id,
            "pending_proposal_ids": list(self.pending_proposal_ids),
            "components": {kind: ref.to_dict() for kind, ref in self.components},
            "capsule_id": self.capsule_id,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())

    @property
    def component_map(self) -> dict[str, ObjectRef]:
        return dict(self.components)


@dataclass(frozen=True)
class CapsulePublication:
    capsule: LearnerCapsuleV1
    manifest_ref: ObjectRef
    marker_ref: ObjectRef


def _ref(key: str, data: bytes) -> ObjectRef:
    return ObjectRef(key=key, sha256=hashlib.sha256(data).hexdigest(), size=len(data))


def publish_capsule(
    backend,
    layout,
    *,
    identity: Mapping[str, Any],
    components: Mapping[str, tuple[bytes, str]],
) -> CapsulePublication:
    if set(components) != REQUIRED_COMPONENTS:
        raise ValueError("exact capsule requires every component")
    refs: dict[str, ObjectRef] = {}
    for kind in sorted(components):
        data, suffix = components[kind]
        if not isinstance(data, bytes) or not data:
            raise ValueError(f"capsule component {kind} must be non-empty bytes")
        digest = hashlib.sha256(data).hexdigest()
        ref = _ref(layout.capsule_component_key(digest, suffix), data)
        backend.put_immutable(ref.key, data, sha256=ref.sha256)
        refs[kind] = ref
    capsule = LearnerCapsuleV1.create(
        {**dict(identity), "components": {key: ref.to_dict() for key, ref in refs.items()}}
    )
    manifest_data = capsule.canonical_bytes()
    manifest_ref = _ref(layout.capsule_manifest_key(capsule.capsule_id), manifest_data)
    backend.put_immutable(
        manifest_ref.key, manifest_data, sha256=manifest_ref.sha256
    )
    marker_data = canonical_bytes(
        {
            "schema": "duraloco-learner-capsule-marker-v1",
            "capsule_id": capsule.capsule_id,
            "manifest_ref": manifest_ref.to_dict(),
        }
    )
    marker_ref = _ref(layout.capsule_marker_key(capsule.capsule_id), marker_data)
    backend.put_immutable(marker_ref.key, marker_data, sha256=marker_ref.sha256)
    return CapsulePublication(capsule, manifest_ref, marker_ref)


def load_capsule(backend, marker_key: str) -> LearnerCapsuleV1:
    marker = canonical_object(backend.get(marker_key))
    if set(marker) != {"schema", "capsule_id", "manifest_ref"} or (
        marker["schema"] != "duraloco-learner-capsule-marker-v1"
    ):
        raise ValueError("capsule marker fields differ")
    manifest_ref = ObjectRef.from_dict(marker["manifest_ref"])
    manifest_data = backend.get(manifest_ref.key)
    if (
        len(manifest_data) != manifest_ref.size
        or hashlib.sha256(manifest_data).hexdigest() != manifest_ref.sha256
    ):
        raise ValueError("capsule manifest ObjectRef differs")
    capsule = LearnerCapsuleV1.from_dict(canonical_object(manifest_data))
    if capsule.capsule_id != marker["capsule_id"]:
        raise ValueError("capsule marker identity differs")
    for ref in capsule.component_map.values():
        data = backend.get(ref.key)
        if len(data) != ref.size or hashlib.sha256(data).hexdigest() != ref.sha256:
            raise ValueError("capsule component ObjectRef differs")
    return capsule
