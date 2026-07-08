"""Inspect a filesystem DiLoCo run."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path
from typing import Any

from .atomic_io import safe_read_json


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shared_root", help="Run shared root")
    parser.add_argument("--db", help="SQLite DB or DB dump path")
    parser.add_argument("--json", action="store_true", help="Emit JSON summary")
    return parser.parse_args(argv)


def _read_csv_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "rows": 0}
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {"exists": True, "rows": len(rows), "last": rows[-1] if rows else None}


def _db_summary(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"exists": False}
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        applied = conn.execute("SELECT COUNT(*) AS n FROM updates WHERE status='applied'").fetchone()["n"]
        pending = conn.execute("SELECT COUNT(*) AS n FROM updates WHERE status='pending'").fetchone()["n"]
        dropped = conn.execute("SELECT COUNT(*) AS n FROM updates WHERE status='dropped'").fetchone()["n"]
        versions = conn.execute("SELECT COUNT(*) AS n FROM global_versions").fetchone()["n"]
        contributors = [
            dict(row)
            for row in conn.execute(
                """
                SELECT applied_version, learner_id, update_id, effective_weight
                FROM updates
                WHERE status='applied'
                ORDER BY applied_version, learner_id
                """
            )
        ]
    finally:
        conn.close()
    return {
        "exists": True,
        "applied_updates": applied,
        "pending_updates": pending,
        "dropped_updates": dropped,
        "global_versions": versions,
        "contributors": contributors,
    }


def summarize_run(shared_root: str | Path, db_path: str | Path | None = None) -> dict[str, Any]:
    root = Path(shared_root)
    latest = safe_read_json(root / "control" / "latest.json")
    stop = safe_read_json(root / "control" / "stop.json")
    if db_path is None:
        dumps = sorted((root / "db_dumps").glob("metadata_*_v*.db"))
        db = dumps[-1] if dumps else None
    else:
        db = Path(db_path)
    return {
        "shared_root": str(root),
        "latest": latest,
        "stop": stop,
        "syncer_metrics": _read_csv_summary(root / "metrics" / "syncer_metrics.csv"),
        "learner_metrics": _read_csv_summary(root / "metrics" / "learner_metrics.csv"),
        "update_manifest": _read_csv_summary(root / "metrics" / "update_manifest.csv"),
        "db": _db_summary(db),
    }


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    summary = summarize_run(args.shared_root, args.db)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    else:
        latest = summary["latest"] or {}
        stop = summary["stop"] or {}
        db = summary["db"]
        print(f"shared_root: {summary['shared_root']}")
        print(f"latest_version: {latest.get('version')}")
        print(f"stop_reason: {stop.get('reason')}")
        print(f"syncer_metric_rows: {summary['syncer_metrics']['rows']}")
        print(f"learner_metric_rows: {summary['learner_metrics']['rows']}")
        print(f"db_exists: {db.get('exists')}")
        if db.get("exists"):
            print(f"global_versions: {db.get('global_versions')}")
            print(f"applied_updates: {db.get('applied_updates')}")
            print(f"pending_updates: {db.get('pending_updates')}")
            print(f"dropped_updates: {db.get('dropped_updates')}")


if __name__ == "__main__":
    main()
