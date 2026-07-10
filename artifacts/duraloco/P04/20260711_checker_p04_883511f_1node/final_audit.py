from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import yaml


PERSISTENCE_COMMIT = "883511f36b0a298bbacae1ead3bb787fa4cf9bf2"
IMPLEMENTATION_COMMIT = "a655413cea6ebe9bc368b5827318efd766683b5a"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    artifact = Path(sys.argv[2]).resolve()
    checks: dict[str, object] = {}
    failures: list[str] = []

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, text=True,
        capture_output=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain=v1"], cwd=root, check=True, text=True,
        capture_output=True,
    ).stdout.splitlines()
    provenance_ok = head == PERSISTENCE_COMMIT and status == []
    checks["clean_persistence_provenance"] = {
        "pass": provenance_ok,
        "head": head,
        "dirty_paths": status,
    }
    if not provenance_ok:
        failures.append("checker did not run from clean persistence commit 883511f")

    expected_runs = {
        "one_node": (
            root / "artifacts/duraloco/P04/20260711_p04_a655413_1node",
            "2358166.opbs",
            "20260711_p04_f6d6e93_1node",
        ),
        "two_node": (
            root / "artifacts/duraloco/P04/20260711_p04_a655413_2node",
            "2358168.opbs",
            "20260711_p04_79373ec_2node",
        ),
        "nine_node": (
            root / "artifacts/duraloco/P04/20260711_p04_a655413_gpt2_9n_50x10",
            "2358179.opbs",
            "20260711_p04_79373ec_gpt2_9n_50x10",
        ),
    }
    manifest_results = {}
    for name, (directory, job_id, parent_id) in expected_runs.items():
        manifest = load_json(directory / "manifest.json")
        clean_log = (directory / "git_status.log").read_text(encoding="utf-8").strip()
        manifest_ok = (
            manifest["git_commit"] == IMPLEMENTATION_COMMIT
            and manifest["pbs_job_id"] == job_id
            and manifest["parent_run_id"] == parent_id
            and manifest["dirty_tree"] is False
            and manifest["dirty_paths"] == []
            and manifest["exit_code"] == 0
            and manifest["result"] == "pass"
            and clean_log == "## HEAD (no branch)"
            and (directory / "git_commit.log").read_text().strip()
            == IMPLEMENTATION_COMMIT
        )
        manifest_results[name] = {
            "pass": manifest_ok,
            "run_id": manifest["run_id"],
            "pbs_job_id": manifest["pbs_job_id"],
            "parent_run_id": manifest["parent_run_id"],
            "git_commit": manifest["git_commit"],
            "dirty_tree": manifest["dirty_tree"],
            "exit_code": manifest["exit_code"],
        }
        if not manifest_ok:
            failures.append(f"{name} maker manifest/provenance/lineage mismatch")
    checks["parent_linked_maker_manifests"] = manifest_results

    one_dir = expected_runs["one_node"][0]
    one_text = (one_dir / "pytest.log").read_text(encoding="utf-8")
    one_report = load_json(one_dir / "p04_1node_report.json")
    one_ok = (
        "272 passed, 1 skipped" in one_text
        and one_report["status"] == "PASS"
        and one_report["commit_seq"] == 10
        and one_report["memory_posix_equal"] is True
        and one_report["cache_rebuild_exact"] is True
        and len(one_report["crash_points"]) == 10
    )
    checks["maker_one_node_contract"] = {"pass": one_ok}
    if not one_ok:
        failures.append("new maker one-node contract evidence is incomplete")

    two_dir = expected_runs["two_node"][0]
    two = load_json(two_dir / "two_node_summary.json")
    two_ok = (
        two["status"] == "PASS"
        and two["rounds"] == 20
        and len(two["hosts"]) == 2
        and two["double_winners"] == 0
        and two["double_inclusions"] == 0
        and two["response_loss_recovered"] is True
        and two["second_node_takeover"] is True
    )
    checks["maker_two_node_contract"] = {
        "pass": two_ok,
        "hosts": two["hosts"],
        "rounds": two["rounds"],
        "double_winners": two["double_winners"],
        "double_inclusions": two["double_inclusions"],
    }
    if not two_ok:
        failures.append("new maker two-node contract evidence is incomplete")

    nine_dir = expected_runs["nine_node"][0]
    terminal = load_json(nine_dir / "terminal_gate_report.json")
    hosts = (nine_dir / "hosts.log").read_text(encoding="utf-8").splitlines()
    qstat = (nine_dir / "qstat_final.log").read_text(encoding="utf-8")
    pbs_script = (
        root / "scripts/miyabi/run_duraloco_milestone_9node_gpt2_50x10.pbs"
    ).read_text(encoding="utf-8")
    terminal_ok = (
        terminal["status"] == "PASS"
        and all(terminal["assertions"].values())
        and terminal["model"] == "gpt2"
        and terminal["dataset"] == "wikitext-2-raw-v1"
        and terminal["learners"] == 8
        and terminal["inner_steps"] == 50
        and terminal["global_outer_transitions"] == 10
        and terminal["nonfinite_or_invalid_loss_count"] == 0
        and terminal["finite_loss_count"] > 0
        and terminal["checkpoint_count"] == 11
        and len(hosts) == len(set(hosts)) == 9
        and "00:00:47" in qstat
        and "#PBS -l select=9:mpiprocs=1" in pbs_script
        and "#PBS -l walltime=00:15:00" in pbs_script
        and "26 passed" in (nine_dir / "p04_pytest.log").read_text(encoding="utf-8")
    )
    checks["maker_terminal_real_9node_50x10"] = {
        "pass": terminal_ok,
        "pbs_job_id": "2358179.opbs",
        "hosts": hosts,
        "observed_qstat_elapsed": "00:00:47",
        "model": terminal["model"],
        "dataset": terminal["dataset"],
        "learners": terminal["learners"],
        "inner_steps": terminal["inner_steps"],
        "outer_transitions": terminal["global_outer_transitions"],
        "finite_loss_count": terminal["finite_loss_count"],
        "checkpoint_count": terminal["checkpoint_count"],
        "all_assertions": all(terminal["assertions"].values()),
    }
    if not terminal_ok:
        failures.append("new real 9-node GPT-2/WikiText-2 50x10 gate is inconsistent")

    pytest_rc = int((artifact / "current_log_pytest_exit_code.log").read_text())
    pytest_text = (artifact / "current_log_pytest.log").read_text(encoding="utf-8")
    pytest_ok = pytest_rc == 0 and "26 passed" in pytest_text
    checks["current_persisted_tests_log"] = {
        "pass": pytest_ok,
        "exit_code": pytest_rc,
        "summary": pytest_text.strip().splitlines()[-1] if pytest_text.strip() else "",
    }
    if not pytest_ok:
        failures.append("current persisted tests/log is not green")

    raw = load_json(artifact / "counterexamples_raw.json")
    counterexamples_ok = (
        not raw["required_failures"]
        and len(raw["checks"]) == 5
        and all(value["pass"] for value in raw["checks"].values())
    )
    checks["p04_a09_five_counterexamples"] = {
        "pass": counterexamples_ok,
        "cases": {name: value["pass"] for name, value in raw["checks"].items()},
    }
    if not counterexamples_ok:
        failures.append("one or more independent P04-A09 counterexamples failed")

    state = yaml.safe_load((root / "plans/duraloco/STATE.yaml").read_text())
    phase_state = yaml.safe_load(
        (root / "plans/duraloco/phases/P04_STATE.yaml").read_text()
    )
    report_text = (root / "plans/duraloco/phases/P04_PHASE_REPORT.md").read_text()
    state_ok = (
        state == phase_state
        and state["phase"] == "P04"
        and state["status"] == "checking"
        and state["last_verified_commit"] == IMPLEMENTATION_COMMIT
        and set(state["acceptance"]) == {f"P04-A{i:02d}" for i in range(1, 10)}
        and all(record["result"] == "pass" for record in state["acceptance"].values())
        and state["checks"]["miyabi_9node"] == "miyabi_9node_pass"
        and not state["open_blockers"]
        and "## English" in report_text
        and "## 中文" in report_text
        and report_text.count("50×10") >= 2
        and "2358166.opbs" in report_text
        and "2358168.opbs" in report_text
        and "2358179.opbs" in report_text
        and "2db8a73" in report_text
        and "24 and failed 2" in report_text
        and "24 项通过、2 项失败" in report_text
    )
    checks["state_report_lifecycle_and_failure_history"] = {
        "pass": state_ok,
        "status": state["status"],
        "last_verified_commit": state["last_verified_commit"],
        "acceptance": {key: value["result"] for key, value in state["acceptance"].items()},
        "bilingual": "## English" in report_text and "## 中文" in report_text,
        "marker_50x10_count": report_text.count("50×10"),
    }
    if not state_ok:
        failures.append("P04 state/report lifecycle or bilingual failure history is inconsistent")

    results = {
        "schema_version": 1,
        "verdict": "PASS" if not failures else "BLOCKED",
        "required_gate_followups": "none" if not failures else failures,
        "P04-A09": "PASS" if counterexamples_ok else "FAIL",
        "checking_to_completed": "AUTHORIZED" if not failures else "DENIED",
        "persistence_commit": PERSISTENCE_COMMIT,
        "verified_implementation": IMPLEMENTATION_COMMIT,
        "checker_pbs_job_id": None,
        "checker_hostname": None,
        "checks": checks,
        "required_failures": failures,
    }
    environment = (artifact / "pbs_environment.log").read_text().splitlines()
    env = dict(line.split("=", 1) for line in environment if "=" in line)
    results["checker_pbs_job_id"] = env.get("PBS_JOBID")
    results["checker_hostname"] = (artifact / "hostname.log").read_text().strip()
    (artifact / "checker_results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(results, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
