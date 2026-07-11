"""Strict P06C redundant Fragment Work Order schema."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Mapping

from fs_diloco.distributed_syncer.hedge_policy import RedundancyPolicyV1

from .canonical_json import canonical_bytes, canonical_digest
from .work_order_v1 import FragmentWorkOrderV1, _strict, _string


@dataclass(frozen=True)
class RedundantFragmentWorkOrderV2:
    SCHEMA: ClassVar[str] = "duraloco-redundant-fragment-work-order-v2"
    schema: str
    work_order_id: str
    base_work_order: FragmentWorkOrderV1
    owner_member_ids: tuple[str, str]
    redundancy_policy: RedundancyPolicyV1

    FIELDS: ClassVar[set[str]] = {
        "schema",
        "work_order_id",
        "base_work_order",
        "owner_member_ids",
        "redundancy_policy",
    }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RedundantFragmentWorkOrderV2":
        _strict(payload, cls.FIELDS)
        if payload["schema"] != cls.SCHEMA:
            raise ValueError("unsupported redundant work-order schema")
        raw_owners = payload["owner_member_ids"]
        if not isinstance(raw_owners, list) or len(raw_owners) != 2:
            raise ValueError("redundant work order requires primary and backup")
        owners = tuple(_string(value, "owner_member_id") for value in raw_owners)
        if len(set(owners)) != 2:
            raise ValueError("primary and backup must be distinct")
        instance = cls(
            schema=cls.SCHEMA,
            work_order_id=_string(payload["work_order_id"], "work_order_id"),
            base_work_order=FragmentWorkOrderV1.from_dict(payload["base_work_order"]),
            owner_member_ids=(owners[0], owners[1]),
            redundancy_policy=RedundancyPolicyV1.from_dict(payload["redundancy_policy"]),
        )
        expected = "fwo2-" + canonical_digest(instance.identity_body())
        if instance.work_order_id != expected:
            raise ValueError("redundant work_order_id does not match canonical content")
        return instance

    @classmethod
    def with_computed_id(
        cls, payload: Mapping[str, Any]
    ) -> "RedundantFragmentWorkOrderV2":
        body = dict(payload)
        body.pop("work_order_id", None)
        body["work_order_id"] = "fwo2-" + canonical_digest(body)
        return cls.from_dict(body)

    def identity_body(self) -> dict[str, object]:
        payload = self.to_dict()
        payload.pop("work_order_id")
        return payload

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "work_order_id": self.work_order_id,
            "base_work_order": self.base_work_order.to_dict(),
            "owner_member_ids": list(self.owner_member_ids),
            "redundancy_policy": self.redundancy_policy.to_dict(),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())

    @property
    def primary_member_id(self) -> str:
        return self.owner_member_ids[0]

    @property
    def backup_member_id(self) -> str:
        return self.owner_member_ids[1]

    def __getattr__(self, name: str):
        # Executor/planner data fields are exactly the strict V1 base identity.
        if name.startswith("__"):
            raise AttributeError(name)
        return getattr(self.base_work_order, name)
