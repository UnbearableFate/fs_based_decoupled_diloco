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
    "miyabi_c1_pass",
    "miyabi_c2_pass",
    "miyabi_c9_pass",
    "miyabi_d1_pass",
    "miyabi_d2_pass",
    "miyabi_d8_pass",
    "miyabi_d1_r2_pass",
    "miyabi_d2_r2_pass",
    "miyabi_d8_r2_pass",
    "skipped_not_required",
    "failed",
    "blocked",
}
ACCEPTANCE_COUNTS = {
    "M00": 12,
    "P00": 8,
    "P01": 8,
    "P02": 8,
    "P03": 8,
    "P04": 9,
    "P05": 20,
    "P06": 20,
    "P06A": 20,
    "P06B": 23,
    "P06C": 24,
    "P07": 24,
    "P08": 25,
    "P08R": 20,
    "P09": 16,
    "P10": 17,
    "P11": 17,
    "P12": 20,
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


PHASE_ORDER = (
    "P00",
    "P01",
    "P02",
    "P03",
    "P04",
    "M00",
    "P05",
    "P06",
    "P06A",
    "P06B",
    "P06C",
    "P07",
    "P08",
    "P08R",
    "P10",
    "P11",
    "P12",
    "P09",
)
PHASE_DEPENDENCIES = {
    "P00": set(),
    "P01": {"P00"},
    "P02": {"P01"},
    "P03": {"P02"},
    "P04": {"P03"},
    "M00": {"P04"},
    "P05": {"M00"},
    "P06": {"P05"},
    "P06A": {"P06"},
    "P06B": {"P06A"},
    "P06C": {"P06B"},
    "P07": {"P06C"},
    "P08": {"P07"},
    "P08R": {"P08"},
    "P10": {"P08R"},
    "P11": {"P10"},
    "P12": {"P11"},
    "P09": {"P12"},
}
TERMINAL_RETRY_PHASES = {
    "P05",
    "P06",
    "P06A",
    "P06B",
    "P06C",
    "P07",
    "P08",
    "P08R",
    "P09",
    "P10",
    "P11",
    "P12",
}


def _phase_rank(value: Any) -> int:
    try:
        return PHASE_ORDER.index(str(value))
    except ValueError as exc:
        raise StateError(f"invalid phase: {value!r}") from exc


def _checker_verdict(root: Path, relative: str) -> tuple[str, str]:
    path = Path(relative)
    path = path if path.is_absolute() else root / path
    if not path.is_file():
        raise StateError(f"checker report does not exist: {relative}")
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r"(?mi)^\s*(?:verdict|status)\s*:\s*(PASS(?:_WITH_FOLLOWUPS)?|BLOCKED)\s*$",
        text,
    )
    if not match:
        raise StateError(f"checker report has no structured verdict: {relative}")
    followups = re.search(r"(?mi)^\s*required_gate_followups\s*:\s*(.+?)\s*$", text)
    return match.group(1), followups.group(1).strip() if followups else ""


def validate(payload: dict[str, Any], *, root: Path) -> None:
    missing = sorted(REQUIRED - payload.keys())
    if missing:
        raise StateError("missing required fields: " + ", ".join(missing))
    _phase_rank(payload["phase"])
    status = payload["status"]
    if status not in STATUSES:
        raise StateError(f"invalid status: {status!r}")
    if not isinstance(payload["current_loop"], int) or payload["current_loop"] < 0:
        raise StateError("current_loop must be a non-negative integer")
    if not isinstance(payload["attempts_for_current_failure"], int) or payload[
        "attempts_for_current_failure"
    ] < 0:
        raise StateError("attempts_for_current_failure must be a non-negative integer")
    if payload["phase"] in TERMINAL_RETRY_PHASES:
        retry_fields = {
            "last_terminal_failure_review",
            "terminal_retry_authorized",
            "terminal_retry_qualification",
        }
        missing_retry_fields = sorted(retry_fields - payload.keys())
        if missing_retry_fields:
            raise StateError(
                "missing terminal retry fields: " + ", ".join(missing_retry_fields)
            )
        if not isinstance(payload["terminal_retry_authorized"], bool):
            raise StateError("terminal_retry_authorized must be boolean")
        review = payload["last_terminal_failure_review"]
        if review is not None and (not isinstance(review, str) or not review):
            raise StateError("last_terminal_failure_review must be null or a non-empty path")
        if payload["terminal_retry_authorized"] and not review:
            raise StateError(
                "terminal_retry_authorized requires last_terminal_failure_review"
            )
        qualification = payload["terminal_retry_qualification"]
        qualification_fields = {
            "targeted_1node_benchmark",
            "miyabi_1node",
            "miyabi_2node",
        }
        if not isinstance(qualification, dict) or set(qualification) != qualification_fields:
            raise StateError("terminal_retry_qualification fields differ from contract")
        for field, reference in qualification.items():
            if reference is not None and (
                not isinstance(reference, str) or not reference.strip()
            ):
                raise StateError(
                    f"terminal_retry_qualification.{field} must be null or a reference"
                )
        if payload["terminal_retry_authorized"]:
            missing_qualification = [
                field for field, reference in qualification.items() if not reference
            ]
            if missing_qualification:
                raise StateError(
                    "terminal_retry_authorized requires same-commit qualification: "
                    + ", ".join(missing_qualification)
                )
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
        verdict, required_gate_followups = _checker_verdict(root, report)
        if verdict not in {"PASS", "PASS_WITH_FOLLOWUPS"}:
            raise StateError("completed phase checker did not pass")
        if verdict == "PASS_WITH_FOLLOWUPS" and required_gate_followups.casefold() not in {
            "none",
            "[]",
        }:
            raise StateError(
                "PASS_WITH_FOLLOWUPS may complete only with required_gate_followups: none"
            )
        if payload["open_blockers"]:
            raise StateError("completed phase cannot have open blockers")
        if any(value in {"not_run", "failed", "blocked"} for value in checks.values()):
            raise StateError("completed phase contains an unresolved check status")
        terminal_checks = {
            "P06A": ("miyabi_c9", "miyabi_c9_pass"),
            "P06B": ("miyabi_d8", "miyabi_d8_pass"),
            "P06C": ("miyabi_d8_r2", "miyabi_d8_r2_pass"),
            "P08": ("miyabi_d8_r2", "miyabi_d8_r2_pass"),
            "P08R": ("miyabi_d8_r2", "miyabi_d8_r2_pass"),
        }
        terminal_key, terminal_value = terminal_checks.get(
            payload["phase"], ("miyabi_9node", "miyabi_9node_pass")
        )
        requires_terminal = _phase_rank(payload["phase"]) >= _phase_rank("P04")
        if requires_terminal and checks.get(terminal_key) != terminal_value:
            raise StateError(
                f"{payload['phase']} completion requires terminal check "
                f"{terminal_key}={terminal_value}"
            )
    if payload["requires_human_approval"] and not payload["approval_reason"]:
        raise StateError("requires_human_approval needs approval_reason")


def validate_transition(previous_states: list[dict[str, Any]], current: dict[str, Any]) -> None:
    by_phase: dict[str, dict[str, Any]] = {}
    for previous in previous_states:
        phase = str(previous["phase"])
        if phase in by_phase:
            raise StateError(f"duplicate previous phase state: {phase}")
        by_phase[phase] = previous

    current_phase = str(current["phase"])
    if current_phase in by_phase:
        if len(by_phase) != 1:
            raise StateError("same-phase transition accepts exactly one previous state")
        previous = by_phase[current_phase]
        if current["status"] not in TRANSITIONS[previous["status"]]:
            raise StateError(
                f"illegal status transition: {previous['status']} -> {current['status']}"
            )
        return

    required = PHASE_DEPENDENCIES[current_phase]
    missing = required - by_phase.keys()
    if missing:
        raise StateError(
            f"missing completed phase dependencies for {current_phase}: {sorted(missing)}"
        )
    unexpected = by_phase.keys() - required
    if unexpected:
        raise StateError(
            f"unexpected phase dependencies for {current_phase}: {sorted(unexpected)}"
        )
    incomplete = sorted(
        phase
        for phase in required
        if by_phase[phase]["status"] not in {"completed", "ready_to_merge", "merged"}
    )
    if incomplete:
        raise StateError("phase dependencies are not completed: " + ", ".join(incomplete))
    if current["status"] not in {"planned", "in_progress"}:
        raise StateError("next phase must start as planned or in_progress")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    parser.add_argument("--previous", type=Path, action="append", default=[])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        current = _load(args.state)
        validate(current, root=args.root.resolve())
        if args.previous:
            previous_states = [_load(path) for path in args.previous]
            for previous in previous_states:
                validate(previous, root=args.root.resolve())
            validate_transition(previous_states, current)
        return 0
    except (OSError, yaml.YAMLError, StateError) as exc:
        print(f"check_phase_state: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
