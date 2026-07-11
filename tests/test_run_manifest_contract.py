from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
CREATE = ROOT / "scripts/agent/create_run_manifest.py"
CHECK = ROOT / "scripts/agent/check_run_manifest.py"


def _create(tmp_path: Path, *, schema_version: int = 1) -> Path:
    for name in ("commands.log", "stdout.log", "stderr.log"):
        (tmp_path / name).write_text(name + "\n")
    output = tmp_path / "manifest.json"
    config = tmp_path / "test-config.yaml"
    config.write_text("test: true\n")
    command = [
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
        "--config",
        str(config),
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
    if schema_version == 2:
        command.extend(
            [
                "--schema-version",
                "2",
                "--validation-shape",
                "unit:manifest-contract",
                "--termination-kind",
                "success",
            ]
        )
    result = subprocess.run(command)
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


def test_run_manifest_without_config_binding_is_rejected(tmp_path):
    output = _create(tmp_path)
    payload = json.loads(output.read_text())
    payload["config_path"] = None
    payload["config_digest"] = None
    body = dict(payload)
    body.pop("manifest_sha256")
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    payload["manifest_sha256"] = hashlib.sha256(encoded).hexdigest()
    output.write_text(json.dumps(payload))
    assert subprocess.run([sys.executable, str(CHECK), str(output)]).returncode != 0


def test_v2_manifest_is_created_and_validated(tmp_path):
    output = _create(tmp_path, schema_version=2)
    payload = json.loads(output.read_text())
    assert payload["schema_version"] == 2
    assert payload["validation_shape"] == "unit:manifest-contract"
    assert payload["termination_kind"] == "success"
    assert set(payload["same_commit_qualification"]) == {
        "targeted_1node_benchmark",
        "miyabi_1node",
        "miyabi_2node",
    }
    assert subprocess.run([sys.executable, str(CHECK), str(output)]).returncode == 0


def test_v2_manifest_result_and_termination_must_agree(tmp_path):
    output = _create(tmp_path, schema_version=2)
    payload = json.loads(output.read_text())
    payload["termination_kind"] = "operator_terminated"
    body = dict(payload)
    body.pop("manifest_sha256")
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    payload["manifest_sha256"] = hashlib.sha256(encoded).hexdigest()
    output.write_text(json.dumps(payload))
    result = subprocess.run(
        [sys.executable, str(CHECK), str(output)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode != 0
    assert "inconsistent" in result.stderr


@pytest.mark.parametrize("phase", ["P05", "P06A", "P06B", "P06C"])
def test_distributed_route_defaults_to_v2_and_requires_validation_shape(tmp_path, phase):
    config = tmp_path / "test-config.yaml"
    config.write_text("test: true\n")
    result = subprocess.run(
        [
            sys.executable,
            str(CREATE),
            "--root",
            str(ROOT),
            "--output",
            str(tmp_path / "manifest.json"),
            "--phase",
            phase,
            "--purpose",
            "unit",
            "--config",
            str(config),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode != 0
    assert "schema version 2 requires --validation-shape" in result.stderr


def test_p05_cannot_explicitly_downgrade_to_v1(tmp_path):
    config = tmp_path / "test-config.yaml"
    config.write_text("test: true\n")
    result = subprocess.run(
        [
            sys.executable,
            str(CREATE),
            "--root",
            str(ROOT),
            "--output",
            str(tmp_path / "manifest.json"),
            "--phase",
            "P05",
            "--purpose",
            "unit",
            "--config",
            str(config),
            "--schema-version",
            "1",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode != 0
    assert "P05 requires schema version 2" in result.stderr


def test_preallocation_cancellation_requires_scheduler_evidence(tmp_path):
    output = _create(tmp_path, schema_version=2)
    payload = json.loads(output.read_text())
    payload["result"] = "inconclusive"
    payload["exit_code"] = None
    payload["termination_kind"] = "pre_allocation_cancelled"
    body = dict(payload)
    body.pop("manifest_sha256")
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    payload["manifest_sha256"] = hashlib.sha256(encoded).hexdigest()
    output.write_text(json.dumps(payload))
    result = subprocess.run(
        [sys.executable, str(CHECK), str(output)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode != 0
    assert "missing scheduler evidence" in result.stderr
