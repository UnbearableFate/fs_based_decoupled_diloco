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
        "acceptance": {
            f"P00-A{number:02d}": {"result": "not_run", "evidence": []}
            for number in range(1, 9)
        },
        "open_decisions": [],
        "open_blockers": [],
        "artifacts": [],
        "next_action": "test",
        "automatic_progression": True,
        "requires_human_approval": False,
        "approval_reason": None,
        "checker_report": None,
    }


def _run(
    tmp_path: Path,
    payload: dict,
    *,
    previous: dict | list[dict] | None = None,
) -> subprocess.CompletedProcess:
    state = tmp_path / "STATE.yaml"
    state.write_text(yaml.safe_dump(payload, sort_keys=False))
    command = [sys.executable, str(CHECKER), str(state), "--root", str(tmp_path)]
    if previous is not None:
        previous_states = previous if isinstance(previous, list) else [previous]
        for index, previous_state in enumerate(previous_states):
            previous_path = tmp_path / f"PREVIOUS-{index}.yaml"
            previous_path.write_text(yaml.safe_dump(previous_state, sort_keys=False))
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
    payload["acceptance"] = {
        key: {"result": "pass", "evidence": ["artifact"]}
        for key in payload["acceptance"]
    }
    payload["checks"] = {"local_static": "static_pass"}
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
    completed["acceptance"] = {
        key: {"result": "pass", "evidence": ["artifact"]}
        for key in completed["acceptance"]
    }
    completed["checks"] = {"local_static": "static_pass"}
    completed["checker_report"] = "checker.md"
    (tmp_path / "checker.md").write_text("Verdict: PASS\n")
    skipped = copy.deepcopy(previous)
    skipped["phase"] = "P02"
    skipped["status"] = "in_progress"
    skipped["acceptance"] = {
        f"P02-A{number:02d}": {"result": "not_run", "evidence": []}
        for number in range(1, 9)
    }
    assert _run(tmp_path, skipped, previous=completed).returncode != 0


def test_missing_acceptance_id_is_rejected_even_before_completion(tmp_path):
    payload = _base_state()
    del payload["acceptance"]["P00-A08"]
    result = _run(tmp_path, payload)
    assert result.returncode != 0
    assert "acceptance set differs" in result.stderr


def test_pass_with_required_gate_followup_cannot_complete(tmp_path):
    report = tmp_path / "checker.md"
    report.write_text(
        "Verdict: PASS_WITH_FOLLOWUPS\nrequired_gate_followups: rerun runtime gate\n"
    )
    payload = _base_state()
    payload["status"] = "completed"
    payload["last_verified_commit"] = "b" * 40
    payload["acceptance"] = {
        key: {"result": "pass", "evidence": ["artifact"]}
        for key in payload["acceptance"]
    }
    payload["checks"] = {"local_static": "static_pass"}
    payload["checker_report"] = "checker.md"
    result = _run(tmp_path, payload)
    assert result.returncode != 0
    assert "required_gate_followups" in result.stderr


def _phase_state(phase: str, acceptance_count: int, *, status: str) -> dict:
    payload = _base_state()
    payload["phase"] = phase
    payload["status"] = status
    payload["acceptance"] = {
        f"{phase}-A{number:02d}": {
            "result": "pass" if status == "completed" else "not_run",
            "evidence": ["artifact"] if status == "completed" else [],
        }
        for number in range(1, acceptance_count + 1)
    }
    if phase in {
        "P05",
        "P06",
        "P06A",
        "P06B",
        "P06C",
        "P07",
        "P08",
        "P09",
        "P10",
        "P11",
        "P12",
    }:
        payload["last_terminal_failure_review"] = None
        payload["terminal_retry_authorized"] = False
        payload["terminal_retry_qualification"] = {
            "targeted_1node_benchmark": None,
            "miyabi_1node": None,
            "miyabi_2node": None,
        }
    if status == "completed":
        payload["last_verified_commit"] = "d" * 40
        terminal_checks = {
            "P06A": {"miyabi_c9": "miyabi_c9_pass"},
            "P06B": {"miyabi_d8": "miyabi_d8_pass"},
            "P06C": {"miyabi_d8_r2": "miyabi_d8_r2_pass"},
        }
        payload["checks"] = terminal_checks.get(
            phase, {"miyabi_9node": "miyabi_9node_pass"}
        )
        payload["checker_report"] = "checker.md"
    return payload


def test_updated_acceptance_counts_and_dependency_graph(tmp_path):
    (tmp_path / "checker.md").write_text("Verdict: PASS\n")
    m00 = _phase_state("M00", 12, status="completed")
    p05 = _phase_state("P05", 20, status="planned")
    assert _run(tmp_path, p05, previous=m00).returncode == 0

    p06 = _phase_state("P06", 20, status="completed")
    p06a = _phase_state("P06A", 20, status="planned")
    assert _run(tmp_path, p06a, previous=p06).returncode == 0
    p06a_completed = _phase_state("P06A", 20, status="completed")
    p06b = _phase_state("P06B", 23, status="planned")
    assert _run(tmp_path, p06b, previous=p06a_completed).returncode == 0
    p06b_completed = _phase_state("P06B", 23, status="completed")
    p06c = _phase_state("P06C", 24, status="planned")
    assert _run(tmp_path, p06c, previous=p06b_completed).returncode == 0

    p06c_completed = _phase_state("P06C", 24, status="completed")
    p07 = _phase_state("P07", 19, status="planned")
    assert _run(tmp_path, p07, previous=p06c_completed).returncode == 0
    p07_completed = _phase_state("P07", 19, status="completed")
    p08 = _phase_state("P08", 16, status="planned")
    assert _run(tmp_path, p08, previous=p07_completed).returncode == 0
    p08_completed = _phase_state("P08", 16, status="completed")
    p10 = _phase_state("P10", 17, status="planned")
    assert _run(tmp_path, p10, previous=p08_completed).returncode == 0
    missing_dependency = _run(tmp_path, p10, previous=p07_completed)
    assert missing_dependency.returncode != 0
    assert "P08" in missing_dependency.stderr

    p12 = _phase_state("P12", 20, status="completed")
    p09 = _phase_state("P09", 16, status="planned")
    assert _run(tmp_path, p09, previous=p12).returncode == 0

    unexpected_dependency = _run(tmp_path, p09, previous=[p12, p08])
    assert unexpected_dependency.returncode != 0
    assert "unexpected phase dependencies" in unexpected_dependency.stderr


def test_p05_terminal_retry_fields_are_enforced(tmp_path):
    payload = _phase_state("P05", 20, status="planned")
    del payload["terminal_retry_authorized"]
    result = _run(tmp_path, payload)
    assert result.returncode != 0
    assert "terminal retry fields" in result.stderr

    payload = _phase_state("P05", 20, status="planned")
    payload["terminal_retry_authorized"] = True
    result = _run(tmp_path, payload)
    assert result.returncode != 0
    assert "last_terminal_failure_review" in result.stderr

    payload["last_terminal_failure_review"] = "reviews/failure.md"
    result = _run(tmp_path, payload)
    assert result.returncode != 0
    assert "same-commit qualification" in result.stderr
