"""Portable RNG cursor hook; P06 deliberately does not claim exact RNG continuation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class RngCursor:
    seed: int
    draws: int = 0

    def __post_init__(self) -> None:
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        if type(self.draws) is not int or self.draws < 0:
            raise ValueError("draws must be a non-negative integer")

    def to_dict(self) -> dict[str, int]:
        return {"seed": self.seed, "draws": self.draws}

    @classmethod
    def from_dict(cls, payload: object) -> "RngCursor":
        if not isinstance(payload, dict) or set(payload) != {"seed", "draws"}:
            raise ValueError("RNG cursor fields differ from contract")
        return cls(seed=payload["seed"], draws=payload["draws"])
