"""CSV metrics helpers."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .atomic_io import ensure_dir


def append_csv_row(path: str | Path, row: dict[str, Any], fieldnames: list[str] | None = None) -> None:
    path = Path(path)
    ensure_dir(path.parent)
    if fieldnames is None:
        fieldnames = list(row.keys())
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


SYNCER_METRIC_FIELDS = [
    "timestamp",
    "version",
    "selected_count",
    "total_update_tokens",
    "read_seconds",
    "aggregation_seconds",
    "outer_step_seconds",
    "publish_seconds",
    "stale_updates_dropped",
    "global_interval_seconds",
]

LEARNER_METRIC_FIELDS = [
    "timestamp",
    "learner_id",
    "local_step",
    "global_version",
    "train_loss",
    "tokens",
    "tokens_per_sec",
    "update_write_seconds",
    "param_norm",
    "phase",
]

UPDATE_MANIFEST_FIELDS = [
    "timestamp",
    "update_id",
    "learner_id",
    "base_global_version",
    "local_step_start",
    "local_step_end",
    "tokens_this_update",
    "file_path",
    "file_size_bytes",
    "sha256",
]
