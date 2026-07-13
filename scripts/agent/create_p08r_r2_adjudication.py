#!/usr/bin/env python3
"""Adjudicate a preserved R2 run under the user-approved reasonable envelope."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-artifacts", type=Path, required=True)
    parser.add_argument("--max-experiment-seconds", type=float, default=600.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source_artifacts
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    elapsed = json.loads((source / "elapsed_contract.json").read_text(encoding="utf-8"))
    performance = json.loads(
        (source / "p08_d8_r2_report.json").read_text(encoding="utf-8")
    )
    interference = json.loads(
        (source / "interference_report.json").read_text(encoding="utf-8")
    )
    bundle = json.loads((source / "bundle_gate_report.json").read_text(encoding="utf-8"))
    lifecycle = json.loads(
        (source / "p07_lifecycle_report.json").read_text(encoding="utf-8")
    )
    junit = ET.parse(source / "p07_regression_junit.xml").getroot()
    tests = int(junit.attrib.get("tests", 0))
    failures = int(junit.attrib.get("failures", 0))
    errors = int(junit.attrib.get("errors", 0))
    skipped = int(junit.attrib.get("skipped", 0))

    experiment_seconds = float(elapsed["experiment_elapsed_seconds"])
    post_seconds = float(elapsed["post_runtime_elapsed_seconds"])
    binding = performance["binding"]
    checks = {
        "source_failed_only_old_elapsed_gate": (
            manifest["result"] == "fail"
            and elapsed["status"] == "FAIL"
            and float(elapsed["max_experiment_seconds"]) == 440.0
        ),
        "reasonable_elapsed_envelope": experiment_seconds
        <= args.max_experiment_seconds,
        "post_runtime_budget": post_seconds <= 25.0,
        "performance_report": performance["status"] == "PASS",
        "interference_report": interference["status"] == "PASS",
        "bundle_gate_report": bundle["status"] == "PASS",
        "lifecycle_report": lifecycle["status"] == "PASS",
        "lifecycle_regressions": tests > 0 and failures == 0 and errors == 0,
        "exact_eight_node_binding": (
            binding["allocation_nodes"] == 8
            and binding["learner_nodes"] == 8
            and len(binding["hosts"]) == 8
        ),
        "clean_source_commit_binding": (
            binding["git_commit"] == manifest["git_commit"]
            and manifest["dirty_tree"] is False
        ),
        "terminal_strict_audit": performance["terminal_audit"]["status"]
        == "PASS",
        "ten_optimizer_transitions": performance["optimizer_transitions"] == 10,
    }
    if not all(checks.values()):
        failed = sorted(key for key, value in checks.items() if not value)
        raise RuntimeError(f"R2 reasonable-envelope adjudication failed: {failed}")

    report = {
        "schema": "duraloco-p08r-r2-reasonable-envelope-v1",
        "status": "PASS",
        "decision": "D-4406",
        "source_artifacts": str(source),
        "source_run_id": manifest["run_id"],
        "source_pbs_job_id": manifest["pbs_job_id"],
        "source_git_commit": manifest["git_commit"],
        "runtime_elapsed_seconds": elapsed["runtime_elapsed_seconds"],
        "post_runtime_elapsed_seconds": post_seconds,
        "experiment_elapsed_seconds": experiment_seconds,
        "max_experiment_seconds": args.max_experiment_seconds,
        "metric_note": (
            "R2 error-recovery is bounded by a practical ten-minute complete-"
            "experiment envelope; the historical 440-second target is diagnostic"
        ),
        "junit": {
            "tests": tests,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
        },
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
