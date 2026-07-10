from __future__ import annotations

from pathlib import Path
import csv
import json

import yaml

from fs_diloco.log.training_probe import run_probe


ROOT = Path(__file__).resolve().parents[2]


def test_terminal_milestone_config_is_real_gpt2_50x10():
    config = yaml.safe_load(
        (ROOT / "configs/duraloco_milestone_gpt2_9node_50x10.yaml").read_text()
    )
    assert config["model"]["name_or_path"] == "gpt2"
    assert config["data"]["dataset_name"] == "wikitext"
    assert config["data"]["dataset_config_name"] == "wikitext-2-raw-v1"
    assert config["sync"]["num_learners"] == 8
    assert config["training"]["inner_steps"] == 50
    assert config["sync"]["stop_after_outer_steps"] == 10
    assert config["io"]["keep_last_global_versions"] == 11


def test_terminal_milestone_pbs_is_nine_nodes_and_hard_15_minutes():
    script = (
        ROOT / "scripts/miyabi/run_duraloco_milestone_9node_gpt2_50x10.pbs"
    ).read_text()
    assert "#PBS -l select=9:mpiprocs=1" in script
    assert "#PBS -l walltime=00:15:00" in script
    assert "-np 9" in script
    assert "fs_diloco.log.training_probe" in script
    assert "tests/log" in script


def test_p04_state_cannot_claim_the_terminal_gate_before_runtime_evidence():
    state = yaml.safe_load((ROOT / "plans/duraloco/phases/P04_STATE.yaml").read_text())
    assert state["checks"]["miyabi_9node"] == "not_run"
    assert state["status"] == "in_progress"


def test_p04_report_is_bilingual_and_records_the_terminal_gate():
    report = (ROOT / "plans/duraloco/phases/P04_PHASE_REPORT.md").read_text()
    assert "## English" in report
    assert "## 中文" in report
    assert "9-node" in report
    assert "50×10" in report


def test_terminal_probe_binds_a_50x10_training_artifact_bundle(tmp_path):
    training = tmp_path / "training"
    for directory in ("control", "heartbeats", "metrics", "weights", "logs"):
        (training / directory).mkdir(parents=True, exist_ok=True)
    checkpoints = []
    for version in range(11):
        checkpoint = training / "weights" / f"global_v{version:06d}.safetensors"
        checkpoint.write_bytes(f"real-checkpoint-surrogate-{version}".encode())
        checkpoints.append(checkpoint)
    (training / "control" / "latest.json").write_text(
        json.dumps({"version": 10, "weight_path": str(checkpoints[-1])})
    )
    (training / "control" / "stop.json").write_text(
        json.dumps({"version": 10, "reason": "stop_after_outer_steps"})
    )
    (training / "control" / "param_index.json").write_text(
        json.dumps({"format_version": 1, "parameters": []})
    )
    for index in range(8):
        (training / "heartbeats" / f"learner_{index:03d}.json").write_text(
            json.dumps({"last_local_step": 50})
        )
    with (training / "metrics" / "learner_metrics.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["learner_id", "train_loss"])
        writer.writeheader()
        for index in range(8):
            writer.writerow({"learner_id": f"learner_{index:03d}", "train_loss": 4.0})
    with (training / "metrics" / "syncer_metrics.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["version", "selected_count", "total_update_tokens"]
        )
        writer.writeheader()
        for version in range(1, 11):
            writer.writerow(
                {"version": version, "selected_count": 4, "total_update_tokens": 1000}
            )
    payload = run_probe(
        training_root=training,
        config_path=ROOT / "configs/duraloco_milestone_gpt2_9node_50x10.yaml",
        storage_root=tmp_path / "p04-store",
        run_id="terminal-probe-test",
        output=tmp_path / "terminal_report.json",
        artifact_root=tmp_path / "artifacts",
    )
    assert payload["status"] == "PASS"
    assert payload["global_outer_transitions"] == 10
    assert payload["p04_projection_commit_seq"] == 10
    assert all(payload["assertions"].values())
