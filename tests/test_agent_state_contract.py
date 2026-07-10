from __future__ import annotations

import copy
from pathlib import Path
import subprocess
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts/agent/check_phase_state.py"


def _base_state() -> dict:
    return {
        "phase": "P00",
        "status": "in_progress",
        "planning_basis_branch": "codex/fs-diloco-miyabi",
        "planning_basis_commit": "a" * 40,
        "actual_base_branch": "main",
        "actual_base_commit": "a" * 40,
        "feature_branch": "codex/duraloco-p00-contract",
        "current_loop": 1,
        "current_goal": "test",
        "attempts_for_current_failure": 0,
        "last_verified_commit": None,
        "checks": {"local_static": "not_run"},
        "acceptance": {"P00-A01": {"result": "not_run", "evidence": []}},
        "open_decisions": [],
        "open_blockers": [],
        "artifacts": [],
        "next_action": "test",
        "automatic_progression": True,
        "requires_human_approval": False,
        "approval_reason": None,
        "checker_report": None,
    }


def _run(tmp_path: Path, payload: dict, *, previous: dict | None = None) -> subprocess.CompletedProcess:
    state = tmp_path / "STATE.yaml"
    state.write_text(yaml.safe_dump(payload, sort_keys=False))
    command = [sys.executable, str(CHECKER), str(state), "--root", str(tmp_path)]
    if previous is not None:
        previous_path = tmp_path / "PREVIOUS.yaml"
        previous_path.write_text(yaml.safe_dump(previous, sort_keys=False))
        command.extend(["--previous", str(previous_path)])
    return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def test_current_in_progress_state_is_valid(tmp_path):
    assert _run(tmp_path, _base_state()).returncode == 0


def test_missing_field_is_rejected(tmp_path):
    payload = _base_state()
    del payload["checks"]
    result = _run(tmp_path, payload)
    assert result.returncode != 0
    assert "missing required fields" in result.stderr


def test_completed_without_evidence_or_checker_is_rejected(tmp_path):
    payload = _base_state()
    payload["status"] = "completed"
    payload["last_verified_commit"] = "b" * 40
    result = _run(tmp_path, payload)
    assert result.returncode != 0
    assert "non-PASS acceptance" in result.stderr


def test_completed_with_structured_checker_and_evidence_passes(tmp_path):
    report = tmp_path / "checker.md"
    report.write_text("Verdict: PASS\n")
    payload = _base_state()
    payload["status"] = "completed"
    payload["last_verified_commit"] = "b" * 40
    payload["acceptance"]["P00-A01"] = {"result": "pass", "evidence": ["artifact"]}
    payload["checker_report"] = "checker.md"
    assert _run(tmp_path, payload).returncode == 0


def test_illegal_status_and_phase_jumps_are_rejected(tmp_path):
    previous = _base_state()
    current = copy.deepcopy(previous)
    current["status"] = "completed"
    assert _run(tmp_path, current, previous=previous).returncode != 0

    completed = copy.deepcopy(previous)
    completed["status"] = "completed"
    completed["last_verified_commit"] = "c" * 40
    completed["acceptance"]["P00-A01"] = {"result": "pass", "evidence": ["artifact"]}
    completed["checker_report"] = "checker.md"
    (tmp_path / "checker.md").write_text("Verdict: PASS\n")
    skipped = copy.deepcopy(previous)
    skipped["phase"] = "P02"
    skipped["status"] = "in_progress"
    skipped["acceptance"] = {"P02-A01": {"result": "not_run", "evidence": []}}
    assert _run(tmp_path, skipped, previous=completed).returncode != 0
