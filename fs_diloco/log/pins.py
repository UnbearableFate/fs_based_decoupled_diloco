"""Explicit immutable lifecycle roots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from fs_diloco.protocol.canonical_json import canonical_bytes, canonical_digest
from fs_diloco.protocol.schemas import ObjectRef


PIN_KINDS = {
    "active_fwo",
    "capsule",
    "experiment",
    "response_loss",
    "quarantine",
    "restore_point",
}


@dataclass(frozen=True)
class LifecyclePinV1:
    kind: str
    owner_id: str
    reason: str
    object_refs: tuple[ObjectRef, ...]
    pin_id: str

    @classmethod
    def create(cls, payload: Mapping[str, Any]) -> "LifecyclePinV1":
        body = dict(payload)
        body["schema"] = "duraloco-lifecycle-pin-v1"
        body["pin_id"] = "pin-" + canonical_digest(body)
        return cls.from_dict(body)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LifecyclePinV1":
        required = {"schema", "kind", "owner_id", "reason", "object_refs", "pin_id"}
        if not isinstance(payload, Mapping) or set(payload) != required:
            raise ValueError("pin fields differ from contract")
        if payload["schema"] != "duraloco-lifecycle-pin-v1" or payload["kind"] not in PIN_KINDS:
            raise ValueError("unsupported lifecycle pin")
        for field in ("owner_id", "reason"):
            if not isinstance(payload[field], str) or not payload[field]:
                raise ValueError(f"{field} must be non-empty")
        raw_refs = payload["object_refs"]
        if not isinstance(raw_refs, list) or not raw_refs:
            raise ValueError("pin object_refs must be non-empty")
        refs = tuple(ObjectRef.from_dict(item) for item in raw_refs)
        if tuple(sorted(refs, key=lambda item: item.key)) != refs:
            raise ValueError("pin object refs are not canonical")
        body = dict(payload)
        pin_id = body.pop("pin_id")
        if pin_id != "pin-" + canonical_digest(body):
            raise ValueError("pin identity differs")
        return cls(
            kind=payload["kind"],
            owner_id=payload["owner_id"],
            reason=payload["reason"],
            object_refs=refs,
            pin_id=pin_id,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "duraloco-lifecycle-pin-v1",
            "kind": self.kind,
            "owner_id": self.owner_id,
            "reason": self.reason,
            "object_refs": [item.to_dict() for item in self.object_refs],
            "pin_id": self.pin_id,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())


def publish_pin(backend, layout, pin: LifecyclePinV1):
    return backend.put_immutable(layout.pin_key(pin.pin_id), pin.canonical_bytes())
