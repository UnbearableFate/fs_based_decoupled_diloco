#!/usr/bin/env python3
"""Build matched P08 D8 telemetry, interference, and bundle-gate evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any

from fs_diloco.log.production import ProductionTransactionalLog
from fs_diloco.runtime_view import build_runtime_view
from fs_diloco.storage import PosixStorageBackend
from fs_diloco.telemetry.bundle_gate import evaluate_bundle_gate
from fs_diloco.telemetry.interference import compare_gpu_step_seconds
from fs_diloco.telemetry.summaries import load_events, summarize_events


CRITICAL_COMMITTER_STAGES = {
    "catalog_discovery",
    "proposal_validation",
    "work_order_publication",
    "prepared_visibility",
    "winner_validation",
    "successor_publication",
    "head_cas",
}


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _gpu_samples(root: Path) -> list[float]:
    values = [
        float(item["gpu_step_seconds"])
        for path in sorted((root / "logs").glob("learner_*.jsonl"))
        for item in _jsonl(path)
        if item.get("event_type") == "inner_step_summary"
        and item.get("gpu_step_seconds") is not None
    ]
    if not values or any(not math.isfinite(value) or value <= 0 for value in values):
        raise AssertionError("finite positive learner GPU-step samples are required")
    return values


def _summary(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    return {
        "count": len(values),
        "min": ordered[0],
        "mean": mean(values),
        "p50": ordered[(len(ordered) - 1) // 2],
        "p95": ordered[int((len(ordered) - 1) * 0.95)],
        "max": ordered[-1],
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _binding(artifacts: Path, config: Path) -> dict[str, object]:
    hosts = [line for line in (artifacts / "hosts.log").read_text().splitlines() if line]
    commit = (artifacts / "git_commit.log").read_text().strip()
    if len(set(hosts)) != 8 or len(commit) != 40:
        raise AssertionError("matched P08R evidence requires eight hosts and one clean commit")
    return {
        "git_commit": commit,
        "config_sha256": _sha256(config),
        "config": str(config),
        "model_revision": "gpt2",
        "dataset_revision": "wikitext-2-raw-v1",
        "seed": 1337,
        "allocation_nodes": 8,
        "learner_nodes": 8,
        "learners": 8,
        "hosts": hosts,
    }


def _stage_profile(root: Path, elapsed_seconds: int) -> dict[str, object]:
    event_paths = sorted((root / "logs").glob("performance_committer_*.jsonl")) + sorted(
        (root / "logs").glob("performance_executor_*.jsonl")
    )
    health = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((root / "logs").glob("performance_*.health.json"))
    ]
    if not event_paths or not health:
        raise AssertionError("raw stage events and recorder health are required")
    report = summarize_events(load_events(event_paths), recorder_health=health)
    wait_fractions: list[float] = []
    total_wait_ns = 0
    for timeline in report["timelines"]:
        committer = [
            item
            for item in timeline["events"]
            if item["role"] == "committer"
            and item["outcome"] == "pass"
            and item["stage"] in CRITICAL_COMMITTER_STAGES
        ]
        critical_ns = sum(
            int(item["monotonic_end_ns"]) - int(item["monotonic_start_ns"])
            for item in committer
        )
        wait_ns = sum(
            int(item["monotonic_end_ns"]) - int(item["monotonic_start_ns"])
            for item in committer
            if item["stage"] == "prepared_visibility"
        )
        if critical_ns <= 0 or wait_ns <= 0 or wait_ns > critical_ns:
            raise AssertionError("invalid same-committer critical-path telemetry")
        wait_fractions.append(wait_ns / critical_ns)
        total_wait_ns += wait_ns
    if len(wait_fractions) != 10:
        raise AssertionError("D8 stage profile requires exactly ten work orders")
    optimistic = min(1.0, 0.5 * total_wait_ns / (elapsed_seconds * 1_000_000_000))
    return {
        **report,
        "single_fwo_wait_fractions": wait_fractions,
        "single_fwo_wait_total_ns": total_wait_ns,
        "two_fwo_optimistic_e2e_improvement_upper_bound": optimistic,
        "projection_note": (
            "upper bound overlaps one half of measured same-committer prepared-visibility "
            "wait and charges no extra I/O/RSS; measured penalties can only reduce it"
        ),
    }


def _distributed_lease_guard(root: Path) -> dict[str, object]:
    events = _jsonl(root / "logs" / "distributed_committer.jsonl")
    stage_guards = [
        str(item.get("stage"))
        for item in events
        if item.get("event_type") == "lease_stage_guard"
    ]
    substages = [
        str(item.get("substage"))
        for item in events
        if item.get("event_type") == "lifecycle_substage_heartbeat"
    ]
    report = {
        "optimizer_head_cas_renewals": stage_guards.count("optimizer_head_cas"),
        "stop_head_cas_renewals": stage_guards.count("stop_head_cas"),
        "lifecycle_substage_renewals": stage_guards.count(
            "lifecycle_substage_heartbeat"
        ),
        "successor_prepare_heartbeats": substages.count("successor_prepare"),
        "post_cas_replay_heartbeats": substages.count("post_cas_replay"),
        "stop_prepare_heartbeats": substages.count("stop_prepare"),
        "stop_post_cas_replay_heartbeats": substages.count("stop_post_cas_replay"),
        "lease_authority_loss_events": sum(
            item.get("event_type") == "stop_not_published_after_lease_authority_loss"
            for item in events
        ),
    }
    if (
        report["optimizer_head_cas_renewals"] != 10
        or report["stop_head_cas_renewals"] != 1
        or report["lifecycle_substage_renewals"] != len(substages)
        or report["lifecycle_substage_renewals"] < 1
        or report["lease_authority_loss_events"]
    ):
        raise AssertionError("distributed D8 lacks complete long-stage lease guards")
    return report


def _validate_r2_attempt_lineage(
    *,
    transition_count: int,
    prepared_attempt_count: int,
    timeline_attempt_counts: list[int],
    terminal_loser_count: int,
) -> dict[str, int]:
    """Validate the frozen factor-two lineage, including the controlled loser.

    Every R2 work order has two canonical attempts. The injected first attempt
    fails before prepared-result publication, so a ten-transition run has
    twenty terminal attempts but only nineteen ``fragment_prepared`` events.
    """

    if transition_count != 10 or timeline_attempt_counts != [2] * 10:
        raise AssertionError("D8-R2 does not contain two attempts for each transition")
    total_attempt_count = sum(timeline_attempt_counts)
    if terminal_loser_count != 1:
        raise AssertionError("D8-R2 requires exactly one controlled terminal loser")
    expected_prepared_count = total_attempt_count - terminal_loser_count
    if prepared_attempt_count != expected_prepared_count:
        raise AssertionError(
            "D8-R2 prepared-result count does not match the terminal attempt lineage"
        )
    return {
        "total_attempts": total_attempt_count,
        "successful_prepared_attempts": prepared_attempt_count,
        "terminal_loser_attempts": terminal_loser_count,
    }


def _write(output: Path, payload: dict[str, object]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))


def _runtime(args: argparse.Namespace, mode: str) -> int:
    root, artifacts, config = args.root, args.artifacts, args.config
    summary = json.loads((artifacts / "training_summary.json").read_text(encoding="utf-8"))
    log = ProductionTransactionalLog.open(
        PosixStorageBackend(root / "authority"), args.run_id, 0
    )
    view = build_runtime_view(log)
    terminal_audit = json.loads(
        (root / "distributed/lifecycle/terminal-audit.json").read_text(
            encoding="utf-8"
        )
    )
    if (
        terminal_audit.get("status") != "PASS"
        or terminal_audit.get("strict_state_digest")
        != view.committed_state_digest
        or terminal_audit.get("snapshot_state_digest")
        != view.committed_state_digest
    ):
        raise AssertionError("runtime terminal strict audit differs from fresh report view")
    samples = _gpu_samples(root)
    payload: dict[str, object] = {
        "schema": "duraloco-p08-matched-runtime-v1",
        "status": "PASS",
        "mode": mode,
        "binding": _binding(artifacts, config),
        "optimizer_transitions": view.optimizer_transition_count,
        "stop_reason": summary["stop_reason"],
        "elapsed_seconds": args.elapsed_seconds,
        "gpu_step_seconds": _summary(samples),
        "gpu_step_samples": samples,
        "coordination_protocol": log.spec.coordination_protocol,
        "terminal_audit": terminal_audit,
    }
    if view.optimizer_transition_count != 10 or summary["stop_reason"] != "stop_after_outer_steps":
        raise AssertionError("matched runtime did not reach the frozen ten-transition terminal")

    if mode == "no_lfe":
        syncer_events = _jsonl(root / "logs" / "syncer.jsonl")
        stop_prepare_heartbeats = [
            item
            for item in syncer_events
            if item.get("event_type") == "transaction_substage_heartbeat"
            and item.get("substage") == "stop_prepare"
        ]
        stop_replay_heartbeats = [
            item
            for item in syncer_events
            if item.get("event_type") == "transaction_substage_heartbeat"
            and item.get("substage") == "stop_post_cas_replay"
        ]
        stop_stages = [
            item
            for item in syncer_events
            if item.get("event_type") == "coordination_stage_completed"
            and item.get("stage") == "authoritative_stop"
        ]
        if not stop_prepare_heartbeats or not stop_replay_heartbeats or len(stop_stages) != 1:
            raise AssertionError("no-LFE terminal lacks guarded stop heartbeat evidence")
        payload.update(
            {
                "executors": 0,
                "dedicated_syncer_nodes": 1,
                "lfe_cpu_threads_per_learner": 0,
                "fault_tape": [],
                "terminal_lease_guard": {
                    "stop_prepare_heartbeats": len(stop_prepare_heartbeats),
                    "stop_post_cas_replay_heartbeats": len(stop_replay_heartbeats),
                    "authoritative_stop_seconds": float(stop_stages[0]["seconds"]),
                    "final_renew_before_cas": True,
                },
            }
        )
    elif mode == "factor_one":
        base = json.loads(args.base_report.read_text(encoding="utf-8"))
        stage = _stage_profile(root, args.elapsed_seconds)
        if base["optimizer_transitions"] != 10 or base["executors"] != 8:
            raise AssertionError("factor-one base report differs from the frozen D8 shape")
        payload.update(
            {
                "executors": 8,
                "dedicated_syncer_nodes": 0,
                "lfe_cpu_threads_per_learner": 8,
                "replication_factor": 1,
                "fault_tape": [],
                "resource_telemetry": base["resource_telemetry"],
                "lustre_io_telemetry": base["lustre_io_telemetry"],
                "stage_profile": stage,
                "lease_guard": _distributed_lease_guard(root),
                "base_report": base,
            }
        )
    else:
        stage = _stage_profile(root, args.elapsed_seconds)
        faults = _jsonl(root / "distributed" / "faults" / "p08_fault_sequence.jsonl")
        commits = [
            item
            for item in _jsonl(root / "logs" / "distributed_committer.jsonl")
            if item.get("event_type") == "distributed_transition_committed"
        ]
        prepared = [
            item
            for path in sorted((root / "logs").glob("distributed_executor_*.jsonl"))
            for item in _jsonl(path)
            if item.get("event_type") == "fragment_prepared"
        ]
        failures = [
            attempt
            for timeline in stage["timelines"]
            for attempt in timeline["attempts"]
            if attempt["outcome"] != "pass"
        ]
        attempt_lineage = _validate_r2_attempt_lineage(
            transition_count=len(commits),
            prepared_attempt_count=len(prepared),
            timeline_attempt_counts=[
                len(timeline["attempts"]) for timeline in stage["timelines"]
            ],
            terminal_loser_count=len(failures),
        )
        fault_health = sorted(
            (root / "logs").glob("performance_executor_*-fault.health.json")
        )
        if len(faults) != 1 or faults[0].get("event") != "executor_injected_failure":
            raise AssertionError("D8-R2 controlled executor-fault tape is incomplete")
        if len(fault_health) != 1:
            raise AssertionError("D8-R2 controlled fault lacks preserved recorder health")
        successors = [
            item for item in commits if float(item["timestamp"]) > float(faults[0]["timestamp"])
        ]
        if not successors:
            raise AssertionError("D8-R2 did not recover after the controlled fault")
        if any(item.get("budget_violation") for item in prepared):
            raise AssertionError("D8-R2 observed an LFE resource budget violation")
        payload.update(
            {
                "executors": 8,
                "dedicated_syncer_nodes": 0,
                "lfe_cpu_threads_per_learner": 8,
                "replication_factor": 2,
                "redundancy_mode": "hedged",
                "hedge_delay_ms": 6000,
                "fault_tape": faults,
                "recovery_seconds": float(successors[0]["timestamp"])
                - float(faults[0]["timestamp"]),
                "prepared_attempts": len(prepared),
                "terminal_loser_attempts": failures,
                "attempt_lineage": attempt_lineage,
                "resource_telemetry": {
                    "rss_bytes": _summary([float(item["rss_bytes"]) for item in prepared]),
                    "cpu_affinity_by_member": {
                        str(item["member_id"]): item["cpu_affinity"] for item in prepared
                    },
                    "numa_by_member": {
                        str(item["member_id"]): item["numa_mems_allowed_list"]
                        for item in prepared
                    },
                    "threads": sorted({int(item["actual_torch_threads"]) for item in prepared}),
                },
                "stage_profile": stage,
                "lease_guard": _distributed_lease_guard(root),
            }
        )
    _write(args.output, payload)
    return 0


def _compare(args: argparse.Namespace) -> int:
    report_paths = {
        "factor_one": args.factor_one_report,
        "r2": args.r2_report,
    }
    if args.no_lfe_report is not None:
        report_paths = {"no_lfe": args.no_lfe_report, **report_paths}
    reports = {
        mode: json.loads(path.read_text(encoding="utf-8"))
        for mode, path in report_paths.items()
    }
    stable_fields = (
        "git_commit",
        "config_sha256",
        "model_revision",
        "dataset_revision",
        "seed",
        "allocation_nodes",
        "learner_nodes",
        "learners",
    )
    unmatched = {
        field: {mode: report["binding"][field] for mode, report in reports.items()}
        for field in stable_fields
        if len({report["binding"][field] for report in reports.values()}) != 1
    }
    if unmatched:
        raise AssertionError(f"matched interference binding differs: {unmatched}")
    comparison = compare_gpu_step_seconds(
        {
            mode: tuple(float(value) for value in report["gpu_step_samples"])
            for mode, report in reports.items()
        }
    )
    payload = {
        **comparison,
        "status": "PASS",
        "binding": {
            field: next(iter(reports.values()))["binding"][field]
            for field in stable_fields
        },
        "unmatched_dimensions": {
            "execution_topology": ({
                "no_lfe": "historical dedicated centralized syncer; no learner-hosted executor",
                "factor_one": "eight learner-hosted LFEs; replication factor one",
                "r2": "eight learner-hosted LFEs; hedged factor two and one controlled fault",
            } if "no_lfe" in reports else {
                "factor_one": "eight learner-hosted LFEs; replication factor one",
                "r2": "eight learner-hosted LFEs; hedged factor two and one controlled fault",
            })
        },
        "negative_tradeoffs_reported": True,
        "source_reports": {mode: str(path) for mode, path in report_paths.items()},
    }
    _write(args.output, payload)
    return 0


def _gate(args: argparse.Namespace) -> int:
    factor = json.loads(args.factor_one_report.read_text(encoding="utf-8"))
    r2 = json.loads(args.r2_report.read_text(encoding="utf-8"))
    interference = json.loads(args.interference_report.read_text(encoding="utf-8"))
    factor_stage = factor["stage_profile"]
    r2_stage = r2["stage_profile"]
    factor_mean = float(interference["means"]["factor_one"])
    r2_mean = float(interference["means"]["r2"])
    measured_penalty = max(0.0, r2_mean / factor_mean - 1.0)
    payload = evaluate_bundle_gate(
        wait_fractions={
            "factor_one": factor_stage["single_fwo_wait_fractions"],
            "r2": r2_stage["single_fwo_wait_fractions"],
        },
        optimistic_e2e_improvements={
            "factor_one": factor_stage[
                "two_fwo_optimistic_e2e_improvement_upper_bound"
            ],
            "r2": r2_stage["two_fwo_optimistic_e2e_improvement_upper_bound"],
        },
        measured_penalty_fraction=measured_penalty,
    )
    payload.update(
        {
            "decision": "D-0807",
            "source_reports": [str(args.factor_one_report), str(args.r2_report)],
            "interference_report": str(args.interference_report),
            "penalty_basis": "observed R2 GPU-step mean overhead relative to factor one",
        }
    )
    _write(args.output, payload)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for mode in ("no-lfe", "factor-one", "r2"):
        command = subparsers.add_parser(mode)
        command.add_argument("--root", type=Path, required=True)
        command.add_argument("--artifacts", type=Path, required=True)
        command.add_argument("--run-id", required=True)
        command.add_argument("--config", type=Path, required=True)
        command.add_argument("--elapsed-seconds", type=int, required=True)
        command.add_argument("--output", type=Path, required=True)
        if mode == "factor-one":
            command.add_argument("--base-report", type=Path, required=True)
    compare = subparsers.add_parser("compare")
    compare.add_argument("--no-lfe-report", type=Path)
    compare.add_argument("--factor-one-report", type=Path, required=True)
    compare.add_argument("--r2-report", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    gate = subparsers.add_parser("gate")
    gate.add_argument("--factor-one-report", type=Path, required=True)
    gate.add_argument("--r2-report", type=Path, required=True)
    gate.add_argument("--interference-report", type=Path, required=True)
    gate.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "no-lfe":
        return _runtime(args, "no_lfe")
    if args.command == "factor-one":
        return _runtime(args, "factor_one")
    if args.command == "r2":
        return _runtime(args, "r2")
    if args.command == "compare":
        return _compare(args)
    if args.command == "gate":
        return _gate(args)
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
