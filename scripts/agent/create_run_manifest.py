#!/usr/bin/env python3
"""Create a non-overwriting validation run manifest bound to Git and config."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import uuid


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip())
    return proc.stdout.rstrip("\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", required=True, choices=[f"P{i:02d}" for i in range(13)])
    parser.add_argument(
        "--purpose",
        required=True,
        choices=["unit", "contract", "smoke", "chaos", "benchmark", "experiment"],
    )
    parser.add_argument("--run-id")
    parser.add_argument("--parent-run-id")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--backend", default="memory")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--dataset-revision")
    parser.add_argument("--model-revision")
    parser.add_argument("--hostname")
    parser.add_argument("--pbs-job-id")
    parser.add_argument("--pbs-nodefile-digest")
    parser.add_argument("--commands-log", default="commands.log")
    parser.add_argument("--stdout", default="stdout.log")
    parser.add_argument("--stderr", default="stderr.log")
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--result", choices=["pass", "fail", "inconclusive"], default="inconclusive")
    parser.add_argument("--assertion", action="append", default=[])
    parser.add_argument("--started-at-utc")
    parser.add_argument("--ended-at-utc")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    if output.exists():
        print(f"refusing to overwrite immutable manifest: {output}", file=sys.stderr)
        return 2
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    status = _git(root, "status", "--porcelain=v1").splitlines()
    nodefile_digest = None
    nodefile = os.environ.get("PBS_NODEFILE")
    if nodefile and Path(nodefile).is_file():
        nodefile_digest = _sha256(Path(nodefile))
    config_path = None
    config_digest = None
    if args.config:
        config = args.config if args.config.is_absolute() else root / args.config
        if not config.is_file():
            print(f"config does not exist: {config}", file=sys.stderr)
            return 2
        config_path = config.relative_to(root).as_posix() if config.is_relative_to(root) else str(config)
        config_digest = _sha256(config)
    payload = {
        "schema_version": 1,
        "run_id": args.run_id or str(uuid.uuid4()),
        "parent_run_id": args.parent_run_id,
        "purpose": args.purpose,
        "phase": args.phase,
        "git_commit": _git(root, "rev-parse", "HEAD"),
        "git_branch": _git(root, "branch", "--show-current"),
        "dirty_tree": bool(status),
        "dirty_paths": status,
        "hostname": args.hostname or platform.node(),
        "python_version": platform.python_version(),
        "pbs_job_id": args.pbs_job_id or os.environ.get("PBS_JOBID"),
        "pbs_nodefile_digest": args.pbs_nodefile_digest or nodefile_digest,
        "config_path": config_path,
        "config_digest": config_digest,
        "dataset_revision": args.dataset_revision,
        "model_revision": args.model_revision,
        "backend": args.backend,
        "seed": args.seed,
        "commands_log": args.commands_log,
        "stdout": args.stdout,
        "stderr": args.stderr,
        "exit_code": args.exit_code,
        "started_at_utc": args.started_at_utc or now,
        "ended_at_utc": args.ended_at_utc or now,
        "result": args.result,
        "assertions": args.assertion,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["manifest_sha256"] = hashlib.sha256(encoded).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
