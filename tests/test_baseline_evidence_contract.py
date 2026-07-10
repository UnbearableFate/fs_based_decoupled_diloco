from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "scripts/agent/verify_baseline_evidence.py"


def _make_run(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    for directory in ("control", "logs", "weights", "db_dumps"):
        (run / directory).mkdir(parents=True)
    weight = run / "weights/global_v000001.safetensors"
    weight.write_bytes(b"representative-tensor")
    (run / "control/latest.json").write_text(
        json.dumps({"version": 1, "weight_path": str(weight)})
    )
    (run / "control/stop.json").write_text(
        json.dumps({"version": 1, "reason": "stop_after_outer_steps"})
    )
    (run / "control/run_config.resolved.yaml").write_text("run: test\n")
    (run / "control/param_index.json").write_text("{}\n")
    events = [
        {"event_type": "process_start"},
        {"event_type": "inner_step_summary", "train_loss": 1.25},
        {"event_type": "update_written"},
        {"event_type": "updates_selected"},
        {"event_type": "outer_step_applied"},
        {"event_type": "global_published"},
        {"event_type": "stop_published"},
        {"event_type": "process_exit"},
    ]
    (run / "logs/syncer.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events)
    )
    database = sqlite3.connect(run / "db_dumps/metadata_test_v000001.db")
    database.execute("CREATE TABLE global_versions(version INTEGER PRIMARY KEY)")
    database.execute("INSERT INTO global_versions VALUES (1)")
    database.commit()
    database.close()
    return run


def _verify(
    run: Path, output: Path, *extra: str
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VERIFY), str(run), "--output", str(output), *extra],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_complete_finite_baseline_evidence_passes(tmp_path):
    run = _make_run(tmp_path)
    output = tmp_path / "evidence.json"
    assert _verify(run, output).returncode == 0
    assertions = json.loads(output.read_text())["assertions"]
    assert all(assertions.values())


@pytest.mark.parametrize("bad_line", ['{"event_type":"inner_step_summary","train_loss":NaN}\n', "not-json\n"])
def test_nonfinite_or_malformed_log_fails_closed(tmp_path, bad_line):
    run = _make_run(tmp_path)
    with (run / "logs/syncer.jsonl").open("a") as handle:
        handle.write(bad_line)
    result = _verify(run, tmp_path / "bad.json")
    assert result.returncode != 0
    assert "non-finite" in result.stderr or "invalid JSON" in result.stderr


def test_missing_expected_training_event_fails_closed(tmp_path):
    run = _make_run(tmp_path)
    log = run / "logs/syncer.jsonl"
    events = [json.loads(line) for line in log.read_text().splitlines()]
    log.write_text(
        "".join(
            json.dumps(event) + "\n"
            for event in events
            if event["event_type"] != "outer_step_applied"
        )
    )
    result = _verify(run, tmp_path / "bad.json")
    assert result.returncode != 0
    assert "groups=" in result.stderr


def test_non_success_stop_requires_explicit_documented_allowance(tmp_path):
    run = _make_run(tmp_path)
    (run / "control/stop.json").write_text(
        json.dumps({"version": 1, "reason": "no_progress_timeout"})
    )
    rejected = _verify(run, tmp_path / "rejected.json")
    assert rejected.returncode != 0
    assert "stop reason" in rejected.stderr
    accepted = _verify(
        run,
        tmp_path / "accepted.json",
        "--allow-stop-reason",
        "no_progress_timeout",
    )
    assert accepted.returncode == 0
