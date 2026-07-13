#!/usr/bin/env python3
"""Validate the frozen P08R runtime and complete-experiment wall-clock contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-started-ns", type=int, required=True)
    parser.add_argument("--runtime-started-ns", type=int, required=True)
    parser.add_argument("--runtime-ended-ns", type=int, required=True)
    parser.add_argument("--experiment-ended-ns", type=int, required=True)
    parser.add_argument("--max-experiment-seconds", type=float, default=440.0)
    parser.add_argument("--max-post-runtime-seconds", type=float, default=25.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    values = (
        args.experiment_started_ns,
        args.runtime_started_ns,
        args.runtime_ended_ns,
        args.experiment_ended_ns,
    )
    if any(type(value) is not int or value < 0 for value in values):
        raise ValueError("monotonic timestamps must be non-negative integers")
    if list(values) != sorted(values):
        raise ValueError("elapsed timestamps are not monotonic")
    setup = (values[1] - values[0]) / 1_000_000_000
    runtime = (values[2] - values[1]) / 1_000_000_000
    post = (values[3] - values[2]) / 1_000_000_000
    experiment = (values[3] - values[0]) / 1_000_000_000
    passed = (
        experiment <= args.max_experiment_seconds
        and post <= args.max_post_runtime_seconds
    )
    report = {
        "schema": "duraloco-p08r-elapsed-contract-v1",
        "status": "PASS" if passed else "FAIL",
        "experiment_started_monotonic_ns": values[0],
        "runtime_started_monotonic_ns": values[1],
        "runtime_ended_monotonic_ns": values[2],
        "experiment_ended_monotonic_ns": values[3],
        "setup_elapsed_seconds": setup,
        "runtime_elapsed_seconds": runtime,
        "post_runtime_elapsed_seconds": post,
        "experiment_elapsed_seconds": experiment,
        "max_experiment_seconds": args.max_experiment_seconds,
        "max_post_runtime_seconds": args.max_post_runtime_seconds,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
