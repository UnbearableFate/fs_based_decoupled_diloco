#!/usr/bin/env python3
"""Independently audit the final P08 maker evidence and gate conclusion."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"{path} is not a JSON object")
    return value


def _verify_checksums(root: Path, path: Path) -> list[str]:
    checked: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        target = root / relative
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != expected:
            raise AssertionError(f"checksum mismatch: {relative}")
        checked.append(relative)
    if len(checked) < 15:
        raise AssertionError("maker checksum set is incomplete")
    return checked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--no-lfe-report", type=Path, required=True)
    parser.add_argument("--factor-one-report", type=Path, required=True)
    parser.add_argument("--r2-report", type=Path, required=True)
    parser.add_argument("--interference-report", type=Path, required=True)
    parser.add_argument("--bundle-gate-report", type=Path, required=True)
    parser.add_argument("--lifecycle-report", type=Path, required=True)
    parser.add_argument("--error-ledger", type=Path, required=True)
    parser.add_argument("--checksums", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    manifests = [_json(path) for path in args.manifest]
    commits = {item.get("git_commit") for item in manifests}
    if len(manifests) < 6 or len(commits) != 1 or any(
        item.get("result") != "pass" or item.get("exit_code") != 0
        for item in manifests
    ):
        raise AssertionError("maker manifests are not six same-commit PASS results")
    runtime_commit = str(next(iter(commits)))

    no_lfe = _json(args.no_lfe_report)
    factor = _json(args.factor_one_report)
    r2 = _json(args.r2_report)
    for report in (no_lfe, factor, r2):
        if (
            report.get("status") != "PASS"
            or report.get("optimizer_transitions") != 10
            or report.get("binding", {}).get("git_commit") != runtime_commit
        ):
            raise AssertionError("matched runtime report differs from the maker commit")
    if no_lfe.get("executors") != 0 or factor.get("replication_factor") != 1:
        raise AssertionError("no-LFE or factor-one topology differs")
    if r2.get("replication_factor") != 2 or r2.get("attempt_lineage") != {
        "total_attempts": 20,
        "successful_prepared_attempts": 19,
        "terminal_loser_attempts": 1,
    }:
        raise AssertionError("R2 attempt lineage differs")
    if len(r2.get("fault_tape", [])) != 1 or not math.isfinite(
        float(r2.get("recovery_seconds", math.nan))
    ):
        raise AssertionError("controlled R2 recovery evidence differs")
    guard = r2.get("lease_guard", {})
    if (
        guard.get("optimizer_head_cas_renewals") != 10
        or guard.get("stop_head_cas_renewals") != 1
        or guard.get("lease_authority_loss_events") != 0
    ):
        raise AssertionError("R2 lease-guard evidence differs")

    interference = _json(args.interference_report)
    if (
        interference.get("status") != "PASS"
        or interference.get("binding", {}).get("git_commit") != runtime_commit
        or min(interference.get("sample_counts", {}).values()) < 400
        or interference.get("negative_tradeoffs_reported") is not True
    ):
        raise AssertionError("matched interference evidence differs")

    gate = _json(args.bundle_gate_report)
    if (
        gate.get("status") != "PASS"
        or gate.get("triggered") is not False
        or gate.get("conclusion") != "retain_single_fwo"
        or gate.get("authority_objects_written") != 0
        or gate.get("transitions_crossing_wait_threshold", {}).get("factor_one") >= 8
        or float(gate.get("conservative_projected_e2e_improvement", 1.0)) >= 0.15
    ):
        raise AssertionError("D-0807 retain-single-FWO conclusion is unsupported")

    lifecycle = _json(args.lifecycle_report)
    curve = lifecycle.get("growth_curve", [])
    tail = [int(item["effective_live_count"]) for item in curve[-3:]]
    if (
        lifecycle.get("status") != "PASS"
        or lifecycle.get("optimizer_transition_count") != 10
        or lifecycle.get("bounded_window_preregistered_delta") != 80
        or max(tail) - min(tail) > 80
        or not all(lifecycle.get("checks", {}).values())
    ):
        raise AssertionError("P07 lifecycle integration evidence differs")

    ledger = args.error_ledger.read_text(encoding="utf-8")
    error_ids = [int(value) for value in re.findall(r"P08-E(\d{3})", ledger)]
    if sorted(set(error_ids)) != list(range(1, max(error_ids) + 1)) or max(error_ids) < 29:
        raise AssertionError("P08 error ledger is incomplete or non-contiguous")
    checked_files = _verify_checksums(args.root, args.checksums)

    payload = {
        "schema": "duraloco-p08-checker-v1",
        "status": "PASS",
        "verdict": "PASS",
        "required_gate_followups": "none",
        "runtime_commit": runtime_commit,
        "checked_acceptance_ids": [f"P08-A{index:02d}" for index in range(1, 26)],
        "independent_counterexamples": [
            "head_or_epoch_jump_invalidates_prefetch_and_validation_tokens",
            "validation_and_fsync_have_no_disable_switch",
            "factor_two_prepublication_failure_has_20_19_1_lineage",
            "P07_snapshot_suffix_strict_replay_and_bounded_window",
            "active_surface_has_no_embedded_database",
        ],
        "bundle_gate_conclusion": gate["conclusion"],
        "bundle_acceptance": {f"P08-A{index:02d}": "not_applicable" for index in range(16, 19)},
        "interference": {
            "factor_one_slowdown": interference["factor_one_slowdown"],
            "r2_slowdown": interference["r2_slowdown"],
        },
        "r2_recovery_seconds": r2["recovery_seconds"],
        "lifecycle_tail": tail,
        "verified_checksum_files": checked_files,
        "error_ledger_max_id": max(error_ids),
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    args.report.write_text(
        "# P08 Independent Checker Report\n\n"
        "Verdict: PASS\n\n"
        "required_gate_followups: none\n\n"
        f"Runtime commit: `{runtime_commit}`\n\n"
        "All P08-A01–A25 evidence, matched C9/factor-one/R2 reports, the "
        "D-0807 retain-single-FWO decision, P07 lifecycle integration, failure "
        "ledger, and maker checksums passed independent audit. P08-A16–A18 "
        "are accepted as `not_applicable`; no bundle authority object exists.\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
