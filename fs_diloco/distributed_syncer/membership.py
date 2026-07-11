"""Strict committed membership values; heartbeats are deliberately absent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.protocol.work_order_v1 import _digest, _integer, _strict, _string


@dataclass(frozen=True)
class DistributedMemberV1:
    member_id: str
    learner_id: str
    learner_session_id: str
    executor_id: str
    executor_session_id: str
    node_id: str
    capability_digest: str
    committer_eligible: bool

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DistributedMemberV1":
        _strict(
            payload,
            {
                "member_id", "learner_id", "learner_session_id", "executor_id",
                "executor_session_id", "node_id", "capability_digest",
                "committer_eligible",
            },
        )
        if type(payload["committer_eligible"]) is not bool:
            raise ValueError("committer_eligible must be boolean")
        return cls(
            member_id=_string(payload["member_id"], "member_id"),
            learner_id=_string(payload["learner_id"], "learner_id"),
            learner_session_id=_string(payload["learner_session_id"], "learner_session_id"),
            executor_id=_string(payload["executor_id"], "executor_id"),
            executor_session_id=_string(payload["executor_session_id"], "executor_session_id"),
            node_id=_string(payload["node_id"], "node_id"),
            capability_digest=_digest(payload["capability_digest"], "capability_digest"),
            committer_eligible=payload["committer_eligible"],
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "member_id": self.member_id,
            "learner_id": self.learner_id,
            "learner_session_id": self.learner_session_id,
            "executor_id": self.executor_id,
            "executor_session_id": self.executor_session_id,
            "node_id": self.node_id,
            "capability_digest": self.capability_digest,
            "committer_eligible": self.committer_eligible,
        }


@dataclass(frozen=True)
class MembershipRevisionV1:
    schema: str
    revision: int
    members: tuple[DistributedMemberV1, ...]
    capability_set_digest: str
    membership_digest: str

    SCHEMA = "duraloco-membership-revision-v1"

    @classmethod
    def create(
        cls, revision: int, members: tuple[DistributedMemberV1, ...]
    ) -> "MembershipRevisionV1":
        body = {
            "schema": cls.SCHEMA,
            "revision": revision,
            "members": [item.to_dict() for item in members],
            "capability_set_digest": canonical_digest(
                sorted(item.capability_digest for item in members)
            ),
        }
        return cls.from_dict({**body, "membership_digest": canonical_digest(body)})

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MembershipRevisionV1":
        _strict(
            payload,
            {"schema", "revision", "members", "capability_set_digest", "membership_digest"},
        )
        if payload["schema"] != cls.SCHEMA:
            raise ValueError("unsupported membership schema")
        raw = payload["members"]
        if not isinstance(raw, list) or not raw:
            raise ValueError("membership requires at least one member")
        members = tuple(DistributedMemberV1.from_dict(item) for item in raw)
        ids = tuple(item.member_id for item in members)
        if ids != tuple(sorted(ids)) or len(ids) != len(set(ids)):
            raise ValueError("members must be unique and sorted by member_id")
        for attr in ("learner_id", "learner_session_id", "executor_id", "executor_session_id"):
            values = [getattr(item, attr) for item in members]
            if len(values) != len(set(values)):
                raise ValueError(f"membership has duplicate {attr}")
        instance = cls(
            schema=cls.SCHEMA,
            revision=_integer(payload["revision"], "revision"),
            members=members,
            capability_set_digest=_digest(
                payload["capability_set_digest"], "capability_set_digest"
            ),
            membership_digest=_digest(payload["membership_digest"], "membership_digest"),
        )
        if instance.capability_set_digest != canonical_digest(
            sorted(item.capability_digest for item in members)
        ):
            raise ValueError("capability set digest differs")
        body = instance.to_dict()
        body.pop("membership_digest")
        if instance.membership_digest != canonical_digest(body):
            raise ValueError("membership digest differs")
        return instance

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "revision": self.revision,
            "members": [item.to_dict() for item in self.members],
            "capability_set_digest": self.capability_set_digest,
            "membership_digest": self.membership_digest,
        }

    def member(self, member_id: str) -> DistributedMemberV1:
        return next(item for item in self.members if item.member_id == member_id)
