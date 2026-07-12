"""Immutable role-scoped lifecycle acknowledgements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from fs_diloco.protocol.canonical_json import canonical_bytes, canonical_digest
from fs_diloco.protocol.schemas import ObjectRef


ACK_KINDS = {"observed", "durably_adopted", "capsuled", "no_longer_needs"}
ACK_ROLES = {"learner", "executor", "committer", "lifecycle_worker"}


@dataclass(frozen=True)
class LifecycleAcknowledgementV1:
    role: str
    subject_id: str
    session_id: str
    kind: str
    commit_seq: int
    commit_id: str
    fragment_id: int | None
    object_refs: tuple[ObjectRef, ...]
    acknowledgement_id: str

    @classmethod
    def create(cls, payload: Mapping[str, Any]) -> "LifecycleAcknowledgementV1":
        body = dict(payload)
        body["schema"] = "duraloco-lifecycle-ack-v1"
        body["acknowledgement_id"] = "ack-" + canonical_digest(body)
        return cls.from_dict(body)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LifecycleAcknowledgementV1":
        required = {
            "schema",
            "role",
            "subject_id",
            "session_id",
            "kind",
            "commit_seq",
            "commit_id",
            "object_refs",
            "acknowledgement_id",
        }
        optional = {"fragment_id"}
        if not isinstance(payload, Mapping) or not required <= set(payload) or (
            set(payload) - required - optional
        ):
            raise ValueError("acknowledgement fields differ from contract")
        if payload["schema"] != "duraloco-lifecycle-ack-v1":
            raise ValueError("unsupported acknowledgement schema")
        role = payload["role"]
        kind = payload["kind"]
        if role not in ACK_ROLES or kind not in ACK_KINDS:
            raise ValueError("unsupported acknowledgement role or kind")
        for field in ("subject_id", "session_id", "commit_id"):
            if not isinstance(payload[field], str) or not payload[field]:
                raise ValueError(f"{field} must be non-empty")
        commit_seq = payload["commit_seq"]
        if type(commit_seq) is not int or commit_seq < 0:
            raise ValueError("commit_seq must be non-negative")
        fragment_id = payload.get("fragment_id")
        if fragment_id is not None and (type(fragment_id) is not int or fragment_id < 0):
            raise ValueError("fragment_id must be non-negative when present")
        raw_refs = payload["object_refs"]
        if not isinstance(raw_refs, list):
            raise ValueError("object_refs must be a list")
        refs = tuple(ObjectRef.from_dict(item) for item in raw_refs)
        if tuple(sorted(refs, key=lambda item: item.key)) != refs:
            raise ValueError("acknowledgement object refs are not canonical")
        if kind == "capsuled" and not refs:
            raise ValueError("capsuled acknowledgement requires object refs")
        body = dict(payload)
        acknowledgement_id = body.pop("acknowledgement_id")
        expected = "ack-" + canonical_digest(body)
        if acknowledgement_id != expected:
            raise ValueError("acknowledgement identity differs")
        return cls(
            role=role,
            subject_id=payload["subject_id"],
            session_id=payload["session_id"],
            kind=kind,
            commit_seq=commit_seq,
            commit_id=payload["commit_id"],
            fragment_id=fragment_id,
            object_refs=refs,
            acknowledgement_id=acknowledgement_id,
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema": "duraloco-lifecycle-ack-v1",
            "role": self.role,
            "subject_id": self.subject_id,
            "session_id": self.session_id,
            "kind": self.kind,
            "commit_seq": self.commit_seq,
            "commit_id": self.commit_id,
            "object_refs": [item.to_dict() for item in self.object_refs],
            "acknowledgement_id": self.acknowledgement_id,
        }
        if self.fragment_id is not None:
            payload["fragment_id"] = self.fragment_id
        return payload

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())


def publish_acknowledgement(backend, layout, acknowledgement: LifecycleAcknowledgementV1):
    data = acknowledgement.canonical_bytes()
    return backend.put_immutable(
        layout.acknowledgement_key(acknowledgement.acknowledgement_id), data
    )
