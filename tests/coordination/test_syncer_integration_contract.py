from __future__ import annotations

import inspect

import pytest

import fs_diloco.syncer as syncer
import fs_diloco.analysis as analysis
import fs_diloco.log.training_probe as training_probe
from fs_diloco.config import Config, resolve_config


def test_p05_run_spec_freezes_head_fenced_coordination():
    config = Config()
    config.run.run_id = "run-test"
    spec = syncer._run_spec(
        config,
        parameter_digest="a" * 64,
        layout_digest="b" * 64,
    )
    assert spec.coordination_protocol == "head-fenced-v1"
    assert spec.to_dict()["coordination_protocol"] == "head-fenced-v1"


def test_coordination_defaults_fit_replay_and_renewal_budget():
    config = Config()
    assert config.coordination.lease_ttl_seconds == 45.0
    assert config.coordination.renew_interval_seconds == 10.0
    assert config.coordination.renew_margin_seconds == 15.0
    assert config.coordination.max_clock_skew_seconds == 2.0
    assert config.coordination.renew_interval_seconds < config.coordination.renew_margin_seconds
    assert config.coordination.renew_margin_seconds < config.coordination.lease_ttl_seconds


def test_invalid_coordination_config_fails_closed(tmp_path):
    path = tmp_path / "invalid.yaml"
    path.write_text(
        "coordination:\n  enabled: false\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="coordination.enabled"):
        resolve_config(path, project_root=tmp_path)


def test_public_syncer_cli_exposes_owner_and_standby_without_db_flags():
    args = syncer.parse_args(
        [
            "--config",
            "config.yaml",
            "--owner-id",
            "syncer-a",
            "--owner-session-id",
            "session-a",
            "--standby",
        ]
    )
    assert args.owner_id == "syncer-a"
    assert args.owner_session_id == "session-a"
    assert args.standby is True
    source = inspect.getsource(syncer.parse_args)
    assert "sqlite" not in source.casefold()
    assert "--db" not in source


def test_syncer_stop_and_takeover_use_committed_coordination_path():
    source = inspect.getsource(syncer)
    assert "log.activate_owner(" in source
    assert "log.commit_stop(" in source
    assert "standby_wait" in source
    assert "NotImplementedError" not in source
    assert "derived-from-committed-stop-control-transition" in source
    assert "view.optimizer_transition_count >= config.sync.stop_after_outer_steps" in source


def test_analysis_and_terminal_probe_count_only_optimizer_transitions():
    analysis_source = inspect.getsource(analysis)
    probe_source = inspect.getsource(training_probe)
    for source in (analysis_source, probe_source):
        assert "isinstance(commit, CommitManifest)" in source
    assert '"global_merge_event": view.optimizer_transition_count' in analysis_source
    assert '"global_outer_transitions": view.optimizer_transition_count' in probe_source
