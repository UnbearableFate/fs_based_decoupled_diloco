"""Dependency-free P06C duplicate prepared-result decision kernel."""

from __future__ import annotations

from dataclasses import dataclass


class DivergentPreparedResult(RuntimeError):
    """Same FWO produced more than one semantic prepared-result identity."""


@dataclass(frozen=True)
class PreparedResultObservation:
    work_order_id: str
    prepared_result_id: str
    attempt_envelope_id: str
    executor_id: str

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value
            for value in (
                self.work_order_id,
                self.prepared_result_id,
                self.attempt_envelope_id,
                self.executor_id,
            )
        ):
            raise ValueError("prepared-result observation fields must be non-empty strings")


@dataclass(frozen=True)
class DuplicateResultDecision:
    work_order_id: str
    prepared_result_id: str
    attempt_envelope_ids: tuple[str, ...]
    executor_ids: tuple[str, ...]


def decide_duplicate_results(
    work_order_id: str,
    observations: tuple[PreparedResultObservation, ...],
    *,
    required_attempts: int,
) -> DuplicateResultDecision:
    if not isinstance(work_order_id, str) or not work_order_id:
        raise ValueError("work_order_id must be a non-empty string")
    if type(required_attempts) is not int or required_attempts < 1:
        raise ValueError("required_attempts must be positive")
    if len(observations) < required_attempts:
        raise ValueError("insufficient prepared-result attempts")
    if any(row.work_order_id != work_order_id for row in observations):
        raise ValueError("observation belongs to another work order")
    attempt_ids = tuple(row.attempt_envelope_id for row in observations)
    executor_ids = tuple(row.executor_id for row in observations)
    if len(set(attempt_ids)) != len(attempt_ids) or len(set(executor_ids)) != len(
        executor_ids
    ):
        raise ValueError("duplicate observations require distinct attempt and executor IDs")
    result_ids = tuple(sorted({row.prepared_result_id for row in observations}))
    if len(result_ids) != 1:
        raise DivergentPreparedResult(
            f"same work order {work_order_id} produced divergent results {result_ids}"
        )
    return DuplicateResultDecision(
        work_order_id=work_order_id,
        prepared_result_id=result_ids[0],
        attempt_envelope_ids=tuple(sorted(attempt_ids)),
        executor_ids=tuple(sorted(executor_ids)),
    )
