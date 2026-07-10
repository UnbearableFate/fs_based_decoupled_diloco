#!/usr/bin/env python3
"""Validate DuraLoCo phase state and legal persisted transitions."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from typing import Any

import yaml


STATUSES = {
    "planned",
    "in_progress",
    "blocked",
    "checking",
    "completed",
    "ready_to_merge",
    "merged",
}
TRANSITIONS = {
    "planned": {"planned", "in_progress", "blocked"},
    "in_progress": {"in_progress", "checking", "blocked"},
    "checking": {"checking", "in_progress", "completed", "blocked"},
    "blocked": {"blocked", "in_progress"},
    "completed": {"completed", "ready_to_merge"},
    "ready_to_merge": {"ready_to_merge", "merged"},
    "merged": {"merged"},
}
CHECK_VALUES = {
    "not_run",
    "static_pass",
    "unit_pass",
    "reference_pass",
    "contract_pass",
    "runtime_pass",
    "miyabi_1node_pass",
    "miyabi_2node_pass",
    "miyabi_9node_pass",
    "skipped_not_required",
    "failed",
    "blocked",
}
ACCEPTANCE_COUNTS = {
    "P00": 8,
    "P01": 8,
    "P02": 8,
    "P03": 8,
    "P04": 9,
    "P05": 10,
    "P06": 11,
    "P07": 10,
    "P08": 8,
    "P09": 9,
    "P10": 9,
    "P11": 9,
    "P12": 12,
}
REQUIRED = {
    "phase",
    "status",
    "planning_basis_branch",
    "planning_basis_commit",
    "actual_base_branch",
    "actual_base_commit",
    "feature_branch",
    "current_loop",
    "current_goal",
    "attempts_for_current_failure",
    "last_verified_commit",
    "checks",
    "acceptance",
    "open_decisions",
    "open_blockers",
    "artifacts",
    "next_action",
    "automatic_progression",
    "requires_human_approval",
    "approval_reason",
    "checker_report",
}


class StateError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise StateError(f"{path}: root must be a mapping")
    return payload


def _phase_number(value: Any) -> int:
    match = re.fullmatch(r"P(0[0-9]|1[0-2])", str(value))
    if not match:
        raise StateError(f"invalid phase: {value!r}")
    return int(match.group(1))


def _checker_verdict(root: Path, relative: str) -> str:
    path = Path(relative)
    path = path if path.is_absolute() else root / path
    if not path.is_file():
        raise StateError(f"checker report does not exist: {relative}")
    text = path.read_text(encoding="utf-8")
    match = re.search(r"(?mi)^\s*(?:verdict|status)\s*:\s*(PASS(?:_WITH_FOLLOWUPS)?|BLOCKED)\s*$", text)
    if not match:
        raise StateError(f"checker report has no structured verdict: {relative}")
    return match.group(1)


def validate(payload: dict[str, Any], *, root: Path) -> None:
    missing = sorted(REQUIRED - payload.keys())
    if missing:
        raise StateError("missing required fields: " + ", ".join(missing))
    _phase_number(payload["phase"])
    status = payload["status"]
    if status not in STATUSES:
        raise StateError(f"invalid status: {status!r}")
    if not isinstance(payload["current_loop"], int) or payload["current_loop"] < 0:
        raise StateError("current_loop must be a non-negative integer")
    if not isinstance(payload["attempts_for_current_failure"], int) or payload[
        "attempts_for_current_failure"
    ] < 0:
        raise StateError("attempts_for_current_failure must be a non-negative integer")
    checks = payload["checks"]
    if not isinstance(checks, dict) or not checks:
        raise StateError("checks must be a non-empty mapping")
    invalid_checks = {key: value for key, value in checks.items() if value not in CHECK_VALUES}
    if invalid_checks:
        raise StateError(f"invalid check values: {invalid_checks}")
    acceptance = payload["acceptance"]
    if not isinstance(acceptance, dict) or not acceptance:
        raise StateError("acceptance must be a non-empty mapping")
    expected_acceptance = {
        f"{payload['phase']}-A{number:02d}"
        for number in range(1, ACCEPTANCE_COUNTS[payload["phase"]] + 1)
    }
    if set(acceptance) != expected_acceptance:
        raise StateError(
            "acceptance set differs from phase contract: "
            f"missing={sorted(expected_acceptance - set(acceptance))} "
            f"extra={sorted(set(acceptance) - expected_acceptance)}"
        )
    for acceptance_id, evidence in acceptance.items():
        if not re.fullmatch(rf"{payload['phase']}-A\d{{2}}", str(acceptance_id)):
            raise StateError(f"invalid acceptance ID for phase: {acceptance_id}")
        if not isinstance(evidence, dict) or evidence.get("result") not in {
            "not_run",
            "pass",
            "fail",
            "blocked",
        }:
            raise StateError(f"invalid acceptance record: {acceptance_id}")
        if evidence.get("result") == "pass" and not evidence.get("evidence"):
            raise StateError(f"PASS has no evidence: {acceptance_id}")
    if status in {"completed", "ready_to_merge", "merged"}:
        failed = [key for key, value in acceptance.items() if value.get("result") != "pass"]
        if failed:
            raise StateError("completed phase has non-PASS acceptance: " + ", ".join(failed))
        commit = payload["last_verified_commit"]
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise StateError("completed phase requires a 40-hex last_verified_commit")
        report = payload["checker_report"]
        if not isinstance(report, str) or not report:
            raise StateError("completed phase requires checker_report")
        if _checker_verdict(root, report) not in {"PASS", "PASS_WITH_FOLLOWUPS"}:
            raise StateError("completed phase checker did not pass")
        if payload["open_blockers"]:
            raise StateError("completed phase cannot have open blockers")
        if any(value in {"not_run", "failed", "blocked"} for value in checks.values()):
            raise StateError("completed phase contains an unresolved check status")
    if payload["requires_human_approval"] and not payload["approval_reason"]:
        raise StateError("requires_human_approval needs approval_reason")


def validate_transition(previous: dict[str, Any], current: dict[str, Any]) -> None:
    previous_phase = _phase_number(previous["phase"])
    current_phase = _phase_number(current["phase"])
    if current_phase == previous_phase:
        if current["status"] not in TRANSITIONS[previous["status"]]:
            raise StateError(
                f"illegal status transition: {previous['status']} -> {current['status']}"
            )
        return
    if current_phase != previous_phase + 1:
        raise StateError(f"phase jump is not sequential: P{previous_phase:02d} -> P{current_phase:02d}")
    if previous["status"] not in {"completed", "ready_to_merge", "merged"}:
        raise StateError("next phase cannot start before previous phase completed")
    if current["status"] not in {"planned", "in_progress"}:
        raise StateError("next phase must start as planned or in_progress")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        current = _load(args.state)
        validate(current, root=args.root.resolve())
        if args.previous:
            previous = _load(args.previous)
            validate(previous, root=args.root.resolve())
            validate_transition(previous, current)
        return 0
    except (OSError, yaml.YAMLError, StateError) as exc:
        print(f"check_phase_state: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
