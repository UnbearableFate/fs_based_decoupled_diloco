"""Dataset cursor hooks for explicit warm, non-exact learner recovery."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class DataCursor:
    batch_index: int
    token_offset: int = 0

    def __post_init__(self) -> None:
        if type(self.batch_index) is not int or self.batch_index < 0:
            raise ValueError("batch_index must be a non-negative integer")
        if type(self.token_offset) is not int or self.token_offset < 0:
            raise ValueError("token_offset must be a non-negative integer")

    def to_dict(self) -> dict[str, int]:
        return {"batch_index": self.batch_index, "token_offset": self.token_offset}

    @classmethod
    def from_dict(cls, payload: object) -> "DataCursor":
        if not isinstance(payload, dict) or set(payload) != {"batch_index", "token_offset"}:
            raise ValueError("data cursor fields differ from contract")
        return cls(batch_index=payload["batch_index"], token_offset=payload["token_offset"])
