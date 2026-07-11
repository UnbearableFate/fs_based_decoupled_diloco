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
    raise NotImplementedError("P06C RED: duplicate decision kernel is not implemented")
