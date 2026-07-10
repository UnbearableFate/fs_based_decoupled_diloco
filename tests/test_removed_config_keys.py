from __future__ import annotations

import pytest

from fs_diloco.config import load_config
from fs_diloco.syncer import parse_args


@pytest.mark.parametrize(
    ("section", "key"),
    [
        ("init", "resume_db_dump"),
        ("sync", "db_dump_every_versions"),
        ("io", "keep_last_db_dumps"),
        ("io", "sqlite_local_dir"),
    ],
)
def test_removed_persistence_keys_fail_closed(tmp_path, section, key):
    config = tmp_path / "removed.yaml"
    config.write_text(f"{section}:\n  {key}: null\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown config key"):
        load_config(config)


def test_removed_command_option_fails_closed():
    with pytest.raises(SystemExit):
        parse_args(["--config", "config.yaml", "--sqlite-local-dir", "/tmp/legacy"])
