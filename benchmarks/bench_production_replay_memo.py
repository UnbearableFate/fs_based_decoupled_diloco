#!/usr/bin/env python3
"""Compare empty-cache and same-process replay on a real production prefix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from fs_diloco.log import ProductionTransactionalLog
from fs_diloco.storage import PosixStorageBackend


def _measure(log: ProductionTransactionalLog, *, force_full: bool) -> dict[str, object]:
    backend = log.backend
    reads_before = backend.read_counters
    gets_before = sum(record.operation == "get" for record in backend.history)
    started = time.monotonic_ns()
    if force_full:
        replay = log.replay(force_full=True)
        mode = "empty_cache_strict"
        telemetry = None
    else:
        replay_result = log.replay_from_snapshot()
        replay = replay_result.replay
        mode = replay_result.mode
        telemetry = (
            replay_result.telemetry.to_dict()
            if replay_result.telemetry is not None
            else None
        )
    elapsed_ns = time.monotonic_ns() - started
    reads_after = backend.read_counters
    gets_after = sum(record.operation == "get" for record in backend.history)
    return {
        "mode": mode,
        "elapsed_ns": elapsed_ns,
        "storage_get_count": gets_after - gets_before,
        "storage_header_bytes": reads_after["header_bytes"] - reads_before["header_bytes"],
        "storage_payload_bytes": reads_after["payload_bytes"] - reads_before["payload_bytes"],
        "head_commit_seq": replay.head_frontier.commit_seq,
        "optimizer_transition_count": sum(
            getattr(commit, "optimizer_transition_count", None) is not None
            and commit.__class__.__name__ == "CommitManifest"
            for commit in replay.commits
        ),
        "committed_state_digest": replay.committed_state_digest,
        "cache_entries_after": log._replay_cache.entry_count,
        "replay_telemetry": telemetry,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-generation", type=int, default=0)
    parser.add_argument("--strict-repeats", type=int, default=2)
    parser.add_argument("--warm-repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.strict_repeats < 1 or args.warm_repeats < 2:
        raise ValueError("strict-repeats must be positive and warm-repeats at least two")

    backend = PosixStorageBackend(args.authority_root)
    log = ProductionTransactionalLog.open(
        backend, args.run_id, args.run_generation
    )
    strict_calls = [
        _measure(log, force_full=True) for _ in range(args.strict_repeats)
    ]
    warm_calls = [
        _measure(log, force_full=False) for _ in range(args.warm_repeats)
    ]
    digests = {
        str(call["committed_state_digest"]) for call in strict_calls + warm_calls
    }
    if len(digests) != 1:
        raise RuntimeError("strict and memoized replay digests differ")
    if any(call["optimizer_transition_count"] != 10 for call in strict_calls + warm_calls):
        raise RuntimeError("benchmark input is not the frozen ten-transition prefix")
    prior_payloads = [int(call["storage_payload_bytes"]) for call in warm_calls[1:]]
    if any(value != 0 for value in prior_payloads):
        raise RuntimeError("same-owner warm replay reread verified tensor payload bytes")

    strict_total = sum(int(call["elapsed_ns"]) for call in strict_calls)
    warm_total = sum(int(call["elapsed_ns"]) for call in warm_calls[1:])
    report = {
        "schema": "duraloco-p08r-real-prefix-replay-v1",
        "authority_root": str(args.authority_root),
        "run_id": args.run_id,
        "run_generation": args.run_generation,
        "strict_calls": strict_calls,
        "warm_calls": warm_calls,
        "strict_mean_elapsed_seconds": strict_total / len(strict_calls) / 1_000_000_000,
        "steady_warm_mean_elapsed_seconds": (
            warm_total / (len(warm_calls) - 1) / 1_000_000_000
        ),
        "strict_total_payload_bytes": sum(
            int(call["storage_payload_bytes"]) for call in strict_calls
        ),
        "steady_warm_total_payload_bytes": sum(prior_payloads),
        "committed_state_digest": digests.pop(),
        "status": "PASS",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
