#!/usr/bin/env python3
"""Measure P08 asynchronous stage-recorder overhead around real streaming reduction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import time

import torch

from fs_diloco.optimizer.streaming_reduce import reduce_fragment_streaming
from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.syncer_core.types import FragmentPlan
from fs_diloco.telemetry import StageRecorder


def _plan(quorum: int) -> FragmentPlan:
    proposal_ids = tuple(f"proposal-{index:04d}" for index in range(quorum))
    weight = float(1.0 / quorum).hex()
    return FragmentPlan(
        fragment_id=0,
        parent_commit_id="telemetry-parent",
        parent_commit_seq=0,
        parent_frontier_digest="0" * 64,
        selected_proposal_ids=proposal_ids,
        payload_sha256=tuple(f"{index:064x}" for index in range(quorum)),
        weights_hex=tuple(weight for _ in range(quorum)),
        aggregate_digest=canonical_digest({"quorum": quorum}),
        selection_digest=canonical_digest({"proposal_ids": list(proposal_ids)}),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--numel", type=int, default=32_000_000)
    parser.add_argument("--quorum", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=40)
    parser.add_argument("--max-overhead-fraction", type=float, default=0.02)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.numel < 1 or args.quorum < 1 or args.repeats < 4:
        raise ValueError("positive numel/quorum and at least four repeats are required")
    torch.set_num_threads(min(8, torch.get_num_threads()))
    plan = _plan(args.quorum)
    current = torch.zeros(args.numel, dtype=torch.float32)
    proposals = {
        proposal_id: torch.full((args.numel,), float(index + 1), dtype=torch.float32)
        for index, proposal_id in enumerate(plan.selected_proposal_ids)
    }

    def reduce_once():
        result, _ = reduce_fragment_streaming(
            plan=plan,
            load_proposal=proposals.__getitem__,
            current_params=current,
            max_inflight_bytes=args.numel * 4,
        )
        return result

    reduce_once()
    baseline_started = time.monotonic_ns()
    baseline_result = None
    for _ in range(args.repeats):
        baseline_result = reduce_once()
    baseline_ns = time.monotonic_ns() - baseline_started

    with tempfile.TemporaryDirectory(prefix="p08-telemetry-") as raw:
        recorder = StageRecorder(
            Path(raw) / "events.jsonl",
            run_id="p08-telemetry-overhead",
            run_generation=0,
            role="executor",
            role_session_id="benchmark-session",
            health_path=Path(raw) / "health.json",
        )
        instrumented_started = time.monotonic_ns()
        instrumented_result = None
        for index in range(args.repeats):
            operation_started = time.monotonic_ns()
            instrumented_result = reduce_once()
            operation_finished = time.monotonic_ns()
            for stage in (
                "executor_input_read",
                "streaming_reduction",
                "outer_step",
                "prepared_publication",
            ):
                recorder.record(
                    stage,
                    start_ns=operation_started,
                    end_ns=operation_finished,
                    counters={"repeat": index},
                )
        health = recorder.close()
        instrumented_ns = time.monotonic_ns() - instrumented_started

    if baseline_result is None or instrumented_result is None:
        raise AssertionError("benchmark did not execute")
    if not health.complete:
        raise AssertionError("telemetry recorder dropped benchmark events")
    if not torch.equal(baseline_result, instrumented_result):
        raise AssertionError("telemetry changed the streaming reduction result")
    overhead = instrumented_ns / baseline_ns - 1.0
    report = {
        "schema": "duraloco-telemetry-overhead-v1",
        "status": "PASS" if overhead <= args.max_overhead_fraction else "FAIL",
        "numel": args.numel,
        "quorum": args.quorum,
        "repeats": args.repeats,
        "torch_threads": torch.get_num_threads(),
        "baseline_ns": baseline_ns,
        "instrumented_ns": instrumented_ns,
        "overhead_fraction": overhead,
        "maximum_overhead_fraction": args.max_overhead_fraction,
        "events": health.written_events,
        "recorder_health": health.to_dict(),
        "numeric_equal": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))
    if report["status"] != "PASS":
        raise AssertionError("telemetry overhead exceeded the D-0806 two-percent budget")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
