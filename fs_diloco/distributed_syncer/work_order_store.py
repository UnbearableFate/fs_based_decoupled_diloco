"""Immutable authoritative work-order publication and verification."""

from __future__ import annotations

from fs_diloco.protocol.work_order_v1 import FragmentWorkOrderV1

from .layout import DistributedLayout


def publish_work_order(backend, layout: DistributedLayout, order: FragmentWorkOrderV1):
    return backend.put_immutable(
        layout.work_order_key(order.work_order_id), order.canonical_bytes()
    )


def load_work_order(backend, layout: DistributedLayout, work_order_id: str) -> FragmentWorkOrderV1:
    from fs_diloco.protocol.canonical_json import canonical_object

    payload = canonical_object(backend.get(layout.work_order_key(work_order_id)))
    order = FragmentWorkOrderV1.from_dict(payload)
    if order.work_order_id != work_order_id:
        raise ValueError("work-order key and identity differ")
    return order
