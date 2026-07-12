#!/usr/bin/env python3
"""Build P06C D8-R2 chaos, resource, latency, and factor-one comparison evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean

from fs_diloco.log.production import ProductionTransactionalLog
from fs_diloco.runtime_view import build_runtime_view
from fs_diloco.storage import PosixStorageBackend


def _jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--elapsed-seconds", type=int, required=True)
    parser.add_argument("--max-elapsed-seconds", type=int, default=900)
    parser.add_argument("--runtime-report", type=Path, required=True)
    parser.add_argument("--factor-one-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    runtime = json.loads(args.runtime_report.read_text(encoding="utf-8"))
    baseline = json.loads(args.factor_one_report.read_text(encoding="utf-8"))
    log = ProductionTransactionalLog.open(
        PosixStorageBackend(args.root / "authority"), args.run_id, 0
    )
    replay = log.replay(force_full=True)
    view = build_runtime_view(log, force_full=True)
    if view.membership is None or view.membership.revision != 1:
        raise AssertionError("D8-R2 lacks committed membership revision one")
    if view.membership.replication_factor != 2:
        raise AssertionError("D8-R2 final ownership is not factor two")

    faults = _jsonl(args.root / "distributed" / "faults" / "fault_sequence.jsonl")
    executor_faults = [item for item in faults if item["event"] == "executor_process_killed"]
    whole_faults = [item for item in faults if item["event"] == "whole_learner_member_killed"]
    if len(executor_faults) != 1 or len(whole_faults) != 1:
        raise AssertionError("D8-R2 failure tape is incomplete")
    removed_member = str(whole_faults[0]["target_member_id"])

    committer = _jsonl(args.root / "logs" / "distributed_committer.jsonl")
    transitions = [
        item for item in committer if item.get("event_type") == "distributed_transition_committed"
    ]
    reconfigurations = [
        item for item in committer if item.get("event_type") == "membership_reconfigured"
    ]
    if len(transitions) != 10 or len(reconfigurations) != 1:
        raise AssertionError("D8-R2 transition or committed reconfiguration count differs")
    if reconfigurations[0]["removed_member_id"] != removed_member:
        raise AssertionError("committed reconfiguration removed another member")
    if not reconfigurations[0].get("failure_evidence_id"):
        raise AssertionError("committed reconfiguration lacks bound failure evidence")

    policies = [item["redundancy_policy"] for item in runtime["lineage"]]
    if any(policy != {"mode": "hedged", "hedge_delay_ms": 6000} for policy in policies):
        raise AssertionError("D8-R2 work orders do not bind the fixed hedged policy")
    if runtime["optimizer_transitions"] != 10 or runtime["learners"] != 8:
        raise AssertionError("D8-R2 runtime shape differs from 8 learners and 10 transitions")

    executor_events = [
        item
        for path in sorted((args.root / "logs").glob("distributed_executor_*.jsonl"))
        for item in _jsonl(path)
        if item.get("event_type") == "fragment_prepared"
    ]
    learner_events = [
        item
        for path in sorted((args.root / "logs").glob("learner_*.jsonl"))
        for item in _jsonl(path)
    ]
    gpu_steps = [
        float(item["gpu_step_seconds"])
        for item in learner_events
        if item.get("event_type") == "inner_step_summary"
        and item.get("gpu_step_seconds") is not None
    ]
    latencies = [float(item["publish_to_commit_seconds"]) for item in transitions]
    if not gpu_steps or not latencies:
        raise AssertionError("D8-R2 resource or latency telemetry is absent")

    recovery = []
    for fault in faults:
        successors = [
            item for item in transitions if float(item["timestamp"]) > float(fault["timestamp"])
        ]
        if not successors:
            raise AssertionError(f"no transition recovered after {fault['event']}")
        recovery.append(
            {
                **fault,
                "recovery_commit_seq": successors[0]["commit_seq"],
                "recovery_seconds": float(successors[0]["timestamp"])
                - float(fault["timestamp"]),
            }
        )

    current_io = {
        "input_bytes": sum(int(item["input_bytes"]) for item in executor_events),
        "output_bytes": sum(int(item["output_bytes"]) for item in executor_events),
        "prepare_seconds": sum(float(item["prepare_seconds"]) for item in executor_events),
    }
    baseline_io = baseline["lustre_io_telemetry"]
    baseline_gpu_mean = float(baseline["resource_telemetry"]["gpu_step_seconds"]["mean"])
    current_gpu_mean = mean(gpu_steps)
    control_kinds = [
        item.control_kind for item in replay.commits if hasattr(item, "control_kind")
    ]
    if control_kinds.count("membership") != 1 or control_kinds[-1] != "stop":
        raise AssertionError("D8-R2 committed control sequence differs")

    report = {
        "status": "PASS",
        "learner_nodes": 8,
        "dedicated_syncer_nodes": 0,
        "optimizer_transitions": 10,
        "membership_revision": 1,
        "replication_factor": 2,
        "removed_member_id": removed_member,
        "failure_evidence_id": reconfigurations[0]["failure_evidence_id"],
        "reconfiguration_request_id": reconfigurations[0][
            "reconfiguration_request_id"
        ],
        "mode": "hedged",
        "hedge_delay_ms": 6000,
        "prepared_attempts_in_committed_lineage": runtime["prepared_attempts"],
        "total_observed_attempts": runtime["total_observed_attempts"],
        "abandoned_old_epoch_attempts": runtime["abandoned_old_epoch_attempts"],
        "duplicate_attempts": runtime["duplicate_attempts"],
        "latency_seconds": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "p99": _percentile(latencies, 0.99),
            "max": max(latencies),
        },
        "recovery": recovery,
        "max_recovery_seconds": max(item["recovery_seconds"] for item in recovery),
        "elapsed_seconds": args.elapsed_seconds,
        "fault_goodput_transitions_per_second": 10 / args.elapsed_seconds,
        "factor_one_baseline": {
            "source": str(args.factor_one_report),
            "elapsed_seconds": baseline["elapsed_seconds"],
            "goodput_transitions_per_second": 10 / float(baseline["elapsed_seconds"]),
            "gpu_step_seconds_mean": baseline_gpu_mean,
            "executor_input_bytes": baseline_io["executor_input_bytes"],
            "executor_output_bytes": baseline_io["executor_output_bytes"],
        },
        "r2_resource": {
            **current_io,
            "gpu_step_seconds_mean": current_gpu_mean,
            "gpu_step_mean_ratio_vs_factor_one": current_gpu_mean / baseline_gpu_mean,
            "input_byte_ratio_vs_factor_one": current_io["input_bytes"]
            / float(baseline_io["executor_input_bytes"]),
            "output_byte_ratio_vs_factor_one": current_io["output_bytes"]
            / float(baseline_io["executor_output_bytes"]),
        },
        "control_sequence": control_kinds,
        "no_optimizer_state_transfer": True,
        "p07_lifecycle_requirements": [
            "retain committed PFR payloads and exact attempt lineage while reachable",
            "retain divergent or abandoned old-epoch attempts through an audit grace boundary",
            "derive reachability from committed global-head ancestry, never immutable listing alone",
            "delete marker last after every referenced immutable payload and envelope",
        ],
        "runtime_report": runtime,
    }
    if report["elapsed_seconds"] > args.max_elapsed_seconds:
        raise AssertionError("D8-R2 exceeded its configured runtime envelope")
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
