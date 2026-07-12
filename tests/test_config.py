import pytest

from fs_diloco.config import load_config, resolve_config


def test_config_defaults_and_cli_overrides(tmp_path):
    config = resolve_config(
        "configs/fs_diloco_tiny_local.yaml",
        run_id="test_run",
        shared_root=str(tmp_path / "run"),
        num_learners=1,
        project_root=tmp_path,
    )
    assert config.run.run_id == "test_run"
    assert config.run.shared_root == str(tmp_path / "run")
    assert config.sync.num_learners == 1
    assert config.sync.quorum_min == 1
    assert config.inner_optimizer.betas == (0.9, 0.95)
    assert config.fragments.enabled is False
    assert config.sync.staleness_lambda == 0.2
    assert config.sync.selection_policy == "oldest_pending"
    assert config.io.keep_last_global_versions is None
    assert config.io.keep_last_learner_update_versions is None


def test_config_defaults_keep_all_writable_state_inside_project(tmp_path):
    config = resolve_config(
        "configs/fs_diloco_tiny_local.yaml",
        run_id="contained_run",
        project_root=tmp_path,
    )
    assert config.run.shared_root == str(tmp_path / "runs/fs_diloco/contained_run")
    assert config.data.cache_dir == str(tmp_path / ".cache/fs_diloco/huggingface/datasets")


def test_config_rejects_runtime_paths_outside_project(tmp_path):
    with pytest.raises(ValueError, match="must stay inside project root"):
        resolve_config(
            "configs/fs_diloco_tiny_local.yaml",
            run_id="escaped_run",
            project_root=tmp_path,
            shared_root=str(tmp_path.parent / "outside"),
        )


def test_config_rejects_data_cache_outside_project(tmp_path):
    config_path = tmp_path / "outside-cache.yaml"
    config_path.write_text(
        f"data:\n  cache_dir: {tmp_path.parent / 'outside-cache'}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="data.cache_dir must stay inside project root"):
        resolve_config(config_path, run_id="escaped_cache", project_root=tmp_path)


def test_fragment_config_and_unknown_keys(tmp_path):
    good = tmp_path / "good.yaml"
    good.write_text(
        """
run:
  name: fragment
fragments:
  enabled: true
  strategy: balanced_tensor
  num_fragments: 4
""",
        encoding="utf-8",
    )
    config = load_config(good)
    assert config.fragments.enabled is True
    assert config.fragments.num_fragments == 4

    bad_top = tmp_path / "bad_top.yaml"
    bad_top.write_text("unknown_section: {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown config key"):
        load_config(bad_top)

    bad_nested = tmp_path / "bad_nested.yaml"
    bad_nested.write_text("sync:\n  mode: fragment\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown config key"):
        load_config(bad_nested)


def test_grace_window_must_fit_inside_lease_renewal_budget(tmp_path):
    path = tmp_path / "unsafe-grace.yaml"
    path.write_text(
        """
sync:
  grace_window:
    fixed_seconds: 31
    max_seconds: 31
coordination:
  lease_ttl_seconds: 45
  renew_margin_seconds: 15
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="grace_window"):
        resolve_config(path, run_id="unsafe-grace", project_root=tmp_path)
