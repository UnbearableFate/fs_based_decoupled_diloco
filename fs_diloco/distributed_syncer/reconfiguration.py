"""Strict derived request consumed by the authoritative Floating Committer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Mapping

from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.protocol.identities import validate_sha256

from .failure_evidence import FailureEvidenceV1, _nonempty


@dataclass(frozen=True)
class ReconfigurationRequestV1:
    SCHEMA: ClassVar[str] = "duraloco-reconfiguration-request-v1"
    schema: str
    request_id: str
    expected_membership_revision: int
    expected_membership_digest: str
    remove_member_id: str
    evidence: FailureEvidenceV1

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReconfigurationRequestV1":
        expected = {
            "schema",
            "request_id",
            "expected_membership_revision",
            "expected_membership_digest",
            "remove_member_id",
            "evidence",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected:
            raise ValueError("reconfiguration request fields are not canonical")
        if payload["schema"] != cls.SCHEMA:
            raise ValueError("unsupported reconfiguration request schema")
        revision = payload["expected_membership_revision"]
        if type(revision) is not int or revision < 0:
            raise ValueError("expected membership revision must be non-negative")
        validate_sha256(
            payload["expected_membership_digest"], field="expected_membership_digest"
        )
        evidence = FailureEvidenceV1.from_dict(payload["evidence"])
        remove_member_id = _nonempty(payload["remove_member_id"], "remove_member_id")
        if (
            evidence.membership_revision != revision
            or evidence.suspected_member_id != remove_member_id
        ):
            raise ValueError("failure evidence does not bind requested membership removal")
        instance = cls(
            schema=cls.SCHEMA,
            request_id=_nonempty(payload["request_id"], "request_id"),
            expected_membership_revision=revision,
            expected_membership_digest=payload["expected_membership_digest"],
            remove_member_id=remove_member_id,
            evidence=evidence,
        )
        if instance.request_id != "reconfigure-" + canonical_digest(instance.identity_body()):
            raise ValueError("reconfiguration request ID differs from canonical content")
        return instance

    @classmethod
    def create(cls, payload: Mapping[str, Any]) -> "ReconfigurationRequestV1":
        body = dict(payload)
        body["schema"] = cls.SCHEMA
        body["evidence"] = (
            body["evidence"].to_dict()
            if isinstance(body["evidence"], FailureEvidenceV1)
            else body["evidence"]
        )
        body.pop("request_id", None)
        body["request_id"] = "reconfigure-" + canonical_digest(body)
        return cls.from_dict(body)

    def identity_body(self) -> dict[str, object]:
        body = self.to_dict()
        body.pop("request_id")
        return body

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "request_id": self.request_id,
            "expected_membership_revision": self.expected_membership_revision,
            "expected_membership_digest": self.expected_membership_digest,
            "remove_member_id": self.remove_member_id,
            "evidence": self.evidence.to_dict(),
        }
