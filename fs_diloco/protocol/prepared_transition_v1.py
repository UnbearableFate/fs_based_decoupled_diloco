"""Inactive canonical prepared-result and attempt-envelope schemas for P06B."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Mapping

from .canonical_json import canonical_bytes, canonical_digest
from .schemas import ObjectRef
from .work_order_v1 import _digest, _integer, _strict, _string


@dataclass(frozen=True)
class PreparedFragmentResultV1:
    SCHEMA: ClassVar[str] = "duraloco-prepared-fragment-result-v1"
    schema: str
    prepared_result_id: str
    work_order_id: str
    parent_commit_id: str
    validated_input_digests: tuple[str, ...]
    aggregate_digest: str
    aggregate_content_sha256: str
    params_ref: ObjectRef
    outer_state_ref: ObjectRef
    state_semantic_digest: str
    numeric_implementation_digest: str

    FIELDS: ClassVar[set[str]] = {
        "schema",
        "prepared_result_id",
        "work_order_id",
        "parent_commit_id",
        "validated_input_digests",
        "aggregate_digest",
        "aggregate_content_sha256",
        "params_ref",
        "outer_state_ref",
        "state_semantic_digest",
        "numeric_implementation_digest",
    }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PreparedFragmentResultV1":
        _strict(payload, cls.FIELDS)
        if payload["schema"] != cls.SCHEMA:
            raise ValueError("unsupported prepared result schema")
        raw_inputs = payload["validated_input_digests"]
        if not isinstance(raw_inputs, list) or not raw_inputs:
            raise ValueError("validated_input_digests must be a non-empty list")
        inputs = tuple(_digest(item, "validated_input_digest") for item in raw_inputs)
        if tuple(sorted(inputs)) != inputs or len(set(inputs)) != len(inputs):
            raise ValueError("validated input digests must be unique and sorted")
        instance = cls(
            schema=cls.SCHEMA,
            prepared_result_id=_string(payload["prepared_result_id"], "prepared_result_id"),
            work_order_id=_string(payload["work_order_id"], "work_order_id"),
            parent_commit_id=_string(payload["parent_commit_id"], "parent_commit_id"),
            validated_input_digests=inputs,
            aggregate_digest=_digest(payload["aggregate_digest"], "aggregate_digest"),
            aggregate_content_sha256=_digest(
                payload["aggregate_content_sha256"], "aggregate_content_sha256"
            ),
            params_ref=ObjectRef.from_dict(payload["params_ref"]),
            outer_state_ref=ObjectRef.from_dict(payload["outer_state_ref"]),
            state_semantic_digest=_digest(
                payload["state_semantic_digest"], "state_semantic_digest"
            ),
            numeric_implementation_digest=_digest(
                payload["numeric_implementation_digest"], "numeric_implementation_digest"
            ),
        )
        expected = "pfr-" + canonical_digest(instance.identity_body())
        if instance.prepared_result_id != expected:
            raise ValueError("prepared_result_id does not match canonical content")
        return instance

    @classmethod
    def with_computed_id(cls, payload: Mapping[str, Any]) -> "PreparedFragmentResultV1":
        body = dict(payload)
        body.pop("prepared_result_id", None)
        body["prepared_result_id"] = "pfr-" + canonical_digest(body)
        return cls.from_dict(body)

    def identity_body(self) -> dict[str, object]:
        body = self.to_dict()
        body.pop("prepared_result_id")
        return body

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "prepared_result_id": self.prepared_result_id,
            "work_order_id": self.work_order_id,
            "parent_commit_id": self.parent_commit_id,
            "validated_input_digests": list(self.validated_input_digests),
            "aggregate_digest": self.aggregate_digest,
            "aggregate_content_sha256": self.aggregate_content_sha256,
            "params_ref": self.params_ref.to_dict(),
            "outer_state_ref": self.outer_state_ref.to_dict(),
            "state_semantic_digest": self.state_semantic_digest,
            "numeric_implementation_digest": self.numeric_implementation_digest,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())


@dataclass(frozen=True)
class PreparedAttemptEnvelopeV1:
    SCHEMA: ClassVar[str] = "duraloco-prepared-attempt-envelope-v1"
    schema: str
    attempt_envelope_id: str
    prepared_result_id: str
    work_order_id: str
    executor_id: str
    executor_session_id: str
    attempt_id: str
    membership_revision: int
    resource_evidence_digest: str

    FIELDS: ClassVar[set[str]] = {
        "schema",
        "attempt_envelope_id",
        "prepared_result_id",
        "work_order_id",
        "executor_id",
        "executor_session_id",
        "attempt_id",
        "membership_revision",
        "resource_evidence_digest",
    }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PreparedAttemptEnvelopeV1":
        _strict(payload, cls.FIELDS)
        if payload["schema"] != cls.SCHEMA:
            raise ValueError("unsupported prepared attempt schema")
        instance = cls(
            schema=cls.SCHEMA,
            attempt_envelope_id=_string(
                payload["attempt_envelope_id"], "attempt_envelope_id"
            ),
            prepared_result_id=_string(payload["prepared_result_id"], "prepared_result_id"),
            work_order_id=_string(payload["work_order_id"], "work_order_id"),
            executor_id=_string(payload["executor_id"], "executor_id"),
            executor_session_id=_string(
                payload["executor_session_id"], "executor_session_id"
            ),
            attempt_id=_string(payload["attempt_id"], "attempt_id"),
            membership_revision=_integer(payload["membership_revision"], "membership_revision"),
            resource_evidence_digest=_digest(
                payload["resource_evidence_digest"], "resource_evidence_digest"
            ),
        )
        expected = "pfa-" + canonical_digest(instance.identity_body())
        if instance.attempt_envelope_id != expected:
            raise ValueError("attempt_envelope_id does not match canonical content")
        return instance

    @classmethod
    def with_computed_id(cls, payload: Mapping[str, Any]) -> "PreparedAttemptEnvelopeV1":
        body = dict(payload)
        body.pop("attempt_envelope_id", None)
        body["attempt_envelope_id"] = "pfa-" + canonical_digest(body)
        return cls.from_dict(body)

    def identity_body(self) -> dict[str, object]:
        body = self.to_dict()
        body.pop("attempt_envelope_id")
        return body

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "attempt_envelope_id": self.attempt_envelope_id,
            "prepared_result_id": self.prepared_result_id,
            "work_order_id": self.work_order_id,
            "executor_id": self.executor_id,
            "executor_session_id": self.executor_session_id,
            "attempt_id": self.attempt_id,
            "membership_revision": self.membership_revision,
            "resource_evidence_digest": self.resource_evidence_digest,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())

