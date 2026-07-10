"""Small Protocol v2 invariant helpers used before a durable log exists."""

from __future__ import annotations

from dataclasses import dataclass, field

from .canonical_json import canonical_digest
from .errors import ErrorCategory, ProtocolError
from .schemas import ProposalManifest


@dataclass
class IdentityRegistry:
    """Detect one protocol identity mapping to different canonical content."""

    _proposal_bodies: dict[str, str] = field(default_factory=dict)

    def check(self, proposal: ProposalManifest) -> bool:
        digest = canonical_digest(proposal.identity_body())
        existing = self._proposal_bodies.get(proposal.proposal_id)
        if existing is None:
            return True
        if existing != digest:
            raise ProtocolError(
                "IDENTITY_CONTENT_CONFLICT",
                f"proposal {proposal.proposal_id} maps to multiple canonical bodies",
                category=ErrorCategory.FATAL,
                details={"expected_digest": existing, "observed_digest": digest},
            )
        return False

    def observe(self, proposal: ProposalManifest) -> bool:
        is_new = self.check(proposal)
        if is_new:
            self._proposal_bodies[proposal.proposal_id] = canonical_digest(
                proposal.identity_body()
            )
        return is_new


def assert_unique_selected(proposal_ids: list[str] | tuple[str, ...]) -> None:
    if len(proposal_ids) != len(set(proposal_ids)):
        raise ProtocolError(
            "DUPLICATE_SELECTION",
            "the same proposal appears more than once in a tentative transition",
            category=ErrorCategory.FATAL,
        )
