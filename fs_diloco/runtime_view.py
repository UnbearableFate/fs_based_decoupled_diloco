"""Immutable process-local view rebuilt exclusively from the committed log."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from fs_diloco.log.replay import ReplayResult, replay_log
from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.protocol.schemas import CommitManifest, FragmentState, FrontierManifest, StopProjection


Lineage = tuple[str, str, int]
IntervalBase = tuple[str, str, int, str, int]


@dataclass(frozen=True)
class RuntimeView:
    run_id: str
    run_generation: int
    commit_seq: int
    optimizer_transition_count: int
    commit_id: str
    fencing_epoch: int
    owner_id: str | None
    owner_session_id: str | None
    authoritative_stop: StopProjection | None
    frontier_sha256: str
    committed_state_digest: str
    fragments: Mapping[int, FragmentState]
    consumed_proposal_ids: frozenset[str]
    consumed_interval_bases: frozenset[IntervalBase]
    last_committed_sequences: Mapping[Lineage, int]
    commit_sequences_by_id: Mapping[str, int]
    frontier_digests_by_commit: Mapping[str, str]
    fragment_versions_by_commit: Mapping[str, Mapping[int, int]]
    scheduler_cursor: int
    total_seen_tokens: int
    view_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "fragments", MappingProxyType(dict(self.fragments)))
        object.__setattr__(
            self,
            "last_committed_sequences",
            MappingProxyType(dict(self.last_committed_sequences)),
        )
        object.__setattr__(
            self,
            "commit_sequences_by_id",
            MappingProxyType(dict(self.commit_sequences_by_id)),
        )
        object.__setattr__(
            self,
            "frontier_digests_by_commit",
            MappingProxyType(dict(self.frontier_digests_by_commit)),
        )
        object.__setattr__(
            self,
            "fragment_versions_by_commit",
            MappingProxyType(
                {
                    key: MappingProxyType(dict(value))
                    for key, value in self.fragment_versions_by_commit.items()
                }
            ),
        )
        object.__setattr__(self, "consumed_proposal_ids", frozenset(self.consumed_proposal_ids))
        object.__setattr__(self, "consumed_interval_bases", frozenset(self.consumed_interval_bases))

    @property
    def ancestor_commit_ids(self) -> frozenset[str]:
        return frozenset(self.commit_sequences_by_id)

    @property
    def fragment_versions(self) -> Mapping[int, int]:
        return MappingProxyType(
            {fragment_id: state.version for fragment_id, state in self.fragments.items()}
        )

    @classmethod
    def from_replay(cls, replay: ReplayResult) -> "RuntimeView":
        head = replay.head_frontier
        commit_sequences = {item.commit_id: item.commit_seq for item in replay.frontiers}
        frontier_digests = {
            item.commit_id: item.frontier_sha256 for item in replay.frontiers
        }
        fragment_versions = {
            item.commit_id: {
                fragment_id: state.version for fragment_id, state in item.fragments.items()
            }
            for item in replay.frontiers
        }
        sequences: dict[Lineage, int] = {}
        intervals: set[IntervalBase] = set()
        total_seen_tokens = 0
        for proposal in replay.proposals.values():
            session = getattr(proposal, "learner_session_id", None)
            if session is None:
                session = getattr(proposal, "session_id")
            lineage = (proposal.learner_id, session, proposal.fragment_id)
            sequences[lineage] = max(sequences.get(lineage, -1), proposal.sequence)
            intervals.add(
                (
                    *lineage,
                    proposal.base_commit_id,
                    proposal.base_fragment_version,
                )
            )
            total_seen_tokens += int(
                getattr(proposal, "target_tokens_since_base", getattr(proposal, "target_tokens", 0))
            )
        coordination = head.coordination
        optimizer_transition_count = (
            coordination.optimizer_transition_count
            if coordination is not None
            else sum(isinstance(item, CommitManifest) for item in replay.commits)
        )
        identity = {
            "run_id": head.run_id,
            "run_generation": head.run_generation,
            "commit_seq": head.commit_seq,
            "optimizer_transition_count": optimizer_transition_count,
            "commit_id": head.commit_id,
            "fencing_epoch": head.fencing_epoch,
            "owner_id": coordination.owner_id if coordination is not None else None,
            "owner_session_id": (
                coordination.owner_session_id if coordination is not None else None
            ),
            "authoritative_stop": (
                coordination.stop.to_dict()
                if coordination is not None and coordination.stop is not None
                else None
            ),
            "frontier_sha256": head.frontier_sha256,
            "committed_state_digest": replay.committed_state_digest,
            "fragments": {
                str(key): value.to_dict() for key, value in sorted(head.fragments.items())
            },
            "consumed_proposal_ids": sorted(replay.consumption),
            "consumed_interval_bases": [list(item) for item in sorted(intervals)],
            "last_committed_sequences": [
                [*key, value] for key, value in sorted(sequences.items())
            ],
            "scheduler_cursor": head.scheduler_state["next_fragment_cursor"],
            "total_seen_tokens": total_seen_tokens,
        }
        return cls(
            run_id=head.run_id,
            run_generation=head.run_generation,
            commit_seq=head.commit_seq,
            optimizer_transition_count=optimizer_transition_count,
            commit_id=head.commit_id,
            fencing_epoch=head.fencing_epoch,
            owner_id=coordination.owner_id if coordination is not None else None,
            owner_session_id=(
                coordination.owner_session_id if coordination is not None else None
            ),
            authoritative_stop=(coordination.stop if coordination is not None else None),
            frontier_sha256=head.frontier_sha256,
            committed_state_digest=replay.committed_state_digest,
            fragments=head.fragments,
            consumed_proposal_ids=frozenset(replay.consumption),
            consumed_interval_bases=frozenset(intervals),
            last_committed_sequences=sequences,
            commit_sequences_by_id=commit_sequences,
            frontier_digests_by_commit=frontier_digests,
            fragment_versions_by_commit=fragment_versions,
            scheduler_cursor=head.scheduler_state["next_fragment_cursor"],
            total_seen_tokens=total_seen_tokens,
            view_digest=canonical_digest(identity),
        )


def build_runtime_view(log, *, force_full: bool = False) -> RuntimeView:
    if hasattr(log, "replay"):
        replay = log.replay(force_full=force_full)
    else:
        replay = replay_log(log.transactional if hasattr(log, "transactional") else log)
    return RuntimeView.from_replay(replay)
