#!/usr/bin/env python3
"""Profile the pre-optimization materialized LFE reduction on a compute node."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import resource
import time

import torch

from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.syncer_core.aggregation import reduce_fragment
from fs_diloco.syncer_core.types import FragmentPlan


def _plan(quorum: int) -> FragmentPlan:
    proposal_ids = tuple(f"proposal-{index:04d}" for index in range(quorum))
    weight = float(1.0 / quorum).hex()
    return FragmentPlan(
        fragment_id=0,
        parent_commit_id="baseline-parent",
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
    parser.add_argument("--numel", type=int, default=4_000_000)
    parser.add_argument("--quorum", type=int, action="append", default=[])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    quorums = args.quorum or [1, 2, 4, 8]
    if args.numel < 1 or args.repeats < 1 or any(value < 1 for value in quorums):
        raise ValueError("numel, repeats and quorum must be positive")
    torch.set_num_threads(min(8, torch.get_num_threads()))
    cases = []
    for quorum in quorums:
        current = torch.zeros(args.numel, dtype=torch.float32)
        plan = _plan(quorum)
        proposals = {
            proposal_id: torch.full(
                (args.numel,), float(index + 1), dtype=torch.float32
            )
            for index, proposal_id in enumerate(plan.selected_proposal_ids)
        }
        durations = []
        digest = None
        for _ in range(args.repeats):
            started = time.monotonic_ns()
            result = reduce_fragment(
                plan=plan,
                proposal_tensors=proposals,
                current_params=current,
            )
            durations.append(time.monotonic_ns() - started)
            digest = canonical_digest(
                {
                    "numel": int(result.numel()),
                    "sum_hex": float(result.sum().item()).hex(),
                }
            )
        cases.append(
            {
                "quorum": quorum,
                "fragment_numel": args.numel,
                "fragment_bytes_float32": args.numel * 4,
                "materialized_proposal_bytes": quorum * args.numel * 4,
                "durations_ns": durations,
                "min_duration_ns": min(durations),
                "result_digest": digest,
                "max_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            }
        )
    report = {
        "schema": "duraloco-p08-lfe-materialized-baseline-v1",
        "implementation": "materialized-proposal-map-left-fold",
        "torch_version": torch.__version__,
        "torch_threads": torch.get_num_threads(),
        "cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
