from __future__ import annotations

import ast
from pathlib import Path

from fs_diloco.syncer_core.planning import (
    PlanningCandidate,
    build_fragment_plan,
    select_candidate_ids,
)
from fs_diloco.testing.deterministic_reference import ReferenceWeightingConfig


def _candidate(
    proposal_id: str,
    learner_id: str,
    sequence: int,
    *,
    fragment_id: int = 0,
    tokens: int = 10,
) -> PlanningCandidate:
    return PlanningCandidate(
        proposal_id=proposal_id,
        learner_id=learner_id,
        sequence=sequence,
        fragment_id=fragment_id,
        target_tokens=tokens,
        base_fragment_version=0,
        payload_sha256=(proposal_id[-1] * 64),
    )


def test_selection_is_order_independent_oldest_first_and_one_per_learner():
    candidates = (
        _candidate("proposal-c", "learner-a", 2),
        _candidate("proposal-b", "learner-b", 1, tokens=20),
        _candidate("proposal-a", "learner-a", 1),
        _candidate("proposal-d", "learner-c", 1, fragment_id=1),
    )
    expected = ("proposal-a", "proposal-b")
    assert select_candidate_ids(candidates, fragment_id=0, quorum_max=2) == expected
    assert select_candidate_ids(reversed(candidates), fragment_id=0, quorum_max=2) == expected


def test_plan_freezes_hex_weights_and_parent_facts():
    candidates = (
        _candidate("proposal-a", "learner-a", 1, tokens=10),
        _candidate("proposal-b", "learner-b", 1, tokens=30),
    )
    plan = build_fragment_plan(
        candidates,
        fragment_id=0,
        current_fragment_version=0,
        parent_commit_id="commit-parent",
        parent_commit_seq=3,
        parent_frontier_digest="f" * 64,
        quorum_max=2,
        weighting_config=ReferenceWeightingConfig(),
    )
    assert plan.selected_proposal_ids == ("proposal-a", "proposal-b")
    assert plan.weights_hex == ((0.25).hex(), (0.75).hex())
    assert plan.parent_commit_seq == 3
    assert len(plan.aggregate_digest) == 64
    assert len(plan.selection_digest) == 64


def test_pure_modules_do_not_import_or_call_authority_and_environment_surfaces():
    root = Path(__file__).resolve().parents[2] / "fs_diloco" / "syncer_core"
    forbidden_imports = {
        "os",
        "pathlib",
        "random",
        "socket",
        "time",
        "fs_diloco.coordination",
        "fs_diloco.storage",
    }
    forbidden_calls = {"conditional_replace", "list_prefix", "time", "monotonic", "getpid"}
    for name in ("planning.py", "aggregation.py", "transaction_attempt.py", "types.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        imports: set[str] = set()
        calls: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
        assert not any(
            imported == forbidden or imported.startswith(forbidden + ".")
            for imported in imports
            for forbidden in forbidden_imports
        ), (name, imports & forbidden_imports)
        assert calls.isdisjoint(forbidden_calls), (name, calls & forbidden_calls)

