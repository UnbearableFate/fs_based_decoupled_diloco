#!/usr/bin/env python3
"""Validate one P07 distributed lifecycle run from raw authority objects."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fs_diloco.learner_protocol.capsule import load_capsule
from fs_diloco.log.production import ProductionTransactionalLog
from fs_diloco.log.reachability import build_reachability
from fs_diloco.protocol.schemas import ControlCommitManifest
from fs_diloco.storage import PosixStorageBackend


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-generation", required=True, type=int)
    parser.add_argument("--expected-learners", required=True, type=int)
    parser.add_argument("--require-bounded-window", action="store_true")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    backend = PosixStorageBackend(root / "authority")
    log = ProductionTransactionalLog.open(
        backend, args.run_id, args.run_generation
    )
    strict = log.replay(force_full=True)
    accelerated = log.replay_from_snapshot()
    if accelerated.mode != "snapshot_suffix" or accelerated.replay != strict:
        raise RuntimeError("snapshot+suffix replay did not equal strict replay")
    pins = [
        commit
        for commit in strict.commits
        if isinstance(commit, ControlCommitManifest)
        and commit.control_kind == "snapshot_pin"
    ]
    if not pins:
        raise RuntimeError("run has no committed snapshot pin")
    marker_prefix = f"{log.layout.capsule_prefix}markers/"
    marker_keys = backend.list_prefix(marker_prefix)
    capsule_by_key = {key: load_capsule(backend, key) for key in marker_keys}
    capsules = list(capsule_by_key.values())
    learner_ids = {capsule.learner_id for capsule in capsules}
    if len(learner_ids) < args.expected_learners:
        raise RuntimeError("not every learner published an exact capsule")
    ancestry = strict.frontier_by_commit
    if any(capsule.frontier_commit_id not in ancestry for capsule in capsules):
        raise RuntimeError("capsule frontier is not in committed ancestry")
    report = build_reachability(log, replay=strict)
    retained_marker_keys = sorted(set(marker_keys) & set(report.reachable))
    candidate_marker_keys = sorted(set(marker_keys) & set(report.candidates))
    if set(marker_keys) != set(retained_marker_keys) | set(candidate_marker_keys):
        raise RuntimeError("capsule marker is neither retained nor safely reclaimable")
    retained_capsules = [capsule_by_key[key] for key in retained_marker_keys]
    if len({capsule.learner_id for capsule in retained_capsules}) < args.expected_learners:
        raise RuntimeError("not every learner has a retained exact restore capsule")
    delete_results = backend.list_prefix(log.layout.delete_result_prefix)
    if delete_results:
        raise RuntimeError("real run unexpectedly contains destructive GC results")
    cycle_paths = sorted((root / "distributed" / "lifecycle").glob("cycle-*.json"))
    cycles = [json.loads(path.read_text(encoding="utf-8")) for path in cycle_paths]
    if not cycles or any(not item.get("dry_run") for item in cycles):
        raise RuntimeError("lifecycle cycle evidence is missing or not dry-run")
    growth_curve = [
        {
            "head_commit_seq": item["head_commit_seq"],
            "inventory_count": item["inventory_count"],
            "inventory_bytes": item["inventory_bytes"],
            "inventory_header_bytes_read": item.get(
                "inventory_header_bytes_read"
            ),
            "inventory_payload_bytes_read": item.get(
                "inventory_payload_bytes_read"
            ),
            "lifecycle_header_bytes_read": item.get(
                "lifecycle_header_bytes_read"
            ),
            "lifecycle_payload_bytes_read": item.get(
                "lifecycle_payload_bytes_read"
            ),
            "candidate_count": item["candidate_count"],
            "effective_live_count": item["inventory_count"]
            - item["candidate_count"],
            "lifecycle_seconds": item["lifecycle_seconds"],
            "snapshot_storage_get_count": item["snapshot_storage_get_count"],
        }
        for item in cycles
    ]
    if args.require_bounded_window:
        if len(cycles) < 4 or not any(item["candidate_count"] > 0 for item in cycles[2:]):
            raise RuntimeError("accelerated soak never exposed a reclaimable compacted prefix")
        tail = [item["effective_live_count"] for item in growth_curve[-3:]]
        # The exact count varies with fault evidence.  This preregistered bound
        # permits one cadence window (64 metadata objects) of churn.
        if max(tail) - min(tail) > 64:
            raise RuntimeError("effective live-object window exceeded preregistered bound")
    payload = {
        "status": "PASS",
        "run_id": args.run_id,
        "run_generation": args.run_generation,
        "head_commit_id": strict.head_frontier.commit_id,
        "head_commit_seq": strict.head_frontier.commit_seq,
        "optimizer_transition_count": (
            strict.head_frontier.coordination.optimizer_transition_count
            if strict.head_frontier.coordination is not None
            else None
        ),
        "strict_state_digest": strict.committed_state_digest,
        "snapshot_state_digest": accelerated.replay.committed_state_digest,
        "snapshot_id": accelerated.snapshot_id,
        "snapshot_pin_count": len(pins),
        "snapshot_suffix_length": accelerated.suffix_length,
        "snapshot_storage_get_count": accelerated.storage_get_count,
        "capsule_count": len(capsules),
        "capsule_learner_ids": sorted(learner_ids),
        "capsule_ids": sorted(capsule.capsule_id for capsule in capsules),
        "retained_capsule_marker_count": len(retained_marker_keys),
        "candidate_capsule_marker_count": len(candidate_marker_keys),
        "reachability_root_count": len(report.roots),
        "reachable_count": len(report.reachable),
        "candidate_count": len(report.candidates),
        "protected_unknown_count": len(report.protected_unknown),
        "gc_apply_count": 0,
        "lifecycle_cycles": cycles,
        "growth_curve": growth_curve,
        "bounded_window_preregistered_delta": 64,
        "checks": {
            "snapshot_suffix_equals_strict": True,
            "snapshot_is_ancestry_pinned": True,
            "capsules_marker_last_and_complete": True,
            "capsule_frontiers_in_ancestry": True,
            "latest_capsules_are_reachability_roots": True,
            "older_capsules_are_explainable_candidates": True,
            "real_namespace_gc_is_dry_run": True,
            "bounded_effective_live_window": args.require_bounded_window,
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
