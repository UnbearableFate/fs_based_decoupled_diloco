#!/usr/bin/env python3
"""Measure deferred periodic lifecycle reads plus one terminal strict audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

from fs_diloco.log import ProductionTransactionalLog
from fs_diloco.log.reachability import build_reachability
from fs_diloco.storage import PosixStorageBackend


def _elapsed(operation):
    started = time.monotonic_ns()
    value = operation()
    return value, time.monotonic_ns() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-generation", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    backend = PosixStorageBackend(args.training_root / "authority")
    log = ProductionTransactionalLog.open(backend, args.run_id, args.run_generation)
    head_before = hashlib.sha256(backend.get(log.layout.head_key)).hexdigest()
    reads_before = backend.read_counters

    accelerated, accelerated_ns = _elapsed(log.replay_from_snapshot)
    if accelerated.mode != "snapshot_suffix":
        raise RuntimeError("frozen R2 authority lacks a valid terminal snapshot")
    reachability, reachability_ns = _elapsed(
        lambda: build_reachability(log, replay=accelerated.replay)
    )
    inventory_bytes, inventory_ns = _elapsed(
        lambda: sum(backend.head(key).size for key in reachability.inventory)
    )
    periodic_ns = accelerated_ns + reachability_ns + inventory_ns
    periodic_reads = backend.read_counters

    strict, strict_ns = _elapsed(lambda: log.replay(force_full=True))
    reads_after = backend.read_counters
    head_after = hashlib.sha256(backend.get(log.layout.head_key)).hexdigest()
    if accelerated.replay != strict:
        raise RuntimeError("terminal snapshot replay differs from strict replay")
    if head_before != head_after:
        raise RuntimeError("read-only lifecycle benchmark changed authority head")
    if periodic_ns > 10_000_000_000:
        raise RuntimeError("deferred periodic lifecycle read path exceeds ten seconds")

    cycle_paths = sorted(
        (args.training_root / "distributed" / "lifecycle").glob("cycle-*.json")
    )
    cycles = [json.loads(path.read_text(encoding="utf-8")) for path in cycle_paths]
    if len(cycles) != 5:
        raise RuntimeError("frozen R2 authority does not contain five lifecycle cycles")
    historical_cycle_seconds = sum(float(item["lifecycle_seconds"]) for item in cycles)
    historical_payload_bytes = sum(
        int(item["lifecycle_payload_bytes_read"]) for item in cycles
    )
    if historical_cycle_seconds < 200 or historical_payload_bytes < 100_000_000_000:
        raise RuntimeError("frozen R2 failure no longer demonstrates the strict replay cost")

    report = {
        "schema": "duraloco-p08r-deferred-lifecycle-benchmark-v1",
        "status": "PASS",
        "training_root": str(args.training_root),
        "run_id": args.run_id,
        "head_sha256_before": head_before,
        "head_sha256_after": head_after,
        "committed_state_digest": strict.committed_state_digest,
        "optimizer_transition_count": sum(
            commit.__class__.__name__ == "CommitManifest"
            for commit in strict.commits
        ),
        "snapshot_id": accelerated.snapshot_id,
        "snapshot_suffix_length": accelerated.suffix_length,
        "accelerated_seconds": accelerated_ns / 1_000_000_000,
        "reachability_seconds": reachability_ns / 1_000_000_000,
        "inventory_seconds": inventory_ns / 1_000_000_000,
        "deferred_periodic_seconds": periodic_ns / 1_000_000_000,
        "terminal_strict_seconds": strict_ns / 1_000_000_000,
        "inventory_count": len(reachability.inventory),
        "inventory_bytes": inventory_bytes,
        "periodic_header_bytes": (
            periodic_reads["header_bytes"] - reads_before["header_bytes"]
        ),
        "periodic_payload_bytes": (
            periodic_reads["payload_bytes"] - reads_before["payload_bytes"]
        ),
        "terminal_strict_header_bytes": (
            reads_after["header_bytes"] - periodic_reads["header_bytes"]
        ),
        "terminal_strict_payload_bytes": (
            reads_after["payload_bytes"] - periodic_reads["payload_bytes"]
        ),
        "historical_cycle_seconds": historical_cycle_seconds,
        "historical_cycle_payload_bytes": historical_payload_bytes,
        "historical_periodic_strict_replays": len(cycles),
        "deferred_periodic_strict_replays": 0,
        "terminal_strict_replays": 1,
    }
    if report["optimizer_transition_count"] != 10:
        raise RuntimeError("benchmark input is not the frozen ten-transition R2 run")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
