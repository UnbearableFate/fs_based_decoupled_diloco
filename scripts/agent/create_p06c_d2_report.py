#!/usr/bin/env python3
"""Combine strict P06C runtime evidence with the D2-R2 failure tape."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--base-report", type=Path, required=True)
    parser.add_argument("--training-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    base = json.loads(args.base_report.read_text(encoding="utf-8"))
    summary = json.loads(args.training_summary.read_text(encoding="utf-8"))
    faults = _jsonl(args.root / "distributed" / "faults" / "fault_sequence.jsonl")
    committer = _jsonl(args.root / "logs" / "distributed_committer.jsonl")
    transitions = sorted(
        (
            item
            for item in committer
            if item.get("event_type") == "distributed_transition_committed"
        ),
        key=lambda item: float(item["timestamp"]),
    )
    executor_faults = [item for item in faults if item["event"] == "executor_process_killed"]
    committer_faults = [item for item in faults if item["event"] == "committer_process_killed"]
    whole_faults = [item for item in faults if item["event"] == "whole_learner_member_killed"]
    if len(executor_faults) != 2 or len(
        {item["target_member_id"] for item in executor_faults}
    ) != 2:
        raise AssertionError("failure tape lacks distinct primary and backup executor kills")
    if len(committer_faults) != 1 or len(whole_faults) != 1:
        raise AssertionError("failure tape lacks committer or whole-member kill")
    if len(transitions) != 4 or base["optimizer_transitions"] != 4:
        raise AssertionError("D2-R2 did not commit four optimizer transitions")
    if summary["stop_reason"] != "stop_after_outer_steps":
        raise AssertionError("D2-R2 did not reach its authoritative terminal boundary")

    recovery = []
    for fault in faults:
        timestamp = float(fault["timestamp"])
        successors = [item for item in transitions if float(item["timestamp"]) > timestamp]
        if not successors:
            raise AssertionError(f"no committed recovery after {fault['event']}")
        recovery.append(
            {
                **fault,
                "recovery_commit_seq": successors[0]["commit_seq"],
                "recovery_seconds": float(successors[0]["timestamp"]) - timestamp,
            }
        )
    epochs = sorted(
        {
            int(item["fencing_epoch"])
            for item in committer
            if item.get("event_type") == "coordination_stage_completed"
            and item.get("stage") == "fence_commit_and_strict_replay"
        }
    )
    if len(epochs) < 3:
        raise AssertionError("committer and combined failover did not advance fencing epochs")

    report = {
        "status": "PASS",
        "optimizer_transitions": len(transitions),
        "prepared_attempts": base["prepared_attempts"],
        "duplicate_attempts": base["duplicate_attempts"],
        "fencing_epochs": epochs,
        "executor_kill_targets": sorted(
            item["target_member_id"] for item in executor_faults
        ),
        "committer_kill_target": committer_faults[0]["target_member_id"],
        "whole_member_kill_target": whole_faults[0]["target_member_id"],
        "combined_committer_and_learner_host_loss": True,
        "factor_two_degraded_liveness_boundary": (
            "membership remains factor two; one surviving owner may finish only after explicit "
            "derived failure evidence, while removal to one member is prohibited"
        ),
        "recovery": recovery,
        "max_recovery_seconds": max(item["recovery_seconds"] for item in recovery),
        "base_runtime_report": base,
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
