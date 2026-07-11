"""Immutable typed values crossing syncer orchestration boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class FragmentPlan:
    fragment_id: int
    parent_commit_id: str
    parent_commit_seq: int
    parent_frontier_digest: str
    selected_proposal_ids: tuple[str, ...]
    payload_sha256: tuple[str, ...]
    weights_hex: tuple[str, ...]
    aggregate_digest: str
    selection_digest: str

    def __post_init__(self) -> None:
        sizes = {
            len(self.selected_proposal_ids),
            len(self.payload_sha256),
            len(self.weights_hex),
        }
        if sizes != {len(self.selected_proposal_ids)} or not self.selected_proposal_ids:
            raise ValueError("fragment plan proposal fields must have equal non-zero length")

    @property
    def weights(self) -> tuple[float, ...]:
        return tuple(float.fromhex(value) for value in self.weights_hex)

    def identity(self) -> dict[str, object]:
        return {
            "fragment_id": self.fragment_id,
            "parent_commit_id": self.parent_commit_id,
            "parent_commit_seq": self.parent_commit_seq,
            "parent_frontier_digest": self.parent_frontier_digest,
            "selected_proposal_ids": list(self.selected_proposal_ids),
            "payload_sha256": list(self.payload_sha256),
            "weights": list(self.weights_hex),
            "aggregate_digest": self.aggregate_digest,
        }


@dataclass(frozen=True)
class FragmentComputation:
    aggregate: Any
    new_params: Any
    new_outer_state: Mapping[str, Any]
    aggregate_content_sha256: str
    params_content_sha256: str
    outer_state_content_sha256: str
    state_semantic_digest: str


@dataclass(frozen=True)
class TransitionAttempt:
    fragment_id: int
    selected_proposal_ids: tuple[str, ...]
    new_params: bytes
    new_outer_state: bytes
    aggregate_digest: str
    outer_optimizer_impl_digest: str
    request_id: str
    semantic_digest: str

