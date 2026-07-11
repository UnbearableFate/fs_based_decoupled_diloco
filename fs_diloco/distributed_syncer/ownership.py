"""Deterministic rendezvous ownership derived only from committed membership."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

from fs_diloco.protocol.canonical_json import canonical_bytes, canonical_digest

from .membership import MembershipRevisionV1


@dataclass(frozen=True)
class OwnershipMapV1:
    membership_revision: int
    replication_factor: int
    owners: tuple[tuple[int, tuple[str, ...]], ...]
    ownership_digest: str

    def owner_ids(self, fragment_id: int) -> tuple[str, ...]:
        return next(owners for candidate, owners in self.owners if candidate == fragment_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "duraloco-ownership-map-v1",
            "membership_revision": self.membership_revision,
            "replication_factor": self.replication_factor,
            "owners": [
                {"fragment_id": fragment_id, "member_ids": list(member_ids)}
                for fragment_id, member_ids in self.owners
            ],
            "ownership_digest": self.ownership_digest,
        }


def derive_ownership(
    membership: MembershipRevisionV1,
    *,
    fragment_ids: tuple[int, ...],
    replication_factor: int = 1,
) -> OwnershipMapV1:
    if replication_factor < 1 or replication_factor > len(membership.members):
        raise ValueError("replication factor exceeds eligible membership")
    if not fragment_ids or fragment_ids != tuple(sorted(set(fragment_ids))):
        raise ValueError("fragment IDs must be non-empty, unique, and sorted")
    rows: list[tuple[int, tuple[str, ...]]] = []
    for fragment_id in fragment_ids:
        if fragment_id < 0:
            raise ValueError("fragment IDs must be non-negative")
        ranked = sorted(
            membership.members,
            key=lambda member: (
                hashlib.sha256(
                    canonical_bytes(
                        {
                            "schema": "duraloco-rendezvous-owner-score-v1",
                            "membership_digest": membership.membership_digest,
                            "revision": membership.revision,
                            "fragment_id": fragment_id,
                            "member_id": member.member_id,
                        }
                    )
                ).digest(),
                member.member_id,
            ),
            reverse=True,
        )
        rows.append((fragment_id, tuple(item.member_id for item in ranked[:replication_factor])))
    body = {
        "schema": "duraloco-ownership-map-v1",
        "membership_revision": membership.revision,
        "replication_factor": replication_factor,
        "owners": [
            {"fragment_id": fragment_id, "member_ids": list(member_ids)}
            for fragment_id, member_ids in rows
        ],
    }
    return OwnershipMapV1(
        membership_revision=membership.revision,
        replication_factor=replication_factor,
        owners=tuple(rows),
        ownership_digest=canonical_digest(body),
    )
