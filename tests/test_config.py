import pytest

from fs_diloco.config import load_config, resolve_config


def test_config_defaults_and_cli_overrides(tmp_path):
    config = resolve_config(
        "configs/fs_diloco_tiny_local.yaml",
        run_id="test_run",
        shared_root=str(tmp_path / "run"),
        sqlite_local_dir=str(tmp_path / "db"),
        num_learners=1,
        project_root=tmp_path,
    )
    assert config.run.run_id == "test_run"
    assert config.run.shared_root == str(tmp_path / "run")
    assert config.io.sqlite_local_dir == str(tmp_path / "db")
    assert config.sync.num_learners == 1
    assert config.sync.quorum_min == 1
    assert config.inner_optimizer.betas == (0.9, 0.95)
    assert config.fragments.enabled is False
    assert config.io.keep_last_db_dumps == 2
    assert config.io.keep_last_global_versions is None
    assert config.io.keep_last_learner_update_versions is None


def test_config_defaults_keep_all_writable_state_inside_project(tmp_path):
    config = resolve_config(
        "configs/fs_diloco_tiny_local.yaml",
        run_id="contained_run",
        project_root=tmp_path,
    )
    assert config.run.shared_root == str(tmp_path / "runs/fs_diloco/contained_run")
    assert config.io.sqlite_local_dir == str(
        tmp_path / ".runtime/fs_diloco/contained_run/sqlite"
    )
    assert config.data.cache_dir == str(tmp_path / ".cache/fs_diloco/huggingface/datasets")


@pytest.mark.parametrize("field", ["shared_root", "sqlite_local_dir"])
def test_config_rejects_runtime_paths_outside_project(tmp_path, field):
    kwargs = {field: str(tmp_path.parent / "outside")}
    with pytest.raises(ValueError, match="must stay inside project root"):
        resolve_config(
            "configs/fs_diloco_tiny_local.yaml",
            run_id="escaped_run",
            project_root=tmp_path,
            **kwargs,
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
