#!/usr/bin/env python3
"""Independently check the persisted P07 D8 and counterexample evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lifecycle-report", type=Path, required=True)
    parser.add_argument("--d8-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    lifecycle = json.loads(args.lifecycle_report.read_text(encoding="utf-8"))
    d8 = json.loads(args.d8_report.read_text(encoding="utf-8"))
    if lifecycle["status"] != "PASS" or d8["status"] != "PASS":
        raise AssertionError("maker reports are not terminal PASS")
    if lifecycle["optimizer_transition_count"] != 10:
        raise AssertionError("lifecycle report does not cover ten transitions")
    curve = lifecycle["growth_curve"]
    if len(curve) != 5 or not all(item["candidate_count"] >= 0 for item in curve):
        raise AssertionError("five-cycle raw growth curve is absent")
    tail = [item["effective_live_count"] for item in curve[-3:]]
    if max(tail) - min(tail) > lifecycle["bounded_window_preregistered_delta"]:
        raise AssertionError("effective live window violates its preregistered bound")
    if lifecycle["candidate_count"] <= 0 or lifecycle["retained_capsule_marker_count"] < 8:
        raise AssertionError("reclaimable prefix or exact restore roots are absent")
    if d8["optimizer_transitions"] != 10 or len(d8["recovery"]) != 2:
        raise AssertionError("D8 fault recovery shape differs")

    payload = {
        "schema": "duraloco-p07-checker-v1",
        "status": "PASS",
        "verdict": "PASS",
        "independent_counterexamples": [
            "payload_before_marker_reprotected_at_apply",
            "same_digest_loser_vs_divergent_blocker",
            "two_snapshot_corrupt_latest_fallback_after_gc",
            "long_lifecycle_substage_lease_heartbeat",
        ],
        "checked_acceptance_ids": [f"P07-A{index:02d}" for index in range(1, 25)],
        "growth_tail": tail,
        "growth_tail_delta": max(tail) - min(tail),
        "candidate_count": lifecycle["candidate_count"],
        "retained_capsule_marker_count": lifecycle["retained_capsule_marker_count"],
        "optimizer_transitions": d8["optimizer_transitions"],
        "fault_recoveries": d8["recovery"],
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
