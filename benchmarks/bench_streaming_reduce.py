#!/usr/bin/env python3
"""Measure the P08 one-proposal streaming reducer and its hard working-set counters."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import resource
import time

import torch

from fs_diloco.optimizer.streaming_reduce import reduce_fragment_streaming
from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.syncer_core.types import FragmentPlan


def _plan(quorum: int) -> FragmentPlan:
    proposal_ids = tuple(f"proposal-{index:04d}" for index in range(quorum))
    return FragmentPlan(
        fragment_id=0,
        parent_commit_id="optimized-parent",
        parent_commit_seq=0,
        parent_frontier_digest="0" * 64,
        selected_proposal_ids=proposal_ids,
        payload_sha256=tuple(f"{index:064x}" for index in range(quorum)),
        weights_hex=tuple(float(1.0 / quorum).hex() for _ in proposal_ids),
        aggregate_digest=canonical_digest({"quorum": quorum}),
        selection_digest=canonical_digest({"proposal_ids": list(proposal_ids)}),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--numel", type=int, default=4_000_000)
    parser.add_argument("--quorum", type=int, action="append", default=[])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    quorums = args.quorum or [1, 2, 4, 8]
    if args.numel < 1 or args.repeats < 1 or any(value < 1 for value in quorums):
        raise ValueError("numel, repeats and quorum must be positive")
    torch.set_num_threads(min(8, torch.get_num_threads()))
    current = torch.zeros(args.numel, dtype=torch.float32)
    cases = []
    for quorum in quorums:
        plan = _plan(quorum)
        durations: list[int] = []
        final_stats = None
        result_digest = None
        for _ in range(args.repeats):
            def load(
                proposal_id: str,
                *,
                selected_ids=plan.selected_proposal_ids,
            ) -> torch.Tensor:
                index = selected_ids.index(proposal_id)
                return torch.full(
                    (args.numel,), float(index + 1), dtype=torch.float32
                )

            started = time.monotonic_ns()
            result, final_stats = reduce_fragment_streaming(
                plan=plan,
                load_proposal=load,
                current_params=current,
                max_inflight_bytes=args.numel * 4,
            )
            durations.append(time.monotonic_ns() - started)
            result_digest = canonical_digest(
                {
                    "numel": int(result.numel()),
                    "sum_hex": float(result.sum().item()).hex(),
                }
            )
        assert final_stats is not None
        cases.append(
            {
                "quorum": quorum,
                "fragment_numel": args.numel,
                "fragment_bytes_float32": args.numel * 4,
                "durations_ns": durations,
                "min_duration_ns": min(durations),
                "result_digest": result_digest,
                "working_set": final_stats.to_counters(),
                "max_rss_bytes": (
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
                ),
            }
        )
    working_sets = {item["working_set"]["peak_working_bytes"] for item in cases}
    if len(working_sets) != 1:
        raise RuntimeError("streaming reducer working set scales with quorum")
    report = {
        "schema": "duraloco-p08-lfe-streaming-optimized-v1",
        "implementation": "ordered-streaming-left-fold-float32",
        "torch_version": torch.__version__,
        "torch_threads": torch.get_num_threads(),
        "cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
