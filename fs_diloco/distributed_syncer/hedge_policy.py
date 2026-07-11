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
        if not isinstance(payload, Mapping):
            raise ValueError("redundancy policy must be a mapping")
        mode = payload.get("mode")
        if mode not in {"warm_standby", "active_active", "hedged"}:
            raise ValueError("unsupported redundancy mode")
        expected = {"mode", "hedge_delay_ms"} if mode == "hedged" else {"mode"}
        if set(payload) != expected:
            raise ValueError("redundancy policy fields differ from canonical mode")
        delay = payload.get("hedge_delay_ms")
        if mode == "hedged" and (type(delay) is not int or delay < 1):
            raise ValueError("hedged mode requires a positive integer delay")
        return cls(mode=mode, hedge_delay_ms=delay if mode == "hedged" else None)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"mode": self.mode}
        if self.mode == "hedged":
            payload["hedge_delay_ms"] = self.hedge_delay_ms
        return payload


def execution_eligible(
    policy: RedundancyPolicyV1,
    *,
    owner_role: str,
    elapsed_ms: int,
    backup_activated: bool = False,
) -> bool:
    if owner_role not in {"primary", "backup"}:
        raise ValueError("owner role must be primary or backup")
    if type(elapsed_ms) is not int or elapsed_ms < 0:
        raise ValueError("elapsed_ms must be a non-negative integer")
    if type(backup_activated) is not bool:
        raise ValueError("backup_activated must be boolean")
    if owner_role == "primary":
        return True
    if backup_activated or policy.mode == "active_active":
        return True
    if policy.mode == "warm_standby":
        return False
    if policy.mode == "hedged" and policy.hedge_delay_ms is not None:
        return elapsed_ms >= policy.hedge_delay_ms
    raise ValueError("invalid redundancy policy instance")
