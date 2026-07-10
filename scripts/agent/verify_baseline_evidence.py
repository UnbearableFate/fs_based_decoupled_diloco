#!/usr/bin/env python3
"""Validate a representative legacy run without recursively hashing tensors."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "size": path.stat().st_size,
        "sha256": _sha256(path),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.run_root.resolve()
    output = args.output.resolve()
    if output.exists():
        print(f"refusing to overwrite evidence: {output}", file=sys.stderr)
        return 2
    required = [
        root / "control/latest.json",
        root / "control/run_config.resolved.yaml",
        root / "control/param_index.json",
    ]
    logs = sorted((root / "logs").glob("*.jsonl"))
    weights = sorted((root / "weights").glob("*.safetensors"))
    db_dumps = sorted((root / "db_dumps").glob("*.db"))
    missing = [str(path) for path in required if not path.is_file()]
    if not logs:
        missing.append("logs/*.jsonl")
    if not weights:
        missing.append("weights/*.safetensors")
    if not db_dumps:
        missing.append("db_dumps/*.db")
    if missing:
        print("missing baseline artifacts: " + ", ".join(missing), file=sys.stderr)
        return 2
    latest = json.loads(required[0].read_text(encoding="utf-8"))
    has_materialization = isinstance(latest, dict) and any(
        key in latest
        for key in ("weight_path", "weights_path", "materialized_weight_path", "fragments")
    )
    if not isinstance(latest, dict) or "version" not in latest or not has_materialization:
        print("latest.json lacks version or a global/fragment materialization", file=sys.stderr)
        return 2
    events: dict[str, int] = {}
    invalid_log_lines = 0
    finite_losses = 0
    nonfinite_losses = 0
    for log_path in logs:
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                invalid_log_lines += 1
                continue
            name = str(event.get("event", "unknown"))
            events[name] = events.get(name, 0) + 1
            if "loss" in event:
                try:
                    loss = float(event["loss"])
                    if loss == loss and abs(loss) != float("inf"):
                        finite_losses += 1
                    else:
                        nonfinite_losses += 1
                except (TypeError, ValueError):
                    nonfinite_losses += 1
    connection = sqlite3.connect(f"file:{db_dumps[-1]}?mode=ro", uri=True)
    try:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        table_counts = {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in tables
            if re_safe_identifier(table)
        }
    finally:
        connection.close()
    sampled = required + [logs[0], logs[-1], weights[-1], db_dumps[-1]]
    payload = {
        "schema_version": 1,
        "kind": "legacy-run-sample",
        "run_root": str(root),
        "latest": latest,
        "events": events,
        "invalid_log_lines": invalid_log_lines,
        "finite_loss_events": finite_losses,
        "nonfinite_loss_events": nonfinite_losses,
        "sqlite_tables": table_counts,
        "sampled_artifacts": [_record(path, root) for path in dict.fromkeys(sampled)],
        "limitations": [
            "legacy run is observational baseline, not Protocol v2 authority evidence",
            "only representative control/log/DB/tensor artifacts are hashed",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def re_safe_identifier(value: str) -> bool:
    return bool(value) and all(character.isalnum() or character == "_" for character in value)


if __name__ == "__main__":
    raise SystemExit(main())
