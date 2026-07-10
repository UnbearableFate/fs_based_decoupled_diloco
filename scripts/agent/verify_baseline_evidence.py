#!/usr/bin/env python3
"""Verify a run from its committed log and file-native telemetry."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from fs_diloco.analysis import summarize_run


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def verify(root: Path) -> dict[str, object]:
    summary = summarize_run(root)
    required = [
        root / "control" / "run_config.resolved.yaml",
        root / "control" / "param_index.json",
        root / "logs" / "syncer.jsonl",
        root / "metrics" / "syncer_metrics.csv",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError(f"required evidence is missing: {missing}")
    flags = summary["syncer_log_flags"]
    if any(flags.values()):
        raise ValueError(f"syncer failure flags are present: {flags}")
    if summary["commit_seq"] < 1 or summary["consumed_proposal_count"] < 1:
        raise ValueError("committed prefix contains no applied transition")
    if not summary["latest_export_valid"]:
        raise ValueError("materialized latest export does not match the committed head")
    return {
        "status": "PASS",
        "authority": "committed-transition-log",
        "commit_seq": summary["commit_seq"],
        "commit_id": summary["commit_id"],
        "committed_state_digest": summary["committed_state_digest"],
        "runtime_view_digest": summary["runtime_view_digest"],
        "consumed_proposal_count": summary["consumed_proposal_count"],
        "evidence_sha256": {str(path.relative_to(root)): _digest(path) for path in required},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.run_root)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
