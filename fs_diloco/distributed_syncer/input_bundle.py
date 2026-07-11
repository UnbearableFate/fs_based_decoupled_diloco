"""Canonical immutable input references accompanying one FWO."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from fs_diloco.log.codec import canonical_object
from fs_diloco.protocol.canonical_json import canonical_bytes, canonical_digest
from fs_diloco.protocol.schemas import ObjectRef
from fs_diloco.protocol.work_order_v1 import _strict, _string

from .layout import DistributedLayout


@dataclass(frozen=True)
class ProposalInputV1:
    proposal_id: str
    payload_ref: ObjectRef
    tensor_key: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProposalInputV1":
        _strict(payload, {"proposal_id", "payload_ref", "tensor_key"})
        return cls(
            proposal_id=_string(payload["proposal_id"], "proposal_id"),
            payload_ref=ObjectRef.from_dict(payload["payload_ref"]),
            tensor_key=_string(payload["tensor_key"], "tensor_key"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "payload_ref": self.payload_ref.to_dict(),
            "tensor_key": self.tensor_key,
        }


@dataclass(frozen=True)
class ExecutorInputBundleV1:
    schema: str
    bundle_id: str
    work_order_id: str
    parent_commit_id: str
    params_ref: ObjectRef
    outer_state_ref: ObjectRef
    proposals: tuple[ProposalInputV1, ...]

    SCHEMA = "duraloco-executor-input-bundle-v1"

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExecutorInputBundleV1":
        _strict(
            payload,
            {"schema", "bundle_id", "work_order_id", "parent_commit_id", "params_ref", "outer_state_ref", "proposals"},
        )
        if payload["schema"] != cls.SCHEMA:
            raise ValueError("unsupported executor input bundle")
        raw = payload["proposals"]
        if not isinstance(raw, list) or not raw:
            raise ValueError("input bundle requires proposals")
        proposals = tuple(ProposalInputV1.from_dict(item) for item in raw)
        ids = tuple(item.proposal_id for item in proposals)
        if ids != tuple(sorted(ids)) or len(ids) != len(set(ids)):
            raise ValueError("input bundle proposals must be unique and sorted")
        instance = cls(
            schema=cls.SCHEMA,
            bundle_id=_string(payload["bundle_id"], "bundle_id"),
            work_order_id=_string(payload["work_order_id"], "work_order_id"),
            parent_commit_id=_string(payload["parent_commit_id"], "parent_commit_id"),
            params_ref=ObjectRef.from_dict(payload["params_ref"]),
            outer_state_ref=ObjectRef.from_dict(payload["outer_state_ref"]),
            proposals=proposals,
        )
        body = instance.to_dict()
        body.pop("bundle_id")
        if instance.bundle_id != "fwinputs-" + canonical_digest(body):
            raise ValueError("input bundle identity differs")
        return instance

    @classmethod
    def create(cls, payload: Mapping[str, Any]) -> "ExecutorInputBundleV1":
        body = dict(payload)
        body.pop("bundle_id", None)
        return cls.from_dict({**body, "bundle_id": "fwinputs-" + canonical_digest(body)})

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "bundle_id": self.bundle_id,
            "work_order_id": self.work_order_id,
            "parent_commit_id": self.parent_commit_id,
            "params_ref": self.params_ref.to_dict(),
            "outer_state_ref": self.outer_state_ref.to_dict(),
            "proposals": [item.to_dict() for item in self.proposals],
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())


def publish_input_bundle(backend, layout: DistributedLayout, bundle: ExecutorInputBundleV1):
    return backend.put_immutable(layout.input_bundle_key(bundle.work_order_id), bundle.canonical_bytes())


def load_input_bundle(facade, layout: DistributedLayout, work_order_id: str) -> ExecutorInputBundleV1:
    bundle = ExecutorInputBundleV1.from_dict(
        canonical_object(facade.get(layout.input_bundle_key(work_order_id)))
    )
    if bundle.work_order_id != work_order_id:
        raise ValueError("input-bundle key and work-order identity differ")
    return bundle
