from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
CREATE = ROOT / "scripts/agent/create_run_manifest.py"
CHECK = ROOT / "scripts/agent/check_run_manifest.py"


def _create(tmp_path: Path) -> Path:
    for name in ("commands.log", "stdout.log", "stderr.log"):
        (tmp_path / name).write_text(name + "\n")
    output = tmp_path / "manifest.json"
    result = subprocess.run(
        [
            sys.executable,
            str(CREATE),
            "--root",
            str(ROOT),
            "--output",
            str(output),
            "--phase",
            "P00",
            "--purpose",
            "unit",
            "--commands-log",
            "commands.log",
            "--stdout",
            "stdout.log",
            "--stderr",
            "stderr.log",
            "--exit-code",
            "0",
            "--result",
            "pass",
            "--assertion",
            "manifest contract test",
        ]
    )
    assert result.returncode == 0
    return output


def test_run_manifest_is_self_checking_and_has_recovery_fields(tmp_path):
    output = _create(tmp_path)
    payload = json.loads(output.read_text())
    assert "pbs_nodefile_digest" in payload
    assert "dataset_revision" in payload
    assert "model_revision" in payload
    assert subprocess.run([sys.executable, str(CHECK), str(output)]).returncode == 0


def test_run_manifest_mutation_and_missing_evidence_fail_closed(tmp_path):
    output = _create(tmp_path)
    payload = json.loads(output.read_text())
    payload["result"] = "fail"
    output.write_text(json.dumps(payload))
    assert subprocess.run([sys.executable, str(CHECK), str(output)]).returncode != 0

    output.unlink()
    output = _create(tmp_path)
    (tmp_path / "commands.log").unlink()
    assert subprocess.run([sys.executable, str(CHECK), str(output)]).returncode != 0
