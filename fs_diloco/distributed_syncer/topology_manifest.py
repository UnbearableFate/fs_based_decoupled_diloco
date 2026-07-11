"""Strict auditable role placement for no-dedicated-syncer runs."""

from __future__ import annotations

from dataclasses import dataclass

from fs_diloco.protocol.canonical_json import canonical_digest


@dataclass(frozen=True)
class TopologyManifestV1:
    learner_nodes: tuple[str, ...]
    learner_ids: tuple[str, ...]
    executor_ids: tuple[str, ...]
    committer_candidates: tuple[str, ...]
    dedicated_syncer_nodes: int = 0

    def __post_init__(self) -> None:
        if self.dedicated_syncer_nodes != 0:
            raise ValueError("distributed topology cannot allocate a dedicated syncer")
        if not self.learner_nodes or len(self.learner_nodes) != len(self.learner_ids):
            raise ValueError("one learner identity is required per learner node")
        if len(self.executor_ids) != len(self.learner_nodes):
            raise ValueError("one LFE is required per learner node")
        for values in (
            self.learner_nodes, self.learner_ids, self.executor_ids, self.committer_candidates
        ):
            if tuple(sorted(values)) != values or len(set(values)) != len(values):
                raise ValueError("topology identities must be unique and sorted")

    def to_dict(self) -> dict[str, object]:
        body = {
            "schema": "duraloco-distributed-topology-v1",
            "learner_nodes": list(self.learner_nodes),
            "learner_ids": list(self.learner_ids),
            "executor_ids": list(self.executor_ids),
            "committer_candidates": list(self.committer_candidates),
            "dedicated_syncer_nodes": self.dedicated_syncer_nodes,
        }
        return {**body, "topology_digest": canonical_digest(body)}
