"""Observational failure evidence with no direct ownership authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Mapping

from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.protocol.identities import validate_sha256


def _nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


@dataclass(frozen=True)
class FailureEvidenceV1:
    """An immutable observation; only a committed membership transition has authority."""

    SCHEMA: ClassVar[str] = "duraloco-failure-evidence-v1"
    schema: str
    evidence_id: str
    run_id: str
    run_generation: int
    membership_revision: int
    suspected_member_id: str
    reason: str
    reporter_member_ids: tuple[str, ...]
    observation_digest: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FailureEvidenceV1":
        expected = {
            "schema",
            "evidence_id",
            "run_id",
            "run_generation",
            "membership_revision",
            "suspected_member_id",
            "reason",
            "reporter_member_ids",
            "observation_digest",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            raise ValueError("failure evidence fields are not canonical")
        if payload["schema"] != cls.SCHEMA:
            raise ValueError("unsupported failure evidence schema")
        if payload["reason"] not in {
            "executor_process_loss",
            "learner_node_loss",
            "committer_process_loss",
            "storage_timeout",
            "manual_test_injection",
        }:
            raise ValueError("unsupported failure evidence reason")
        reporters = payload["reporter_member_ids"]
        if (
            not isinstance(reporters, list)
            or not reporters
            or any(not isinstance(value, str) or not value for value in reporters)
            or reporters != sorted(set(reporters))
        ):
            raise ValueError("failure evidence reporters must be sorted and unique")
        for field in ("run_generation", "membership_revision"):
            if type(payload[field]) is not int or payload[field] < 0:
                raise ValueError(f"{field} must be a non-negative integer")
        validate_sha256(payload["observation_digest"], field="observation_digest")
        instance = cls(
            schema=cls.SCHEMA,
            evidence_id=_nonempty(payload["evidence_id"], "evidence_id"),
            run_id=_nonempty(payload["run_id"], "run_id"),
            run_generation=payload["run_generation"],
            membership_revision=payload["membership_revision"],
            suspected_member_id=_nonempty(
                payload["suspected_member_id"], "suspected_member_id"
            ),
            reason=payload["reason"],
            reporter_member_ids=tuple(reporters),
            observation_digest=payload["observation_digest"],
        )
        if instance.evidence_id != "failure-" + canonical_digest(instance.identity_body()):
            raise ValueError("failure evidence ID differs from canonical content")
        return instance

    @classmethod
    def create(cls, payload: Mapping[str, Any]) -> "FailureEvidenceV1":
        body = dict(payload)
        body["schema"] = cls.SCHEMA
        body.pop("evidence_id", None)
        body["reporter_member_ids"] = sorted(set(body["reporter_member_ids"]))
        body["evidence_id"] = "failure-" + canonical_digest(body)
        return cls.from_dict(body)

    def identity_body(self) -> dict[str, object]:
        body = self.to_dict()
        body.pop("evidence_id")
        return body

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "evidence_id": self.evidence_id,
            "run_id": self.run_id,
            "run_generation": self.run_generation,
            "membership_revision": self.membership_revision,
            "suspected_member_id": self.suspected_member_id,
            "reason": self.reason,
            "reporter_member_ids": list(self.reporter_member_ids),
            "observation_digest": self.observation_digest,
        }
