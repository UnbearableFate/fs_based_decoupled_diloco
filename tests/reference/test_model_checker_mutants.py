from __future__ import annotations

import pytest

from fs_diloco.testing.model_checker import mutant_violations

from .helpers import state_with_one_commit


@pytest.mark.parametrize(
    ("mutant", "invariant"),
    [
        ("double_apply", "I-003"),
        ("wrong_parent", "I-002"),
        ("state_pairing", "I-005"),
        ("numeric_transition", "I-009"),
    ],
)
def test_deliberate_safety_mutants_are_killed(mutant, invariant):
    violations = mutant_violations(state_with_one_commit(), mutant)
    assert any(invariant in violation for violation in violations)
