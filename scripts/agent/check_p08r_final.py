#!/usr/bin/env python3
"""Independent P08R evidence checker for the pre-P10 handoff."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def _manifest(root: Path, *, result: str = "pass") -> dict[str, object]:
    value = _json(root / "manifest.json")
    if value.get("result") != result:
        raise RuntimeError(f"unexpected manifest result at {root}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--error-ledger", type=Path, required=True)
    parser.add_argument("--factor-repeat-artifacts", type=Path, required=True)
    parser.add_argument("--factor-one-artifacts", type=Path, required=True)
    parser.add_argument("--r2-artifacts", type=Path, required=True)
    parser.add_argument("--proof-artifacts", type=Path, required=True)
    parser.add_argument("--full-artifacts", type=Path, required=True)
    parser.add_argument("--d1-artifacts", type=Path, required=True)
    parser.add_argument("--d2-artifacts", type=Path, required=True)
    parser.add_argument("--independent-replay", type=Path, required=True)
    parser.add_argument("--forbidden-surface", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    state = yaml.safe_load(args.state.read_text(encoding="utf-8"))
    ledger = yaml.safe_load(args.error_ledger.read_text(encoding="utf-8"))
    factor_repeat_manifest = _manifest(args.factor_repeat_artifacts)
    factor_manifest = _manifest(args.factor_one_artifacts)
    r2_manifest = _manifest(args.r2_artifacts, result="fail")
    proof_manifest = _manifest(args.proof_artifacts)
    full_manifest = _manifest(args.full_artifacts)
    d1_manifest = _manifest(args.d1_artifacts)
    d2_manifest = _manifest(args.d2_artifacts)
    factor_repeat_elapsed = _json(
        args.factor_repeat_artifacts / "elapsed_contract.json"
    )
    factor_elapsed = _json(args.factor_one_artifacts / "elapsed_contract.json")
    factor = _json(args.factor_one_artifacts / "p08_d8_report.json")
    r2_elapsed = _json(args.r2_artifacts / "elapsed_contract.json")
    r2 = _json(args.r2_artifacts / "p08_d8_r2_report.json")
    interference = _json(args.r2_artifacts / "interference_report.json")
    bundle = _json(args.r2_artifacts / "bundle_gate_report.json")
    lifecycle = _json(args.r2_artifacts / "p07_lifecycle_report.json")
    proof = _json(args.proof_artifacts / "snapshot_suffix_benchmark.json")
    adjudication = _json(args.proof_artifacts / "r2_adjudication.json")
    independent = _json(args.independent_replay)
    forbidden = _json(args.forbidden_surface)

    qualification_commit = "ac2d961f148841b14ba7bc628ce1566695571bf0"
    runtime_commit = "ba0a5c693eb586d5db27b7e304f230d4acd826a8"
    checks = {
        "state_phase": state["phase"] == "P08R" and state["status"] == "in_progress",
        "maker_acceptance_a01_a19": all(
            state["acceptance"][f"P08R-A{index:02d}"]["result"] == "pass"
            for index in range(1, 20)
        ),
        "maker_a20_waits_for_checker": state["acceptance"]["P08R-A20"]["result"]
        == "not_run",
        "failure_ledger_complete": [
            item["error_id"] for item in ledger["entries"]
        ]
        == [f"P08R-E{index:03d}" for index in range(1, 14)],
        "failure_reasons_recorded": all(
            item.get("situation") and item.get("reason") for item in ledger["entries"]
        ),
        "factor_repeat_440": (
            factor_repeat_elapsed["status"] == "PASS"
            and factor_repeat_elapsed["experiment_elapsed_seconds"] <= 440
            and factor_repeat_manifest["dirty_tree"] is False
        ),
        "factor_one_440": (
            factor_elapsed["status"] == "PASS"
            and factor_elapsed["experiment_elapsed_seconds"] <= 440
            and factor["status"] == "PASS"
        ),
        "factor_exact_eight": (
            factor["binding"]["allocation_nodes"] == 8
            and factor["binding"]["learner_nodes"] == 8
            and len(factor["binding"]["hosts"]) == 8
        ),
        "r2_old_gate_only": (
            r2_elapsed["status"] == "FAIL"
            and r2_elapsed["experiment_elapsed_seconds"] <= 600
            and r2_elapsed["post_runtime_elapsed_seconds"] <= 25
        ),
        "r2_reports_pass": all(
            report["status"] == "PASS"
            for report in (r2, interference, bundle, lifecycle)
        ),
        "r2_exact_eight": (
            r2["binding"]["allocation_nodes"] == 8
            and r2["binding"]["learner_nodes"] == 8
            and len(r2["binding"]["hosts"]) == 8
        ),
        "matched_runtime_commit": (
            factor_manifest["git_commit"] == runtime_commit
            and r2_manifest["git_commit"] == runtime_commit
            and factor["binding"]["git_commit"] == r2["binding"]["git_commit"]
        ),
        "r2_attempt_and_terminal_contract": (
            r2["optimizer_transitions"] == 10
            and r2["attempt_lineage"]["total_attempts"] == 20
            and r2["attempt_lineage"]["successful_prepared_attempts"] == 19
            and r2["terminal_audit"]["status"] == "PASS"
        ),
        "d4406_adjudication": (
            adjudication["status"] == "PASS"
            and adjudication["decision"] == "D-4406"
            and adjudication["source_pbs_job_id"] == "2372318.opbs"
        ),
        "suffix_memo_real_prefix": (
            proof["status"] == "PASS"
            and proof["optimizer_suffix_transitions"] == 2
            and proof["first_call"]["tensor_payload_bytes"] > 0
            and proof["second_call"]["tensor_payload_bytes"] == 0
            and proof["source_head_sha256_before"]
            == proof["source_head_sha256_after"]
        ),
        "independent_empty_cache_replay": (
            independent["status"] == "PASS"
            and independent["committed_state_digest"]
            == r2["terminal_audit"]["strict_state_digest"]
            and independent["head_sha256_before"] == independent["head_sha256_after"]
        ),
        "same_commit_qualification": all(
            manifest["git_commit"] == qualification_commit
            for manifest in (proof_manifest, full_manifest, d1_manifest, d2_manifest)
        ),
        "qualification_manifests_clean": all(
            manifest["dirty_tree"] is False
            for manifest in (proof_manifest, full_manifest, d1_manifest, d2_manifest)
        ),
        "forbidden_surface_empty": forbidden["finding_count"] == 0,
    }
    failed = sorted(key for key, value in checks.items() if not value)
    if failed:
        raise RuntimeError(f"independent P08R checker failed: {failed}")
    report = {
        "schema": "duraloco-p08r-independent-checker-v1",
        "status": "PASS",
        "verdict": "PASS",
        "required_followups": [],
        "checked_acceptance_ids": [f"P08R-A{index:02d}" for index in range(1, 20)],
        "runtime_commit": runtime_commit,
        "qualification_commit": qualification_commit,
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
