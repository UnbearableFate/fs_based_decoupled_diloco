"""Reference equivalence helpers."""

from __future__ import annotations

import math

from fs_diloco.testing.deterministic_reference import (
    ReferenceOptimizerConfig,
    ReferenceOptimizerState,
    Vector,
    outer_step,
)


def assert_vector_close(
    actual: Vector,
    expected: Vector,
    *,
    abs_tol: float = 1.0e-7,
    rel_tol: float = 1.0e-6,
) -> None:
    if len(actual) != len(expected):
        raise AssertionError(f"vector lengths differ: {len(actual)} != {len(expected)}")
    for index, (left, right) in enumerate(zip(actual, expected, strict=True)):
        if not math.isclose(left, right, abs_tol=abs_tol, rel_tol=rel_tol):
            raise AssertionError(f"vector index {index}: {left} != {right}")


def fragment_count_one_step(
    theta: Vector,
    gradient: Vector,
    state: ReferenceOptimizerState,
    config: ReferenceOptimizerConfig,
) -> tuple[Vector, ReferenceOptimizerState]:
    """The one-fragment path is definitionally the full-vector reference step."""
    return outer_step(theta, gradient, state, config)
