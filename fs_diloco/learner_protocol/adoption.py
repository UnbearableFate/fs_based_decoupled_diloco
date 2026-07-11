"""Boundary-only adoption and inner-optimizer policy kernel."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Mapping

from fs_diloco.protocol.canonical_json import canonical_digest

from .interval import AuthorityFrontier


class AdoptionPhase(str, Enum):
    READY = "ready"
    INTERVAL_OPEN = "interval_open"
    PUBLISHED_WAIT = "published_wait"
    STOPPED = "stopped"
    NO_PROGRESS = "no_progress"


class OptimizerAdoptionPolicy(str, Enum):
    RESET_ALL = "reset_all"
    RESET_UPDATED_FRAGMENT = "reset_updated_fragment"
    PRESERVE = "preserve"


@dataclass(frozen=True)
class AdoptionKernel:
    adopted: AuthorityFrontier
    phase: AdoptionPhase = AdoptionPhase.READY
    interval_digest: str | None = None
    proposal_id: str | None = None
    pending: AuthorityFrontier | None = None
    stop_reason: str | None = None
    stop_commit_seq: int | None = None
    no_progress_reason: str | None = None

    @classmethod
    def bootstrap(cls, frontier: AuthorityFrontier) -> "AdoptionKernel":
        return cls(adopted=frontier)

    def _require_nonterminal(self) -> None:
        if self.phase in {AdoptionPhase.STOPPED, AdoptionPhase.NO_PROGRESS}:
            raise ValueError("terminal adoption state cannot transition")

    def begin_interval(self, interval_digest: str) -> "AdoptionKernel":
        self._require_nonterminal()
        if self.phase is not AdoptionPhase.READY:
            raise ValueError("an interval is already active")
        if not isinstance(interval_digest, str) or not interval_digest:
            raise ValueError("interval digest must be non-empty")
        return replace(
            self,
            phase=AdoptionPhase.INTERVAL_OPEN,
            interval_digest=interval_digest,
            proposal_id=None,
            pending=None,
        )

    def observe_successor(self, frontier: AuthorityFrontier) -> "AdoptionKernel":
        self._require_nonterminal()
        if frontier.commit_seq <= self.adopted.commit_seq:
            return self
        if self.phase is AdoptionPhase.READY:
            return replace(self, adopted=frontier, pending=None)
        pending = self.pending
        if pending is None or frontier.commit_seq > pending.commit_seq:
            pending = frontier
        return replace(self, pending=pending)

    def mark_published(self, proposal_id: str) -> "AdoptionKernel":
        self._require_nonterminal()
        if self.phase is not AdoptionPhase.INTERVAL_OPEN:
            raise ValueError("publication requires an open interval")
        if not isinstance(proposal_id, str) or not proposal_id:
            raise ValueError("proposal_id must be non-empty")
        return replace(
            self,
            phase=AdoptionPhase.PUBLISHED_WAIT,
            proposal_id=proposal_id,
        )

    def adopt_successor(self) -> "AdoptionKernel":
        self._require_nonterminal()
        if self.phase is not AdoptionPhase.PUBLISHED_WAIT:
            raise ValueError("successor adoption requires a published interval")
        if self.pending is None:
            raise ValueError("no committed successor is pending")
        return AdoptionKernel(adopted=self.pending)

    def observe_stop(self, reason: str, *, commit_seq: int) -> "AdoptionKernel":
        if self.phase is AdoptionPhase.STOPPED:
            return self
        if not isinstance(reason, str) or not reason:
            raise ValueError("stop reason must be non-empty")
        if type(commit_seq) is not int or commit_seq < self.adopted.commit_seq:
            raise ValueError("stop commit sequence precedes adopted authority")
        return replace(
            self,
            phase=AdoptionPhase.STOPPED,
            stop_reason=reason,
            stop_commit_seq=commit_seq,
            pending=None,
        )

    def declare_no_progress(self, reason: str) -> "AdoptionKernel":
        self._require_nonterminal()
        if self.phase is not AdoptionPhase.PUBLISHED_WAIT:
            raise ValueError("no-progress is valid only after publication")
        if not isinstance(reason, str) or not reason:
            raise ValueError("no-progress reason must be non-empty")
        return replace(
            self,
            phase=AdoptionPhase.NO_PROGRESS,
            no_progress_reason=reason,
            pending=None,
        )

    @property
    def state_digest(self) -> str:
        body: dict[str, object] = {
            "adopted": self.adopted.to_dict(),
            "phase": self.phase.value,
        }
        for key in (
            "interval_digest",
            "proposal_id",
            "stop_reason",
            "stop_commit_seq",
            "no_progress_reason",
        ):
            value = getattr(self, key)
            if value is not None:
                body[key] = value
        if self.pending is not None:
            body["pending"] = self.pending.to_dict()
        return canonical_digest(body)


def optimizer_reset_targets(
    policy: OptimizerAdoptionPolicy | str,
    changed_fragments: set[int] | frozenset[int],
    parameter_fragments: Mapping[str, int],
) -> frozenset[str]:
    selected = OptimizerAdoptionPolicy(policy)
    if selected is OptimizerAdoptionPolicy.PRESERVE:
        return frozenset()
    if selected is OptimizerAdoptionPolicy.RESET_ALL:
        return frozenset(parameter_fragments)
    return frozenset(
        name for name, fragment in parameter_fragments.items() if fragment in changed_fragments
    )
