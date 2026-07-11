"""Marker-last immutable learner publication with durable request identity."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Protocol, runtime_checkable

from fs_diloco.log.layout import LogLayout
from fs_diloco.protocol.canonical_json import canonical_bytes, canonical_digest
from fs_diloco.protocol.schemas import ObjectRef
from fs_diloco.storage.base import BytesLike, ObjectMetadata

from .interval import ContributionInterval


@runtime_checkable
class LearnerImmutableBackend(Protocol):
    """Deliberately excludes conditional replacement and the mutable head surface."""

    def put_immutable(
        self, key: str, data: BytesLike, *, sha256: str | None = None
    ) -> ObjectMetadata: ...

    def get(self, key: str, *, expected_version: str | None = None) -> bytes: ...

    def list_prefix(self, prefix: str) -> tuple[str, ...]: ...


@dataclass(frozen=True)
class PublicationResult:
    request_id: str
    request_digest: str
    proposal_id: str
    session_ref: ObjectRef
    payload_ref: ObjectRef
    request_ref: ObjectRef
    marker_ref: ObjectRef
    marker_bytes: bytes


_ABSENT = object()


class LearnerPublisher:
    """Publish session, payload, request evidence, then the discovery marker."""

    def __init__(self, backend: LearnerImmutableBackend, layout: LogLayout) -> None:
        self.backend = backend
        self.layout = layout

    @staticmethod
    def _identity_ref(metadata: ObjectMetadata) -> dict[str, object]:
        return {
            "key": metadata.key,
            "size": metadata.size,
            "sha256": metadata.sha256,
        }

    def publish(
        self,
        interval: ContributionInterval,
        payload: BytesLike,
        *,
        tensor_key: str,
        shape: tuple[int, ...],
        previous_interval_proposal_id: object = _ABSENT,
    ) -> PublicationResult:
        if not interval.closed:
            raise ValueError("only a closed interval can be published")
        if interval.session.run_id != self.layout.run_id or (
            interval.session.run_generation != self.layout.run_generation
        ):
            raise ValueError("interval session does not match publication layout")
        if not isinstance(payload, (bytes, bytearray, memoryview)):
            raise TypeError("proposal payload must be bytes-like")
        payload_bytes = bytes(payload)
        if not payload_bytes:
            raise ValueError("proposal payload cannot be empty")
        if not isinstance(tensor_key, str) or not tensor_key:
            raise ValueError("tensor_key must be non-empty")
        if not shape or any(type(value) is not int or value < 1 for value in shape):
            raise ValueError("shape must contain positive integers")
        if previous_interval_proposal_id is None:
            raise ValueError("explicit null predecessor is not canonical; omit it")
        if previous_interval_proposal_id is not _ABSENT and (
            not isinstance(previous_interval_proposal_id, str)
            or not previous_interval_proposal_id
        ):
            raise ValueError("previous interval proposal ID must be a non-empty string")

        session = interval.session
        session_metadata = self.backend.put_immutable(
            self.layout.learner_session_key(session.learner_id, session.session_id),
            session.canonical_bytes(),
            sha256=hashlib.sha256(session.canonical_bytes()).hexdigest(),
        )
        payload_digest = hashlib.sha256(payload_bytes).hexdigest()
        payload_metadata = self.backend.put_immutable(
            self.layout.proposal_payload_key(payload_digest),
            payload_bytes,
            sha256=payload_digest,
        )
        identity = {
            "operation": "publish_learner_interval",
            "interval": interval.identity_body(),
            "interval_digest": interval.interval_digest,
            "payload_ref": self._identity_ref(payload_metadata),
            "tensor_key": tensor_key,
            "shape": list(shape),
        }
        if previous_interval_proposal_id is not _ABSENT:
            identity["previous_interval_proposal_id"] = previous_interval_proposal_id
        request_id = "learner-publish-" + canonical_digest(
            {
                "run_id": session.run_id,
                "run_generation": session.run_generation,
                "learner_id": session.learner_id,
                "learner_session_id": session.session_id,
                "sequence": interval.sequence,
                "fragment_id": interval.fragment_id,
            }
        )
        request_digest = canonical_digest(identity)
        request_body = dict(identity)
        request_body.update(
            {
                "record_type": "learner_publication_request",
                "protocol_version": 2,
                "request_id": request_id,
                "request_digest": request_digest,
            }
        )
        request_bytes = canonical_bytes(request_body)
        request_metadata = self.backend.put_immutable(
            self.layout.learner_publication_request_key(
                session.learner_id,
                session.session_id,
                interval.sequence,
                interval.fragment_id,
            ),
            request_bytes,
            sha256=hashlib.sha256(request_bytes).hexdigest(),
        )
        marker_identity = {
            "record_type": "learner_publication_marker",
            "protocol_version": 2,
            "request_id": request_id,
            "request_digest": request_digest,
            "interval": interval.identity_body(),
            "interval_digest": interval.interval_digest,
            "payload_ref": self._identity_ref(payload_metadata),
            "request_ref": self._identity_ref(request_metadata),
            "tensor_key": tensor_key,
            "shape": list(shape),
        }
        if previous_interval_proposal_id is not _ABSENT:
            marker_identity["previous_interval_proposal_id"] = previous_interval_proposal_id
        proposal_id = "proposal-" + canonical_digest(marker_identity)
        marker_body = dict(marker_identity)
        marker_body["proposal_id"] = proposal_id
        marker_bytes = canonical_bytes(marker_body)
        marker_metadata = self.backend.put_immutable(
            self.layout.learner_publication_marker_key(
                session.learner_id,
                session.session_id,
                interval.sequence,
                interval.fragment_id,
            ),
            marker_bytes,
            sha256=hashlib.sha256(marker_bytes).hexdigest(),
        )
        return PublicationResult(
            request_id=request_id,
            request_digest=request_digest,
            proposal_id=proposal_id,
            session_ref=session_metadata.to_ref(),
            payload_ref=payload_metadata.to_ref(),
            request_ref=request_metadata.to_ref(),
            marker_ref=marker_metadata.to_ref(),
            marker_bytes=marker_bytes,
        )
