"""Immutable contribution interval and frozen authority-base contract."""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Mapping

from fs_diloco.protocol.canonical_json import canonical_digest

from .data_cursor import DataCursor
from .rng_state import RngCursor
from .session import LearnerSession


@dataclass(frozen=True)
class AuthorityFrontier:
    commit_id: str
    commit_seq: int
    frontier_sha256: str
    fragment_versions: Mapping[int, int]
    fencing_epoch: int
    owner_id: str | None
    owner_session_id: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.commit_id, str) or not self.commit_id:
            raise ValueError("commit_id must be non-empty")
        if type(self.commit_seq) is not int or self.commit_seq < 0:
            raise ValueError("commit_seq must be non-negative")
        if not isinstance(self.frontier_sha256, str) or len(self.frontier_sha256) != 64:
            raise ValueError("frontier_sha256 must contain 64 characters")
        versions = dict(self.fragment_versions)
        if not versions or any(
            type(key) is not int or key < 0 or type(value) is not int or value < 0
            for key, value in versions.items()
        ):
            raise ValueError("fragment versions must be a non-empty non-negative integer map")
        object.__setattr__(self, "fragment_versions", MappingProxyType(versions))
        if type(self.fencing_epoch) is not int or self.fencing_epoch < 0:
            raise ValueError("fencing_epoch must be non-negative")
        if (self.owner_id is None) != (self.owner_session_id is None):
            raise ValueError("owner identity fields must be jointly present or absent")

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "commit_id": self.commit_id,
            "commit_seq": self.commit_seq,
            "frontier_sha256": self.frontier_sha256,
            "fragment_versions": {
                str(key): value for key, value in sorted(self.fragment_versions.items())
            },
            "fencing_epoch": self.fencing_epoch,
        }
        if self.owner_id is not None:
            payload["owner_id"] = self.owner_id
            payload["owner_session_id"] = self.owner_session_id
        return payload


@dataclass(frozen=True)
class ContributionInterval:
    session: LearnerSession
    sequence: int
    fragment_id: int
    base: AuthorityFrontier
    start_step: int
    end_step: int
    start_cursor: DataCursor
    end_cursor: DataCursor | None
    rng_cursor: RngCursor
    target_tokens: int
    examples: int
    transport_dtype: str
    previous_interval_digest: str | None = None
    closed: bool = False

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 1:
            raise ValueError("sequence must be positive")
        if type(self.fragment_id) is not int or self.fragment_id < 0:
            raise ValueError("fragment_id must be non-negative")
        if self.fragment_id not in self.base.fragment_versions:
            raise ValueError("fragment_id is absent from base")
        for name in ("start_step", "end_step", "target_tokens", "examples"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.end_step < self.start_step:
            raise ValueError("end_step precedes start_step")
        if not isinstance(self.transport_dtype, str) or not self.transport_dtype:
            raise ValueError("transport_dtype must be non-empty")
        if self.closed and self.end_cursor is None:
            raise ValueError("closed interval requires end_cursor")
        if not self.closed and self.end_cursor is not None:
            raise ValueError("open interval cannot have end_cursor")

    @classmethod
    def start(
        cls,
        *,
        session: LearnerSession,
        sequence: int,
        fragment_id: int,
        base: AuthorityFrontier,
        start_step: int,
        start_cursor: DataCursor,
        rng_cursor: RngCursor,
        transport_dtype: str,
        previous: "ContributionInterval | None" = None,
    ) -> "ContributionInterval":
        predecessor = None
        if previous is not None:
            if not previous.closed:
                raise ValueError("previous interval must be closed")
            if previous.session.identity != session.identity:
                raise ValueError("previous interval crosses learner session")
            if sequence <= previous.sequence:
                raise ValueError("sequence must advance monotonically")
            if start_step < previous.end_step:
                raise ValueError("interval local steps overlap")
            predecessor = previous.interval_digest
        return cls(
            session=session,
            sequence=sequence,
            fragment_id=fragment_id,
            base=base,
            start_step=start_step,
            end_step=start_step,
            start_cursor=start_cursor,
            end_cursor=None,
            rng_cursor=rng_cursor,
            target_tokens=0,
            examples=0,
            transport_dtype=transport_dtype,
            previous_interval_digest=predecessor,
        )

    def record_step(self, *, tokens: int, examples: int) -> "ContributionInterval":
        if self.closed:
            raise ValueError("closed interval cannot record work")
        if type(tokens) is not int or tokens <= 0:
            raise ValueError("tokens must be positive")
        if type(examples) is not int or examples <= 0:
            raise ValueError("examples must be positive")
        return replace(
            self,
            end_step=self.end_step + 1,
            target_tokens=self.target_tokens + tokens,
            examples=self.examples + examples,
        )

    def close(self, *, end_cursor: DataCursor) -> "ContributionInterval":
        if self.closed:
            raise ValueError("interval is already closed")
        if self.end_step == self.start_step or self.target_tokens == 0:
            raise ValueError("empty interval cannot be closed")
        if end_cursor < self.start_cursor:
            raise ValueError("data cursor moved backwards")
        return replace(self, end_cursor=end_cursor, closed=True)

    @property
    def local_step_range(self) -> tuple[int, int]:
        return self.start_step, self.end_step

    def identity_body(self) -> dict[str, object]:
        body: dict[str, object] = {
            "protocol_version": 2,
            "run_id": self.session.run_id,
            "run_generation": self.session.run_generation,
            "learner_id": self.session.learner_id,
            "learner_session_id": self.session.session_id,
            "sequence": self.sequence,
            "fragment_id": self.fragment_id,
            "base": self.base.to_dict(),
            "local_step_start": self.start_step,
            "local_step_end": self.end_step,
            "start_cursor": self.start_cursor.to_dict(),
            "rng_cursor": self.rng_cursor.to_dict(),
            "target_tokens": self.target_tokens,
            "examples": self.examples,
            "payload_kind": "local_end_weight",
            "transport_dtype": self.transport_dtype,
            "committed_dtype": "float32",
            "numeric_contract": "proposal-transport-to-float32-commit-v1",
        }
        if self.end_cursor is not None:
            body["end_cursor"] = self.end_cursor.to_dict()
        if self.previous_interval_digest is not None:
            body["previous_interval_digest"] = self.previous_interval_digest
        return body

    @property
    def interval_digest(self) -> str:
        if not self.closed:
            raise ValueError("open interval has no publication digest")
        return canonical_digest(self.identity_body())
