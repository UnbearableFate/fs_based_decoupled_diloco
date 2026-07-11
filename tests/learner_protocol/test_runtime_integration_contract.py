from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import fs_diloco.learner as learner
from fs_diloco.config import Config, resolve_config


def test_public_learner_entrypoints_share_the_single_runtime():
    root = Path(__file__).resolve().parents[2]
    project = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'fs-diloco-learner = "fs_diloco.learner:main"' in project
    assert "if __name__ == \"__main__\":" in inspect.getsource(learner)
    assert not (root / "fs_diloco" / "learner_v2.py").exists()


def test_learner_publication_has_no_head_cas_surface():
    source = inspect.getsource(learner)
    publication_source = inspect.getsource(
        __import__("fs_diloco.learner_protocol.publication", fromlist=["LearnerPublisher"])
    )
    for forbidden in ("conditional_replace", ".head_key", "commit_prepared"):
        assert forbidden not in source
        assert forbidden not in publication_source
    assert "LearnerPublisher" in source
    assert ".publish(" in source


def test_runtime_defers_mid_interval_adoption_and_stops_on_no_progress():
    source = inspect.getsource(learner)
    assert "successor_observed_mid_interval" in source
    assert "adoption_deferred_to_boundary=True" in source
    assert '"no_progress"' in source
    assert 'outcome="terminal"' in source
    assert "if no_progress:\n                break" in source


def test_adoption_policy_default_and_validation(tmp_path):
    assert Config().learner.inner_optimizer_adoption_policy == "reset_all"
    path = tmp_path / "invalid.yaml"
    path.write_text(
        "learner:\n  inner_optimizer_adoption_policy: unknown\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="inner_optimizer_adoption_policy"):
        resolve_config(path, project_root=tmp_path)


def test_interval_metadata_freezes_numeric_and_recovery_identity():
    source = inspect.getsource(learner.write_fragment_update)
    for required in (
        "publication_request_id",
        "publication_request_digest",
        "publication_proposal_id",
        "interval_digest",
        "data_cursor_start",
        "data_cursor_end",
        "rng_cursor",
        "inner_optimizer_adoption_policy",
        "proposal-transport-to-float32-commit-v1",
    ):
        assert required in source
    assert source.count("read_bytes()") == 1
