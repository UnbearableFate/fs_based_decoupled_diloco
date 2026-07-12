#!/usr/bin/env python3
"""Build the P06B D8 correctness, resource, I/O, and latency report."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean

from fs_diloco.log.production import ProductionTransactionalLog
from fs_diloco.runtime_view import build_runtime_view
from fs_diloco.storage import PosixStorageBackend


def _jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _summary(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "min": min(values) if values else None,
        "mean": mean(values) if values else None,
        "max": max(values) if values else None,
    }


def _authority_inventory(root: Path) -> dict[str, int]:
    files = [
        path
        for path in root.rglob("*")
        if path.is_file() and "/.duraloco-locks/" not in path.as_posix()
    ]
    return {
        "observed_object_files": len(files),
        "observed_physical_bytes": sum(path.stat().st_size for path in files),
        "prepared_object_files": sum("/distributed/prepared/" in path.as_posix() for path in files),
        "work_order_object_files": sum(
            "/distributed/work-orders/" in path.as_posix() for path in files
        ),
    }


def build(
    root: Path,
    artifacts: Path,
    run_id: str,
    elapsed: int,
    *,
    max_elapsed_seconds: int = 900,
) -> dict[str, object]:
    summary = json.loads((artifacts / "training_summary.json").read_text(encoding="utf-8"))
    log = ProductionTransactionalLog.open(PosixStorageBackend(root / "authority"), run_id, 0)
    view = build_runtime_view(log, force_full=True)
    committer_events = _jsonl(root / "logs/distributed_committer.jsonl")
    commits = [
        row
        for row in committer_events
        if row.get("event_type") == "distributed_transition_committed"
    ]
    all_executor_events = [
        row
        for path in sorted((root / "logs").glob("distributed_executor_*.jsonl"))
        for row in _jsonl(path)
    ]
    executor_starts = [
        row for row in all_executor_events if row.get("event_type") == "executor_started"
    ]
    executor_events = [
        row for row in all_executor_events if row.get("event_type") == "fragment_prepared"
    ]
    executor_by_order = {str(row["work_order_id"]): row for row in executor_events}
    learner_events = [
        row
        for path in sorted((root / "logs").glob("learner_*.jsonl"))
        for row in _jsonl(path)
    ]
    metrics = list(csv.DictReader((root / "metrics/learner_metrics.csv").open()))
    losses = [float(row["train_loss"]) for row in metrics if row.get("train_loss")]
    gpu_steps = [
        float(row["gpu_step_seconds"])
        for row in learner_events
        if row.get("event_type") == "inner_step_summary" and row.get("gpu_step_seconds") is not None
    ]
    adoption_by_commit: dict[int, list[float]] = {}
    for row in learner_events:
        if row.get("event_type") == "global_adopted":
            adoption_by_commit.setdefault(int(row["version"]), []).append(float(row["timestamp"]))
    latency_rows = []
    for commit in commits:
        executor = executor_by_order[str(commit["work_order_id"])]
        commit_at = float(commit["timestamp"])
        published_at = commit_at - float(commit["publish_to_commit_seconds"])
        adoptions = adoption_by_commit.get(int(commit["commit_seq"]), [])
        latency_rows.append(
            {
                "commit_seq": int(commit["commit_seq"]),
                "work_order_id": commit["work_order_id"],
                "publish_to_prepare_start_seconds": (
                    float(executor["prepare_started_at"]) - published_at
                ),
                "prepare_seconds": float(executor["prepare_seconds"]),
                "prepare_to_commit_seconds": commit_at - float(executor["prepare_finished_at"]),
                "commit_to_first_adopt_seconds": min(adoptions) - commit_at if adoptions else None,
                "commit_to_last_adopt_seconds": max(adoptions) - commit_at if adoptions else None,
                "adoption_count": len(adoptions),
            }
        )
    markers = [
        path
        for path in (root / "authority").rglob("*.json")
        if "/distributed/prepared/markers/" in path.as_posix()
    ]
    resource = {
        "cpu_affinity_by_executor": {
            str(row["member_id"]): row["cpu_affinity"] for row in executor_starts
        },
        "numa_mems_allowed_by_executor": {
            str(row["member_id"]): row["numa_mems_allowed_list"] for row in executor_starts
        },
        "threads": sorted({int(row["threads"]) for row in executor_starts}),
        "rss_bytes": _summary([float(row["rss_bytes"]) for row in executor_events]),
        "gpu_step_seconds": _summary(gpu_steps),
        "learner_tokens_per_second": _summary(
            [float(row["tokens_per_sec"]) for row in metrics if row.get("tokens_per_sec")]
        ),
        "lfe_effective_io_bytes_per_second": _summary(
            [
                (float(row["input_bytes"]) + float(row["output_bytes"]))
                / max(float(row["prepare_seconds"]), 1e-9)
                for row in executor_events
            ]
        ),
    }
    io = {
        "executor_input_bytes": sum(int(row["input_bytes"]) for row in executor_events),
        "executor_output_bytes": sum(int(row["output_bytes"]) for row in executor_events),
        "executor_logical_input_reads": sum(
            int(row["logical_input_reads"]) for row in executor_events
        ),
        "executor_logical_prepare_writes": sum(
            int(row["logical_prepare_writes"]) for row in executor_events
        ),
        "accounting_scope": (
            "logical LFE object operations plus observed terminal authority inventory; "
            "not kernel-level Lustre RPC counters"
        ),
        **_authority_inventory(root / "authority"),
    }
    report = {
        "status": "PASS",
        "learner_nodes": 8,
        "learners": 8,
        "executors": 8,
        "dedicated_syncer_nodes": 0,
        "committer_candidates": 8,
        "running_committer_processes": 2,
        "optimizer_transitions": view.optimizer_transition_count,
        "membership_revision": view.membership.revision if view.membership else None,
        "prepared_markers": len(markers),
        "distributed_commits": len(commits),
        "executor_prepare_events": len(executor_events),
        "executor_start_events": len(executor_starts),
        "finite_loss_count": len(losses),
        "invalid_losses": sum(not math.isfinite(value) for value in losses),
        "elapsed_seconds": elapsed,
        "resource_telemetry": resource,
        "lustre_io_telemetry": io,
        "transition_latency": latency_rows,
        "stop_reason": summary["stop_reason"],
        "coordination_protocol": log.spec.coordination_protocol,
        "control_sequence": [
            row.control_kind
            for row in log.replay(force_full=True).commits
            if hasattr(row, "control_kind")
        ],
    }
    assert report["optimizer_transitions"] == report["distributed_commits"] == 10
    assert report["prepared_markers"] == report["executor_prepare_events"] == 10
    assert report["executor_start_events"] == 8
    assert losses and report["invalid_losses"] == 0 and elapsed <= max_elapsed_seconds
    assert report["membership_revision"] == 0
    assert report["coordination_protocol"] == "distributed-head-fenced-v1"
    assert report["stop_reason"] == "stop_after_outer_steps"
    assert report["control_sequence"] == ["epoch_bump", "stop"]
    assert len(resource["cpu_affinity_by_executor"]) == 8 and gpu_steps
    assert all(row["prepare_to_commit_seconds"] >= 0 for row in latency_rows)
    assert sum(int(row["adoption_count"]) for row in latency_rows) >= 1
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--elapsed-seconds", type=int, required=True)
    parser.add_argument("--max-elapsed-seconds", type=int, default=900)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build(
        args.root,
        args.artifacts,
        args.run_id,
        args.elapsed_seconds,
        max_elapsed_seconds=args.max_elapsed_seconds,
    )
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
