from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/agent/create_p08r_elapsed_report.py"


def _run(tmp_path: Path, *, experiment_seconds: int, post_seconds: int):
    output = tmp_path / "elapsed.json"
    start = 1_000_000_000
    runtime_start = start + 10_000_000_000
    experiment_end = start + experiment_seconds * 1_000_000_000
    runtime_end = experiment_end - post_seconds * 1_000_000_000
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--experiment-started-ns",
            str(start),
            "--runtime-started-ns",
            str(runtime_start),
            "--runtime-ended-ns",
            str(runtime_end),
            "--experiment-ended-ns",
            str(experiment_end),
            "--output",
            str(output),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result, json.loads(output.read_text(encoding="utf-8"))


def test_elapsed_contract_accepts_frozen_budget(tmp_path: Path) -> None:
    result, report = _run(tmp_path, experiment_seconds=440, post_seconds=25)

    assert result.returncode == 0
    assert report["status"] == "PASS"
    assert report["runtime_elapsed_seconds"] == 405


def test_elapsed_contract_rejects_experiment_or_post_budget(tmp_path: Path) -> None:
    experiment, experiment_report = _run(
        tmp_path / "experiment", experiment_seconds=441, post_seconds=25
    )
    post, post_report = _run(tmp_path / "post", experiment_seconds=440, post_seconds=26)

    assert experiment.returncode == 2
    assert experiment_report["status"] == "FAIL"
    assert post.returncode == 2
    assert post_report["status"] == "FAIL"
