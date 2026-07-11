"""Immutable authoritative work-order publication and verification."""

from __future__ import annotations

from fs_diloco.protocol.work_order_v1 import FragmentWorkOrderV1
from fs_diloco.protocol.work_order_v2 import RedundantFragmentWorkOrderV2
from fs_diloco.log.codec import canonical_object

from .layout import DistributedLayout


WorkOrder = FragmentWorkOrderV1 | RedundantFragmentWorkOrderV2


def publish_work_order(backend, layout: DistributedLayout, order: WorkOrder):
    return backend.put_immutable(
        layout.work_order_key(order.work_order_id), order.canonical_bytes()
    )


def load_work_order(backend, layout: DistributedLayout, work_order_id: str) -> WorkOrder:
    payload = canonical_object(backend.get(layout.work_order_key(work_order_id)))
    if payload.get("schema") == FragmentWorkOrderV1.SCHEMA:
        order: WorkOrder = FragmentWorkOrderV1.from_dict(payload)
    elif payload.get("schema") == RedundantFragmentWorkOrderV2.SCHEMA:
        order = RedundantFragmentWorkOrderV2.from_dict(payload)
    else:
        raise ValueError("unsupported work-order schema")
    if order.work_order_id != work_order_id:
        raise ValueError("work-order key and identity differ")
    return order
