"""Immutable, head-anchored lifecycle snapshots.

A snapshot is derived state.  It becomes eligible as a replay accelerator only
after a committed ``snapshot_pin`` control transition references its exact
object identity.  The global head and its ancestry remain the sole authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from fs_diloco.protocol.canonical_json import canonical_bytes, canonical_digest
from fs_diloco.protocol.schemas import FrontierManifest, HeadManifest


SNAPSHOT_SCHEMA = "duraloco-lifecycle-snapshot-v1"


def snapshot_state_digest(head: HeadManifest, frontier: FrontierManifest) -> str:
    """Digest the complete optimizer/control state at one committed head."""

    return canonical_digest(
        {
            "head": head.to_dict(),
            "frontier": frontier.to_dict(),
        }
    )


@dataclass(frozen=True)
class CausalBaseSummary:
    commit_id: str
    commit_seq: int
    frontier_sha256: str
    optimizer_transition_count: int
    fragment_versions: tuple[tuple[int, int], ...]

    @classmethod
    def from_frontier(cls, frontier: FrontierManifest) -> "CausalBaseSummary":
        coordination = frontier.coordination
        optimizer_count = (
            coordination.optimizer_transition_count
            if coordination is not None
            else frontier.commit_seq
        )
        return cls(
            commit_id=frontier.commit_id,
            commit_seq=frontier.commit_seq,
            frontier_sha256=frontier.frontier_sha256,
            optimizer_transition_count=optimizer_count,
            fragment_versions=tuple(
                (fragment_id, fragment.version)
                for fragment_id, fragment in sorted(frontier.fragments.items())
            ),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CausalBaseSummary":
        required = {
            "commit_id",
            "commit_seq",
            "frontier_sha256",
            "optimizer_transition_count",
            "fragment_versions",
        }
        if not isinstance(payload, Mapping) or set(payload) != required:
            raise ValueError("causal base summary fields differ from contract")
        raw_versions = payload["fragment_versions"]
        if not isinstance(raw_versions, list):
            raise ValueError("fragment_versions must be a list")
        versions: list[tuple[int, int]] = []
        for item in raw_versions:
            if (
                not isinstance(item, list)
                or len(item) != 2
                or type(item[0]) is not int
                or item[0] < 0
                or type(item[1]) is not int
                or item[1] < 0
            ):
                raise ValueError("invalid fragment version summary")
            versions.append((item[0], item[1]))
        result = cls(
            commit_id=str(payload["commit_id"]),
            commit_seq=int(payload["commit_seq"]),
            frontier_sha256=str(payload["frontier_sha256"]),
            optimizer_transition_count=int(payload["optimizer_transition_count"]),
            fragment_versions=tuple(versions),
        )
        if not result.commit_id or result.commit_seq < 0:
            raise ValueError("invalid causal base identity")
        if len(result.frontier_sha256) != 64:
            raise ValueError("invalid causal base frontier digest")
        if result.optimizer_transition_count < 0:
            raise ValueError("invalid optimizer transition count")
        if tuple(sorted(result.fragment_versions)) != result.fragment_versions:
            raise ValueError("fragment version summary is not canonical")
        return result

    def to_dict(self) -> dict[str, object]:
        return {
            "commit_id": self.commit_id,
            "commit_seq": self.commit_seq,
            "frontier_sha256": self.frontier_sha256,
            "optimizer_transition_count": self.optimizer_transition_count,
            "fragment_versions": [list(item) for item in self.fragment_versions],
        }


@dataclass(frozen=True)
class SnapshotManifestV1:
    run_id: str
    run_generation: int
    covered_head: HeadManifest
    covered_frontier: FrontierManifest
    covered_state_digest: str
    causal_bases: tuple[CausalBaseSummary, ...]
    control_requests: tuple[tuple[str, str, int], ...]
    snapshot_id: str

    @classmethod
    def create(cls, replay) -> "SnapshotManifestV1":
        head = replay.loaded_head.manifest
        frontier = replay.head_frontier
        body = {
            "schema": SNAPSHOT_SCHEMA,
            "run_id": head.run_id,
            "run_generation": head.run_generation,
            "covered_head": head.to_dict(),
            "covered_frontier": frontier.to_dict(),
            "covered_state_digest": snapshot_state_digest(head, frontier),
            "causal_bases": [
                CausalBaseSummary.from_frontier(item).to_dict()
                for item in replay.frontiers
            ],
            "control_requests": [
                [request_id, digest, commit_seq]
                for request_id, (digest, commit_seq) in sorted(
                    replay.control_requests.items()
                )
            ],
        }
        return cls.from_dict(
            {**body, "snapshot_id": "snapshot-" + canonical_digest(body)}
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SnapshotManifestV1":
        required = {
            "schema",
            "run_id",
            "run_generation",
            "covered_head",
            "covered_frontier",
            "covered_state_digest",
            "causal_bases",
            "control_requests",
            "snapshot_id",
        }
        if not isinstance(payload, Mapping) or set(payload) != required:
            raise ValueError("snapshot fields differ from contract")
        if payload["schema"] != SNAPSHOT_SCHEMA:
            raise ValueError("unsupported snapshot schema")
        head = HeadManifest.from_dict(payload["covered_head"])
        frontier = FrontierManifest.from_dict(payload["covered_frontier"])
        if (
            head.run_id != payload["run_id"]
            or head.run_generation != payload["run_generation"]
            or head.commit_seq != frontier.commit_seq
            or head.commit_id != frontier.commit_id
            or head.fencing_epoch != frontier.fencing_epoch
            or head.frontier_ref.sha256 != frontier.frontier_sha256
        ):
            raise ValueError("snapshot covered head/frontier differ")
        expected_state = snapshot_state_digest(head, frontier)
        if payload["covered_state_digest"] != expected_state:
            raise ValueError("snapshot state digest differs")
        raw_bases = payload["causal_bases"]
        if not isinstance(raw_bases, list) or not raw_bases:
            raise ValueError("snapshot requires causal bases")
        bases = tuple(CausalBaseSummary.from_dict(item) for item in raw_bases)
        if tuple(item.commit_seq for item in bases) != tuple(range(len(bases))):
            raise ValueError("snapshot causal bases are not contiguous")
        if (
            bases[-1].commit_id != head.commit_id
            or bases[-1].commit_seq != head.commit_seq
            or bases[-1].frontier_sha256 != frontier.frontier_sha256
        ):
            raise ValueError("snapshot causal bases do not cover the head")
        raw_requests = payload["control_requests"]
        if not isinstance(raw_requests, list):
            raise ValueError("snapshot control_requests must be a list")
        requests: list[tuple[str, str, int]] = []
        for item in raw_requests:
            if (
                not isinstance(item, list)
                or len(item) != 3
                or not isinstance(item[0], str)
                or not item[0]
                or not isinstance(item[1], str)
                or len(item[1]) != 64
                or type(item[2]) is not int
                or item[2] < 1
            ):
                raise ValueError("invalid snapshot control request summary")
            requests.append((item[0], item[1], item[2]))
        if tuple(sorted(requests)) != tuple(requests):
            raise ValueError("snapshot control requests are not canonical")
        body = dict(payload)
        snapshot_id = body.pop("snapshot_id")
        expected_id = "snapshot-" + canonical_digest(body)
        if snapshot_id != expected_id:
            raise ValueError("snapshot identity differs from canonical content")
        return cls(
            run_id=str(payload["run_id"]),
            run_generation=int(payload["run_generation"]),
            covered_head=head,
            covered_frontier=frontier,
            covered_state_digest=expected_state,
            causal_bases=bases,
            control_requests=tuple(requests),
            snapshot_id=snapshot_id,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": SNAPSHOT_SCHEMA,
            "run_id": self.run_id,
            "run_generation": self.run_generation,
            "covered_head": self.covered_head.to_dict(),
            "covered_frontier": self.covered_frontier.to_dict(),
            "covered_state_digest": self.covered_state_digest,
            "causal_bases": [item.to_dict() for item in self.causal_bases],
            "control_requests": [list(item) for item in self.control_requests],
            "snapshot_id": self.snapshot_id,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())
