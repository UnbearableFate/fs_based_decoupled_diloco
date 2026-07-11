"""Warm learner recovery derived from immutable publication facts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from fs_diloco.log.layout import LogLayout
from fs_diloco.protocol.canonical_json import canonical_digest

from .publication import LearnerImmutableBackend
from .session import LearnerSession


@dataclass(frozen=True)
class WarmRecoveryReport:
    new_session: LearnerSession
    published_intervals: int
    committed_intervals: int
    lost_tokens: int
    repeated_tokens_estimate: int
    next_sequence: int
    warm_not_exact: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "new_session": self.new_session.to_dict(),
            "published_intervals": self.published_intervals,
            "committed_intervals": self.committed_intervals,
            "lost_tokens": self.lost_tokens,
            "repeated_tokens_estimate": self.repeated_tokens_estimate,
            "next_sequence": self.next_sequence,
            "warm_not_exact": self.warm_not_exact,
        }


def recover_learner(
    backend: LearnerImmutableBackend,
    layout: LogLayout,
    *,
    learner_id: str,
    committed_proposal_ids: frozenset[str],
    new_session_id: str | None = None,
) -> WarmRecoveryReport:
    prefix = f"{layout.learner_publication_prefix}{learner_id}/"
    markers = [key for key in backend.list_prefix(prefix) if "/markers/" in key]
    published = 0
    committed = 0
    lost_tokens = 0
    identities: set[tuple[str, int, int]] = set()
    for key in sorted(markers):
        try:
            body = json.loads(backend.get(key))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid learner publication marker: {key}") from exc
        if not isinstance(body, dict) or body.get("record_type") != "learner_publication_marker":
            raise ValueError(f"invalid learner publication marker schema: {key}")
        required = {
            "record_type",
            "protocol_version",
            "request_id",
            "request_digest",
            "interval",
            "interval_digest",
            "payload_ref",
            "request_ref",
            "tensor_key",
            "shape",
            "proposal_id",
        }
        found = set(body)
        if found != required and found != required | {"previous_interval_proposal_id"}:
            raise ValueError(f"learner publication marker fields differ: {key}")
        interval = body.get("interval")
        if not isinstance(interval, dict) or interval.get("learner_id") != learner_id:
            raise ValueError(f"publication marker learner identity mismatch: {key}")
        identity = (
            str(interval.get("learner_session_id")),
            int(interval.get("sequence", -1)),
            int(interval.get("fragment_id", -1)),
        )
        if identity in identities:
            raise ValueError("duplicate learner publication identity")
        identities.add(identity)
        proposal_id = body.get("proposal_id")
        if not isinstance(proposal_id, str) or not proposal_id:
            raise ValueError("publication marker lacks proposal_id")
        tokens = int(interval.get("target_tokens", -1))
        if tokens < 1:
            raise ValueError("publication marker target_tokens must be positive")
        if body.get("interval_digest") != canonical_digest(interval):
            raise ValueError("publication marker interval digest differs")
        marker_identity = dict(body)
        marker_identity.pop("proposal_id")
        if proposal_id != "proposal-" + canonical_digest(marker_identity):
            raise ValueError("publication marker proposal identity differs")
        request_ref = body.get("request_ref")
        if not isinstance(request_ref, dict) or set(request_ref) != {"key", "size", "sha256"}:
            raise ValueError("publication marker request ref differs")
        request_bytes = backend.get(str(request_ref["key"]))
        if len(request_bytes) != int(request_ref["size"]) or (
            hashlib.sha256(request_bytes).hexdigest() != request_ref["sha256"]
        ):
            raise ValueError("publication request object identity differs")
        try:
            request = json.loads(request_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("publication request object is malformed") from exc
        if not isinstance(request, dict):
            raise ValueError("publication request object is not a mapping")
        request_identity = dict(request)
        for field in ("record_type", "protocol_version", "request_id", "request_digest"):
            request_identity.pop(field, None)
        if request.get("request_id") != body.get("request_id") or (
            request.get("request_digest") != body.get("request_digest")
        ):
            raise ValueError("publication request and marker identity differ")
        if request.get("request_digest") != canonical_digest(request_identity):
            raise ValueError("publication request digest differs")
        session_record = LearnerSession(
            run_id=layout.run_id,
            run_generation=layout.run_generation,
            learner_id=learner_id,
            session_id=identity[0],
        )
        session_bytes = backend.get(layout.learner_session_key(learner_id, identity[0]))
        if session_bytes != session_record.canonical_bytes():
            raise ValueError("learner session record differs from publication marker")
        published += 1
        if proposal_id in committed_proposal_ids:
            committed += 1
        else:
            lost_tokens += tokens
    new_session = LearnerSession.new(
        layout.run_id,
        layout.run_generation,
        learner_id,
        session_id=new_session_id,
    )
    return WarmRecoveryReport(
        new_session=new_session,
        published_intervals=published,
        committed_intervals=committed,
        lost_tokens=lost_tokens,
        repeated_tokens_estimate=0,
        next_sequence=1,
    )
