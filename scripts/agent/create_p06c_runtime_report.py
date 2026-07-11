#!/usr/bin/env python3
"""Audit a P06C factor-two run from strict committed replay and PFT markers."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from fs_diloco.distributed_syncer.layout import DistributedLayout
from fs_diloco.distributed_syncer.prepared_store import load_prepared_attempt
from fs_diloco.distributed_syncer.work_order_store import load_work_order
from fs_diloco.log.production import ProductionTransactionalLog
from fs_diloco.protocol.schemas import CommitManifest
from fs_diloco.protocol.work_order_v2 import RedundantFragmentWorkOrderV2
from fs_diloco.storage import PosixStorageBackend


def _jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-generation", type=int, default=1)
    parser.add_argument("--expected-mode", required=True)
    parser.add_argument("--expected-learners", type=int, required=True)
    parser.add_argument("--allow-degraded-attempts", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    backend = PosixStorageBackend(args.root / "authority")
    log = ProductionTransactionalLog.open(
        backend, args.run_id, args.run_generation
    )
    replay = log.replay(force_full=True)
    layout = DistributedLayout(log.layout)
    commits = [item for item in replay.commits if isinstance(item, CommitManifest)]
    if not commits:
        raise AssertionError("factor-two run has no optimizer transitions")

    lineage = []
    all_attempt_ids: set[str] = set()
    for commit in commits:
        if commit.distributed_work_order_id is None or commit.prepared_result_id is None:
            raise AssertionError("distributed commit does not bind FWO/PFR identity")
        order = load_work_order(backend, layout, commit.distributed_work_order_id)
        if not isinstance(order, RedundantFragmentWorkOrderV2):
            raise AssertionError("factor-two run published a factor-one work order")
        if order.redundancy_policy.mode != args.expected_mode:
            raise AssertionError("work-order mode differs from requested validation mode")
        marker_keys = backend.list_prefix(
            f"{layout.prepared_prefix}markers/{order.work_order_id}/"
        )
        attempts = [load_prepared_attempt(backend, key) for key in marker_keys]
        result_ids = {result.prepared_result_id for result, _ in attempts}
        executor_ids = {envelope.executor_id for _, envelope in attempts}
        attempt_ids = {envelope.attempt_envelope_id for _, envelope in attempts}
        if result_ids != {commit.prepared_result_id}:
            raise AssertionError("same-FWO attempts do not equal the committed result identity")
        if (
            args.expected_mode == "active_active"
            and len(executor_ids) != 2
            and not (args.allow_degraded_attempts and len(executor_ids) == 1)
        ):
            raise AssertionError("active-active transition lacks two distinct executors")
        if len(attempt_ids) != len(attempts):
            raise AssertionError("prepared marker set repeats an attempt identity")
        all_attempt_ids.update(attempt_ids)
        lineage.append(
            {
                "commit_seq": commit.commit_seq,
                "commit_id": commit.commit_id,
                "work_order_id": order.work_order_id,
                "prepared_result_id": commit.prepared_result_id,
                "owner_member_ids": list(order.owner_member_ids),
                "attempt_envelope_ids": sorted(attempt_ids),
                "executor_ids": sorted(executor_ids),
            }
        )

    committer_events = _jsonl(args.root / "logs" / "distributed_committer.jsonl")
    committed_events = [
        item
        for item in committer_events
        if item.get("event_type") == "distributed_transition_committed"
    ]
    if len(committed_events) != len(commits):
        raise AssertionError("committer telemetry and committed optimizer prefix differ")
    if any(item.get("redundancy_mode") != args.expected_mode for item in committed_events):
        raise AssertionError("committer telemetry mode differs from FWO mode")

    executor_events = []
    for path in sorted((args.root / "logs").glob("distributed_executor_*.jsonl")):
        executor_events.extend(
            item for item in _jsonl(path) if item.get("event_type") == "fragment_prepared"
        )
    observed_attempt_ids = {str(item["attempt_envelope_id"]) for item in executor_events}
    if observed_attempt_ids != all_attempt_ids:
        raise AssertionError("executor telemetry and authoritative marker attempts differ")

    metric_path = args.root / "metrics" / "learner_metrics.csv"
    metrics = list(csv.DictReader(metric_path.open(encoding="utf-8")))
    losses = [float(item["train_loss"]) for item in metrics if item.get("train_loss")]
    if not losses or not all(math.isfinite(value) for value in losses):
        raise AssertionError("learner losses are missing or non-finite")
    learners = {item.get("learner_id") for item in metrics if item.get("learner_id")}
    if len(learners) != args.expected_learners:
        raise AssertionError("learner metrics do not cover expected learner count")

    total_prepare_seconds = sum(float(item["prepare_seconds"]) for item in executor_events)
    total_input_bytes = sum(int(item["input_bytes"]) for item in executor_events)
    total_output_bytes = sum(int(item["output_bytes"]) for item in executor_events)
    report = {
        "status": "PASS",
        "run_id": args.run_id,
        "mode": args.expected_mode,
        "learners": len(learners),
        "dedicated_syncer_nodes": 0,
        "optimizer_transitions": len(commits),
        "prepared_attempts": len(all_attempt_ids),
        "duplicate_attempts": len(all_attempt_ids) - len(commits),
        "total_prepare_seconds": total_prepare_seconds,
        "duplicate_prepare_seconds_estimate": total_prepare_seconds / len(all_attempt_ids)
        * (len(all_attempt_ids) - len(commits)),
        "total_prepare_input_bytes": total_input_bytes,
        "total_prepare_output_bytes": total_output_bytes,
        "finite_loss_count": len(losses),
        "min_loss": min(losses),
        "max_loss": max(losses),
        "lineage": lineage,
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
