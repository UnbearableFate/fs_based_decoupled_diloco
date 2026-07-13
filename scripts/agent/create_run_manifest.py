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
import re
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
    parser.add_argument(
        "--phase",
        required=True,
        choices=[
            "H0",
            "M00",
            *[f"P{i:02d}" for i in range(13)],
            "P08R",
            "P06A",
            "P06B",
            "P06C",
        ],
    )
    parser.add_argument(
        "--purpose",
        required=True,
        choices=["unit", "contract", "smoke", "chaos", "benchmark", "experiment"],
    )
    parser.add_argument("--run-id")
    parser.add_argument("--parent-run-id")
    parser.add_argument("--schema-version", type=int, choices=[1, 2])
    parser.add_argument("--validation-shape")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--backend", default="memory")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--dataset-revision")
    parser.add_argument("--model-revision")
    parser.add_argument("--hostname")
    parser.add_argument("--pbs-job-id")
    parser.add_argument("--pbs-nodefile-digest")
    parser.add_argument("--pbs-queue")
    parser.add_argument("--requested-resources")
    parser.add_argument("--last-qstat-state")
    parser.add_argument("--termination-detail")
    parser.add_argument("--commands-log", default="commands.log")
    parser.add_argument("--stdout", default="stdout.log")
    parser.add_argument("--stderr", default="stderr.log")
    parser.add_argument("--exit-code", type=int)
    parser.add_argument(
        "--result", choices=["pass", "fail", "inconclusive"], default="inconclusive"
    )
    parser.add_argument(
        "--termination-kind",
        choices=[
            "success",
            "test_failure",
            "operator_terminated",
            "scheduler_timeout",
            "infrastructure",
            "pre_allocation_cancelled",
            "unknown",
        ],
    )
    parser.add_argument("--authority-head-before")
    parser.add_argument("--authority-head-after")
    parser.add_argument("--stage-metrics-path")
    parser.add_argument("--workflow-review-path")
    parser.add_argument("--qualification-targeted-1node-benchmark")
    parser.add_argument("--qualification-miyabi-1node")
    parser.add_argument("--qualification-miyabi-2node")
    parser.add_argument("--assertion", action="append", default=[])
    parser.add_argument("--started-at-utc")
    parser.add_argument("--ended-at-utc")
    parser.add_argument("--git-commit-override")
    parser.add_argument("--git-branch-override")
    parser.add_argument("--clean-tree-override", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    v2_phases = {
        "H0",
        "P05",
        "P06",
        "P06A",
        "P06B",
        "P06C",
        "P07",
        "P08",
        "P08R",
        "P09",
        "P10",
        "P11",
        "P12",
    }
    schema_version = args.schema_version
    if schema_version is None:
        schema_version = 2 if args.phase in v2_phases else 1
    if args.phase in v2_phases and schema_version != 2:
        print(f"{args.phase} requires schema version 2", file=sys.stderr)
        return 2
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    if output.exists():
        print(f"refusing to overwrite immutable manifest: {output}", file=sys.stderr)
        return 2
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    status = _git(root, "status", "--porcelain=v1").splitlines()
    if args.clean_tree_override:
        status = []
    git_commit = args.git_commit_override or _git(root, "rev-parse", "HEAD")
    if re.fullmatch(r"[0-9a-f]{40}", git_commit) is None:
        print("git commit override must be 40 lowercase hex", file=sys.stderr)
        return 2
    nodefile_digest = None
    nodefile = os.environ.get("PBS_NODEFILE")
    if nodefile and Path(nodefile).is_file():
        nodefile_digest = _sha256(Path(nodefile))
    config = args.config if args.config.is_absolute() else root / args.config
    if not config.is_file():
        print(f"config does not exist: {config}", file=sys.stderr)
        return 2
    config_path = (
        config.relative_to(root).as_posix() if config.is_relative_to(root) else str(config)
    )
    config_digest = _sha256(config)
    if schema_version == 2 and not args.validation_shape:
        print("schema version 2 requires --validation-shape", file=sys.stderr)
        return 2
    termination_kind = args.termination_kind
    if schema_version == 2 and termination_kind is None:
        termination_kind = {
            "pass": "success",
            "fail": "test_failure",
            "inconclusive": "unknown",
        }[args.result]
    if schema_version == 2:
        allowed_terminations = {
            "pass": {"success"},
            "fail": {
                "test_failure",
                "operator_terminated",
                "scheduler_timeout",
                "infrastructure",
            },
            "inconclusive": {
                "operator_terminated",
                "scheduler_timeout",
                "infrastructure",
                "pre_allocation_cancelled",
                "unknown",
            },
        }
        if termination_kind not in allowed_terminations[args.result]:
            print(
                f"termination kind {termination_kind!r} is inconsistent with "
                f"result {args.result!r}",
                file=sys.stderr,
            )
            return 2
        if termination_kind == "pre_allocation_cancelled":
            cancellation_evidence = {
                "pbs_job_id": args.pbs_job_id or os.environ.get("PBS_JOBID"),
                "pbs_queue": args.pbs_queue,
                "requested_resources": args.requested_resources,
                "last_qstat_state": args.last_qstat_state,
                "termination_detail": args.termination_detail,
            }
            missing = [field for field, value in cancellation_evidence.items() if not value]
            if missing:
                print(
                    "pre-allocation cancellation requires scheduler evidence: "
                    + ", ".join(missing),
                    file=sys.stderr,
                )
                return 2
    payload = {
        "schema_version": schema_version,
        "run_id": args.run_id or str(uuid.uuid4()),
        "parent_run_id": args.parent_run_id,
        "purpose": args.purpose,
        "phase": args.phase,
        "git_commit": git_commit,
        "git_branch": args.git_branch_override or _git(root, "branch", "--show-current"),
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
    if schema_version == 2:
        payload.update(
            {
                "validation_shape": args.validation_shape,
                "termination_kind": termination_kind,
                "authority_head_before": args.authority_head_before,
                "authority_head_after": args.authority_head_after,
                "stage_metrics_path": args.stage_metrics_path,
                "workflow_review_path": args.workflow_review_path,
                "same_commit_qualification": {
                    "targeted_1node_benchmark": args.qualification_targeted_1node_benchmark,
                    "miyabi_1node": args.qualification_miyabi_1node,
                    "miyabi_2node": args.qualification_miyabi_2node,
                },
                "pbs_queue": args.pbs_queue,
                "requested_resources": args.requested_resources,
                "last_qstat_state": args.last_qstat_state,
                "termination_detail": args.termination_detail,
            }
        )
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["manifest_sha256"] = hashlib.sha256(encoded).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
