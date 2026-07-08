from fs_diloco.config import resolve_config


def test_config_defaults_and_cli_overrides(tmp_path):
    config = resolve_config(
        "configs/fs_diloco_tiny_local.yaml",
        run_id="test_run",
        shared_root=str(tmp_path / "run"),
        sqlite_local_dir=str(tmp_path / "db"),
        num_learners=1,
    )
    assert config.run.run_id == "test_run"
    assert config.run.shared_root == str(tmp_path / "run")
    assert config.io.sqlite_local_dir == str(tmp_path / "db")
    assert config.sync.num_learners == 1
    assert config.sync.quorum_min == 1
    assert config.inner_optimizer.betas == (0.9, 0.95)
