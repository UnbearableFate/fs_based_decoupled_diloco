from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/agent/create_p08r_r2_adjudication.py"


def test_r2_adjudication_accepts_old_elapsed_only_failure(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    payloads = {
        "manifest.json": {
            "result": "fail",
            "run_id": "r2",
            "pbs_job_id": "1.opbs",
            "git_commit": "a" * 40,
            "dirty_tree": False,
        },
        "elapsed_contract.json": {
            "status": "FAIL",
            "runtime_elapsed_seconds": 505.0,
            "post_runtime_elapsed_seconds": 21.0,
            "experiment_elapsed_seconds": 527.0,
            "max_experiment_seconds": 440.0,
        },
        "p08_d8_r2_report.json": {
            "status": "PASS",
            "optimizer_transitions": 10,
            "binding": {
                "allocation_nodes": 8,
                "learner_nodes": 8,
                "hosts": [f"h{i}" for i in range(8)],
                "git_commit": "a" * 40,
            },
            "terminal_audit": {"status": "PASS"},
        },
        "interference_report.json": {"status": "PASS"},
        "bundle_gate_report.json": {"status": "PASS"},
        "p07_lifecycle_report.json": {"status": "PASS"},
    }
    for name, payload in payloads.items():
        (source / name).write_text(json.dumps(payload), encoding="utf-8")
    (source / "p07_regression_junit.xml").write_text(
        '<testsuites><testsuite tests="30" failures="0" errors="0" skipped="0"/>'
        "</testsuites>",
        encoding="utf-8",
    )
    output = tmp_path / "adjudication.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source-artifacts",
            str(source),
            "--output",
            str(output),
        ],
        check=False,
    )
    report = json.loads(output.read_text(encoding="utf-8"))

    assert result.returncode == 0
    assert report["status"] == "PASS"
    assert report["max_experiment_seconds"] == 600.0
