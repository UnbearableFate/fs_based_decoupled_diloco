"""Replayable P06C redundancy policy and derived execution eligibility."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Any


@dataclass(frozen=True)
class RedundancyPolicyV1:
    mode: str
    hedge_delay_ms: int | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RedundancyPolicyV1":
        raise NotImplementedError("P06C RED: strict redundancy policy is not implemented")

    def to_dict(self) -> dict[str, object]:
        raise NotImplementedError("P06C RED: canonical redundancy policy is not implemented")


def execution_eligible(
    policy: RedundancyPolicyV1,
    *,
    owner_role: str,
    elapsed_ms: int,
    backup_activated: bool = False,
) -> bool:
    raise NotImplementedError("P06C RED: hedge eligibility is not implemented")
