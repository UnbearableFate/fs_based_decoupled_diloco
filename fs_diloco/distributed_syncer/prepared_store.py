"""Marker-last publication and strict loading of prepared transition attempts."""

from __future__ import annotations

import hashlib

from fs_diloco.protocol.canonical_json import canonical_bytes, canonical_object
from fs_diloco.protocol.prepared_transition_v1 import (
    PreparedAttemptEnvelopeV1,
    PreparedFragmentResultV1,
)
from fs_diloco.protocol.schemas import ObjectRef

from .layout import DistributedLayout


def content_ref(key: str, data: bytes) -> ObjectRef:
    return ObjectRef(key=key, sha256=hashlib.sha256(data).hexdigest(), size=len(data))


def publish_prepared_attempt(
    facade,
    layout: DistributedLayout,
    *,
    result: PreparedFragmentResultV1,
    envelope: PreparedAttemptEnvelopeV1,
) -> None:
    if envelope.prepared_result_id != result.prepared_result_id:
        raise ValueError("attempt envelope references another prepared result")
    result_data = result.canonical_bytes()
    attempt_data = envelope.canonical_bytes()
    result_ref = content_ref(layout.result_key(result.prepared_result_id), result_data)
    attempt_ref = content_ref(layout.attempt_key(envelope.attempt_envelope_id), attempt_data)
    facade.put_immutable(result_ref.key, result_data, sha256=result_ref.sha256)
    facade.put_immutable(attempt_ref.key, attempt_data, sha256=attempt_ref.sha256)
    marker = {
        "schema": "duraloco-prepared-attempt-marker-v1",
        "work_order_id": result.work_order_id,
        "prepared_result_ref": result_ref.to_dict(),
        "attempt_envelope_ref": attempt_ref.to_dict(),
    }
    facade.put_immutable(
        layout.marker_key(result.work_order_id, envelope.attempt_envelope_id),
        canonical_bytes(marker),
    )


def _verified(backend, ref: ObjectRef) -> bytes:
    data = backend.get(ref.key)
    if len(data) != ref.size or hashlib.sha256(data).hexdigest() != ref.sha256:
        raise ValueError("prepared object reference verification failed")
    return data


def load_prepared_attempt(backend, marker_key: str):
    marker = canonical_object(backend.get(marker_key))
    if set(marker) != {
        "schema", "work_order_id", "prepared_result_ref", "attempt_envelope_ref"
    } or marker["schema"] != "duraloco-prepared-attempt-marker-v1":
        raise ValueError("invalid prepared attempt marker")
    result_ref = ObjectRef.from_dict(marker["prepared_result_ref"])
    attempt_ref = ObjectRef.from_dict(marker["attempt_envelope_ref"])
    result = PreparedFragmentResultV1.from_dict(canonical_object(_verified(backend, result_ref)))
    envelope = PreparedAttemptEnvelopeV1.from_dict(
        canonical_object(_verified(backend, attempt_ref))
    )
    if (
        result.work_order_id != marker["work_order_id"]
        or envelope.work_order_id != result.work_order_id
        or envelope.prepared_result_id != result.prepared_result_id
    ):
        raise ValueError("prepared marker lineage differs")
    return result, envelope
