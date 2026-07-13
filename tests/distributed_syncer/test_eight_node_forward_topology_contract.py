from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_forward_milestone_config_is_eight_learner_50x10() -> None:
    path = ROOT / "configs/duraloco_milestone_gpt2_8node_50x10.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert config["run"]["name"] == "duraloco_milestone_gpt2_8node_50x10"
    assert config["sync"]["num_learners"] == 8
    assert config["training"]["inner_steps"] == 50
    assert config["sync"]["stop_after_outer_steps"] == 10
    assert "9-node" not in path.read_text(encoding="utf-8")


def test_forward_d8_wrappers_allocate_and_launch_exactly_eight_hosts() -> None:
    for name in ("run_duraloco_p08_d8.pbs", "run_duraloco_p08_d8_r2.pbs"):
        script = (ROOT / "scripts/miyabi" / name).read_text(encoding="utf-8")

        assert "#PBS -l select=8:mpiprocs=1" in script
        assert "--requested-resources select=8:mpiprocs=1" in script
        assert '[[ "${#ALL_HOSTS[@]}" -eq 8 ]]' in script
        assert "-np 8" in script
        assert "control_plane_host.log" not in script
        assert "select=9" not in script
        assert "create_p08r_elapsed_report.py" in script
        assert "runtime_started_ns" in script
        assert "runtime_ended_ns" in script
        assert (
            'mkdir -p "$(dirname "$ARTIFACT_ROOT")" '
            '"$(dirname "$STORAGE_ROOT")"' in script
        )
        assert 'if ! mkdir "$STORAGE_ROOT"; then' in script
        assert 'if ! mkdir "$ARTIFACT_ROOT"; then' in script


def test_forward_report_binding_is_exactly_eight_nodes() -> None:
    source = (
        ROOT / "scripts/agent/create_p08_performance_report.py"
    ).read_text(encoding="utf-8")

    assert "len(set(hosts)) != 8" in source
    assert '"allocation_nodes": 8' in source
    assert "requires nine hosts" not in source


def test_forward_r2_comparison_does_not_require_c9() -> None:
    script = (
        ROOT / "scripts/miyabi/run_duraloco_p08_d8_r2.pbs"
    ).read_text(encoding="utf-8")

    assert "NO_LFE_REPORT" not in script
    assert "--no-lfe-report" not in script
