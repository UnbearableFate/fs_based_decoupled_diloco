"""Inactive canonical Fragment Work Order schema frozen by P06A."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, ClassVar, Mapping

from .canonical_json import canonical_bytes, canonical_digest


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _digest(value: Any, field: str) -> str:
    value = _string(value, field)
    if _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _integer(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _strict(payload: Mapping[str, Any], expected: set[str]) -> None:
    if not isinstance(payload, Mapping):
        raise ValueError("work order must be a mapping")
    missing = expected - set(payload)
    unknown = set(payload) - expected
    if missing or unknown:
        raise ValueError(f"work order field mismatch: missing={sorted(missing)} unknown={sorted(unknown)}")


@dataclass(frozen=True)
class WorkOrderProposalV1:
    proposal_id: str
    payload_sha256: str
    target_tokens: int
    base_fragment_version: int
    weight_hex: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorkOrderProposalV1":
        expected = {
            "proposal_id",
            "payload_sha256",
            "target_tokens",
            "base_fragment_version",
            "weight_hex",
        }
        _strict(payload, expected)
        weight_hex = _string(payload["weight_hex"], "weight_hex")
        weight = float.fromhex(weight_hex)
        if not math.isfinite(weight) or weight <= 0.0 or weight.hex() != weight_hex:
            raise ValueError("weight_hex must be a positive canonical float.hex string")
        target_tokens = _integer(payload["target_tokens"], "target_tokens")
        if target_tokens < 1:
            raise ValueError("target_tokens must be positive")
        return cls(
            proposal_id=_string(payload["proposal_id"], "proposal_id"),
            payload_sha256=_digest(payload["payload_sha256"], "payload_sha256"),
            target_tokens=target_tokens,
            base_fragment_version=_integer(
                payload["base_fragment_version"], "base_fragment_version"
            ),
            weight_hex=weight_hex,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "payload_sha256": self.payload_sha256,
            "target_tokens": self.target_tokens,
            "base_fragment_version": self.base_fragment_version,
            "weight_hex": self.weight_hex,
        }


@dataclass(frozen=True)
class FragmentWorkOrderV1:
    SCHEMA: ClassVar[str] = "duraloco-fragment-work-order-v1"
    schema: str
    work_order_id: str
    run_id: str
    run_generation: int
    parent_commit_id: str
    parent_frontier_digest: str
    fragment_id: int
    committer_fencing_epoch: int
    membership_revision: int
    ownership_digest: str
    proposals: tuple[WorkOrderProposalV1, ...]
    aggregation_policy_digest: str
    outer_optimizer_impl_digest: str
    execution_backend_digest: str
    parameter_index_digest: str
    fragment_layout_digest: str

    FIELDS: ClassVar[set[str]] = {
        "schema",
        "work_order_id",
        "run_id",
        "run_generation",
        "parent_commit_id",
        "parent_frontier_digest",
        "fragment_id",
        "committer_fencing_epoch",
        "membership_revision",
        "ownership_digest",
        "proposals",
        "aggregation_policy_digest",
        "outer_optimizer_impl_digest",
        "execution_backend_digest",
        "parameter_index_digest",
        "fragment_layout_digest",
    }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FragmentWorkOrderV1":
        _strict(payload, cls.FIELDS)
        if payload["schema"] != cls.SCHEMA:
            raise ValueError("unsupported work order schema")
        raw_proposals = payload["proposals"]
        if not isinstance(raw_proposals, list) or not raw_proposals:
            raise ValueError("work order proposals must be a non-empty list")
        proposals = tuple(WorkOrderProposalV1.from_dict(item) for item in raw_proposals)
        proposal_ids = tuple(item.proposal_id for item in proposals)
        if tuple(sorted(proposal_ids)) != proposal_ids or len(set(proposal_ids)) != len(proposal_ids):
            raise ValueError("work order proposals must be unique and sorted by proposal_id")
        instance = cls(
            schema=cls.SCHEMA,
            work_order_id=_string(payload["work_order_id"], "work_order_id"),
            run_id=_string(payload["run_id"], "run_id"),
            run_generation=_integer(payload["run_generation"], "run_generation"),
            parent_commit_id=_string(payload["parent_commit_id"], "parent_commit_id"),
            parent_frontier_digest=_digest(
                payload["parent_frontier_digest"], "parent_frontier_digest"
            ),
            fragment_id=_integer(payload["fragment_id"], "fragment_id"),
            committer_fencing_epoch=_integer(
                payload["committer_fencing_epoch"], "committer_fencing_epoch"
            ),
            membership_revision=_integer(payload["membership_revision"], "membership_revision"),
            ownership_digest=_digest(payload["ownership_digest"], "ownership_digest"),
            proposals=proposals,
            aggregation_policy_digest=_digest(
                payload["aggregation_policy_digest"], "aggregation_policy_digest"
            ),
            outer_optimizer_impl_digest=_digest(
                payload["outer_optimizer_impl_digest"], "outer_optimizer_impl_digest"
            ),
            execution_backend_digest=_digest(
                payload["execution_backend_digest"], "execution_backend_digest"
            ),
            parameter_index_digest=_digest(
                payload["parameter_index_digest"], "parameter_index_digest"
            ),
            fragment_layout_digest=_digest(
                payload["fragment_layout_digest"], "fragment_layout_digest"
            ),
        )
        expected = "fwo-" + canonical_digest(instance.identity_body())
        if instance.work_order_id != expected:
            raise ValueError("work_order_id does not match canonical content")
        return instance

    @classmethod
    def with_computed_id(cls, payload: Mapping[str, Any]) -> "FragmentWorkOrderV1":
        body = dict(payload)
        body.pop("work_order_id", None)
        body["work_order_id"] = "fwo-" + canonical_digest(body)
        return cls.from_dict(body)

    def identity_body(self) -> dict[str, object]:
        body = self.to_dict()
        body.pop("work_order_id")
        return body

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "work_order_id": self.work_order_id,
            "run_id": self.run_id,
            "run_generation": self.run_generation,
            "parent_commit_id": self.parent_commit_id,
            "parent_frontier_digest": self.parent_frontier_digest,
            "fragment_id": self.fragment_id,
            "committer_fencing_epoch": self.committer_fencing_epoch,
            "membership_revision": self.membership_revision,
            "ownership_digest": self.ownership_digest,
            "proposals": [item.to_dict() for item in self.proposals],
            "aggregation_policy_digest": self.aggregation_policy_digest,
            "outer_optimizer_impl_digest": self.outer_optimizer_impl_digest,
            "execution_backend_digest": self.execution_backend_digest,
            "parameter_index_digest": self.parameter_index_digest,
            "fragment_layout_digest": self.fragment_layout_digest,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())
