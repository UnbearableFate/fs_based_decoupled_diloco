"""Immutable learner session identity and per-session sequence policy."""

from __future__ import annotations

from dataclasses import dataclass
import re
import uuid

from fs_diloco.protocol.canonical_json import canonical_bytes, canonical_digest


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError(f"{field} must be a safe 1..128 character identifier")
    return value


@dataclass(frozen=True)
class LearnerSession:
    run_id: str
    run_generation: int
    learner_id: str
    session_id: str

    def __post_init__(self) -> None:
        _identifier(self.run_id, "run_id")
        _identifier(self.learner_id, "learner_id")
        _identifier(self.session_id, "session_id")
        if type(self.run_generation) is not int or self.run_generation < 0:
            raise ValueError("run_generation must be a non-negative integer")

    @classmethod
    def new(
        cls,
        run_id: str,
        run_generation: int,
        learner_id: str,
        *,
        session_id: str | None = None,
    ) -> "LearnerSession":
        return cls(
            run_id=run_id,
            run_generation=run_generation,
            learner_id=learner_id,
            session_id=session_id or f"{learner_id}-{uuid.uuid4().hex}",
        )

    @property
    def identity(self) -> tuple[str, int, str, str]:
        return self.run_id, self.run_generation, self.learner_id, self.session_id

    @property
    def session_digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "record_type": "learner_session",
            "protocol_version": 2,
            "run_id": self.run_id,
            "run_generation": self.run_generation,
            "learner_id": self.learner_id,
            "learner_session_id": self.session_id,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())

    def next_sequence(self, recovered_sequences: object) -> int:
        try:
            values = tuple(recovered_sequences)  # type: ignore[arg-type]
        except TypeError as exc:
            raise ValueError("recovered sequences must be iterable") from exc
        for value in values:
            if type(value) is not int or value < 1:
                raise ValueError("recovered sequences must contain positive integers")
        return max(values, default=0) + 1
