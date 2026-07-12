"""Immutable, head-anchored lifecycle snapshots.

A snapshot is derived state.  It becomes eligible as a replay accelerator only
after a committed ``snapshot_pin`` control transition references its exact
object identity.  The global head and its ancestry remain the sole authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
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
    embedded_objects: tuple[tuple[str, str, int, bytes], ...]
    proposal_payloads: tuple[tuple[str, str, int], ...]
    params_numels: tuple[tuple[str, str, int, int], ...]
    outer_numels: tuple[tuple[str, str, int, tuple[int, ...]], ...]
    snapshot_id: str

    @classmethod
    def create(
        cls,
        replay,
        *,
        embedded_objects: Mapping[str, bytes] | None = None,
        replay_cache=None,
    ) -> "SnapshotManifestV1":
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
            "embedded_objects": [
                [
                    key,
                    hashlib.sha256(data).hexdigest(),
                    len(data),
                    base64.b64encode(data).decode("ascii"),
                ]
                for key, data in sorted((embedded_objects or {}).items())
            ],
            "proposal_payloads": [
                list(item)
                for item in sorted(
                    replay_cache.proposal_payloads if replay_cache is not None else ()
                )
            ],
            "params_numels": [
                [*identity, numel]
                for identity, numel in sorted(
                    replay_cache.params_numels.items()
                    if replay_cache is not None
                    else ()
                )
            ],
            "outer_numels": [
                [*identity, sorted(numels)]
                for identity, numels in sorted(
                    replay_cache.outer_numels.items()
                    if replay_cache is not None
                    else ()
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
            "embedded_objects",
            "proposal_payloads",
            "params_numels",
            "outer_numels",
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
        embedded = cls._parse_embedded_objects(payload["embedded_objects"])
        proposal_payloads = cls._parse_ref_identities(
            payload["proposal_payloads"], field="proposal_payloads"
        )
        params_numels = cls._parse_numel_cache(payload["params_numels"])
        outer_numels = cls._parse_outer_cache(payload["outer_numels"])
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
            embedded_objects=embedded,
            proposal_payloads=proposal_payloads,
            params_numels=params_numels,
            outer_numels=outer_numels,
            snapshot_id=snapshot_id,
        )

    @staticmethod
    def _parse_ref_identities(payload: object, *, field: str) -> tuple[tuple[str, str, int], ...]:
        if not isinstance(payload, list):
            raise ValueError(f"snapshot {field} must be a list")
        result: list[tuple[str, str, int]] = []
        for item in payload:
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
                raise ValueError(f"invalid snapshot {field} entry")
            result.append((item[0], item[1], item[2]))
        if tuple(sorted(result)) != tuple(result) or len(set(result)) != len(result):
            raise ValueError(f"snapshot {field} is not canonical")
        return tuple(result)

    @classmethod
    def _parse_embedded_objects(
        cls, payload: object
    ) -> tuple[tuple[str, str, int, bytes], ...]:
        if not isinstance(payload, list):
            raise ValueError("snapshot embedded_objects must be a list")
        result: list[tuple[str, str, int, bytes]] = []
        for item in payload:
            if not isinstance(item, list) or len(item) != 4:
                raise ValueError("invalid snapshot embedded object entry")
            key, digest, size, encoded = item
            if (
                not isinstance(key, str)
                or not key
                or not isinstance(digest, str)
                or len(digest) != 64
                or type(size) is not int
                or size < 1
                or not isinstance(encoded, str)
            ):
                raise ValueError("invalid snapshot embedded object identity")
            try:
                data = base64.b64decode(encoded, validate=True)
            except Exception as exc:
                raise ValueError("invalid snapshot embedded object encoding") from exc
            if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
                raise ValueError("snapshot embedded object digest differs")
            result.append((key, digest, size, data))
        identities = tuple((key, digest, size) for key, digest, size, _ in result)
        if identities != tuple(sorted(identities)) or len(set(identities)) != len(identities):
            raise ValueError("snapshot embedded objects are not canonical")
        return tuple(result)

    @classmethod
    def _parse_numel_cache(
        cls, payload: object
    ) -> tuple[tuple[str, str, int, int], ...]:
        if not isinstance(payload, list):
            raise ValueError("snapshot params_numels must be a list")
        result: list[tuple[str, str, int, int]] = []
        for item in payload:
            if not isinstance(item, list) or len(item) != 4:
                raise ValueError("invalid snapshot params_numels entry")
            identity = cls._parse_ref_identities([item[:3]], field="params_numels")
            if type(item[3]) is not int or item[3] < 1:
                raise ValueError("invalid snapshot params numel")
            result.append((*identity[0], item[3]))
        if tuple(sorted(result)) != tuple(result):
            raise ValueError("snapshot params_numels is not canonical")
        return tuple(result)

    @classmethod
    def _parse_outer_cache(
        cls, payload: object
    ) -> tuple[tuple[str, str, int, tuple[int, ...]], ...]:
        if not isinstance(payload, list):
            raise ValueError("snapshot outer_numels must be a list")
        result: list[tuple[str, str, int, tuple[int, ...]]] = []
        for item in payload:
            if not isinstance(item, list) or len(item) != 4:
                raise ValueError("invalid snapshot outer_numels entry")
            identity = cls._parse_ref_identities([item[:3]], field="outer_numels")
            raw_numels = item[3]
            if (
                not isinstance(raw_numels, list)
                or not raw_numels
                or any(type(value) is not int or value < 1 for value in raw_numels)
                or raw_numels != sorted(set(raw_numels))
            ):
                raise ValueError("invalid snapshot outer numels")
            result.append((*identity[0], tuple(raw_numels)))
        if tuple(sorted(result)) != tuple(result):
            raise ValueError("snapshot outer_numels is not canonical")
        return tuple(result)

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
            "embedded_objects": [
                [key, digest, size, base64.b64encode(data).decode("ascii")]
                for key, digest, size, data in self.embedded_objects
            ],
            "proposal_payloads": [list(item) for item in self.proposal_payloads],
            "params_numels": [list(item) for item in self.params_numels],
            "outer_numels": [
                [key, digest, size, list(numels)]
                for key, digest, size, numels in self.outer_numels
            ],
            "snapshot_id": self.snapshot_id,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())
