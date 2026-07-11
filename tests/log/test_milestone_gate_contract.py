from __future__ import annotations

from pathlib import Path

import yaml

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
    assert config["io"]["tensor_dtype"] == "bfloat16"
    assert config["sync"]["staleness_lambda"] == 0.2
    assert config["sync"]["selection_policy"] == "oldest_pending"


def test_terminal_milestone_pbs_is_nine_nodes_and_hard_15_minutes():
    script = (
        ROOT / "scripts/miyabi/run_duraloco_milestone_9node_gpt2_50x10.pbs"
    ).read_text()
    assert "#PBS -l select=9:mpiprocs=1" in script
    assert "#PBS -l walltime=00:15:00" in script
    assert "-np 9" in script
    assert "fs_diloco.log.training_probe" in script
    assert "tests/log" in script


def test_p04_state_tracks_the_terminal_gate_across_persistence_transitions():
    state = yaml.safe_load((ROOT / "plans/duraloco/phases/P04_STATE.yaml").read_text())
    assert state["status"] in {"in_progress", "checking", "completed"}
    expected = "not_run" if state["last_verified_commit"] is None else "miyabi_9node_pass"
    assert state["checks"]["miyabi_9node"] == expected


def test_p04_report_is_bilingual_and_records_the_terminal_gate():
    report = (ROOT / "plans/duraloco/phases/P04_PHASE_REPORT.md").read_text()
    assert "## English" in report
    assert "## 中文" in report
    assert "9-node" in report
    assert "50×10" in report


def test_terminal_probe_verifies_the_real_production_authority():
    source = (ROOT / "fs_diloco/log/training_probe.py").read_text()
    assert "ProductionTransactionalLog.open" in source
    assert "replay_log(log.transactional)" in source
    assert "proposal_inclusion_exactly_once" in source
    assert "production_log_is_authority" in source
