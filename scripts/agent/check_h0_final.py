#!/usr/bin/env python3
"""Independently check H0 RED/GREEN, identity, and Miyabi evidence."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import yaml


BASELINE_TESTS = (
    "tests/distributed_syncer/test_lease_stage_guard.py::test_committer_conflict_finalization_publishes_only_authoritative_stop",
    "tests/distributed_syncer/test_lease_stage_guard.py::test_committer_finalization_never_masks_active_error",
    "tests/distributed_syncer/test_lease_stage_guard.py::test_committer_crash_marks_error_before_finalization",
    "tests/distributed_syncer/test_lease_stage_guard.py::test_committer_prepare_conflict_forces_strict_replay_and_result_wait_renews",
    "tests/coordination/test_lease_manager.py::test_concurrent_bootstrap_loser_is_converted_to_coordination_conflict",
    "tests/test_fragment_learner_multifragment.py::test_fragment_learner_round_robin_preserves_interval_fragment_metadata",
    "tests/test_config.py::test_grace_window_must_fit_inside_lease_renewal_budget",
    "tests/storage/test_capability_probe.py::test_multiprocess_advisory_lock_scope_probe",
    "tests/lifecycle/test_distributed_reachability.py::test_payload_corrupted_unknown_object_is_discovered_and_never_collected",
    "tests/storage/test_posix_contract.py::test_posix_idempotent_immutable_put_compares_header_identity_only",
    "tests/storage/test_posix_contract.py::test_posix_listing_and_head_are_header_only_but_get_still_verifies_payload",
    "tests/storage/test_posix_contract.py::test_posix_prefix_listing_and_head_read_no_payload_bytes",
    "tests/test_liveness.py::test_previous_generation_heartbeat_cannot_complete_current_training",
    "tests/storage/test_posix_contract.py::test_shared_authority_root_fails_closed_without_cross_node_lock",
    "tests/test_proposal_catalog.py::test_unsupported_payload_dtype_has_typed_quarantine_reason",
    "tests/coordination/test_production_fencing.py::test_control_response_loss_resolves_from_suffix_only_ancestry",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--base-commit", required=True)
    parser.add_argument("--runtime-commit", required=True)
    parser.add_argument("--unit-root", required=True)
    parser.add_argument("--d1-root", required=True)
    parser.add_argument("--d2-root", required=True)
    parser.add_argument("--lock-root", required=True)
    parser.add_argument("--d8-root", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    output: Path | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if output is not None:
        output.write_text(result.stdout, encoding="utf-8")
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n{result.stdout}"
        )
    return result


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def _manifest(root: Path, runtime_commit: str) -> dict:
    manifest = _load_json(root / "manifest.json")
    if manifest.get("result") != "pass" or manifest.get("exit_code") != 0:
        raise RuntimeError(f"run did not pass: {root}")
    if manifest.get("git_commit") != runtime_commit:
        raise RuntimeError(f"run used wrong commit: {root}")
    return manifest


def _junit_counts(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    keys = ("tests", "failures", "errors", "skipped")
    return {key: sum(int(suite.attrib.get(key, 0)) for suite in suites) for key in keys}


def _identity_probe(
    *, python: str, script: Path, cwd: Path, output: Path
) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(cwd)
    _run(
        [python, str(script), "--output", str(output)],
        cwd=cwd,
        env=env,
        output=output.with_suffix(".log"),
        check=True,
    )
    return _load_json(output)


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    artifact_root = Path(args.artifact_root).resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    output = Path(args.output).resolve()
    runtime_commit = args.runtime_commit

    changed_runtime_paths = _run(
        ["git", "diff", "--name-only", f"{runtime_commit}..HEAD"],
        cwd=root,
        check=True,
    ).stdout.splitlines()
    forbidden_post_runtime = [
        path
        for path in changed_runtime_paths
        if path.startswith(("fs_diloco/", "configs/", "pyproject.toml"))
    ]
    if forbidden_post_runtime:
        raise RuntimeError(f"runtime changed after qualification: {forbidden_post_runtime}")

    unit_root = Path(args.unit_root).resolve()
    d1_root = Path(args.d1_root).resolve()
    d2_root = Path(args.d2_root).resolve()
    lock_root = Path(args.lock_root).resolve()
    d8_root = Path(args.d8_root).resolve()
    manifests = {
        name: _manifest(path, runtime_commit)
        for name, path in {
            "unit": unit_root,
            "d1": d1_root,
            "d2": d2_root,
            "lock": lock_root,
            "d8": d8_root,
        }.items()
    }
    unit_counts = _junit_counts(unit_root / "full-junit.xml")
    if unit_counts != {"tests": 469, "failures": 0, "errors": 0, "skipped": 1}:
        raise RuntimeError(f"unexpected full-suite counts: {unit_counts}")

    d2 = _load_json(d2_root / "p07_d2_report.json")
    d2_cycles = d2.get("lifecycle_cycles", [])
    if (
        d2.get("status") != "PASS"
        or d2.get("optimizer_transition_count") != 4
        or len(d2_cycles) != 4
        or any(cycle.get("inventory_payload_bytes_read") != 0 for cycle in d2_cycles)
    ):
        raise RuntimeError("D2 lifecycle counter evidence failed")
    predicted_d2_legacy_bytes = sum(cycle["inventory_bytes"] for cycle in d2_cycles)
    observed_d2_inventory_payload_bytes = sum(
        cycle["inventory_payload_bytes_read"] for cycle in d2_cycles
    )

    lock = _load_json(lock_root / "cross_node_lock_report.json")
    if not all(
        lock.get(key)
        for key in (
            "passed",
            "blocked_while_held",
            "acquired_after_release",
            "distinct_hosts",
        )
    ):
        raise RuntimeError("cross-node advisory-lock evidence failed")

    d8_runtime = _load_json(d8_root / "d8_r2_report.json")
    d8_lifecycle = _load_json(d8_root / "p07_d8_report.json")
    d8_cycles = d8_lifecycle.get("lifecycle_cycles", [])
    if (
        d8_runtime.get("status") != "PASS"
        or d8_runtime.get("optimizer_transitions") != 10
        or d8_runtime.get("learner_nodes") != 8
        or d8_runtime.get("dedicated_syncer_nodes") != 0
        or d8_lifecycle.get("status") != "PASS"
        or d8_lifecycle.get("optimizer_transition_count") != 10
        or len(d8_cycles) != 5
        or any(cycle.get("inventory_payload_bytes_read") != 0 for cycle in d8_cycles)
    ):
        raise RuntimeError("D8-R2 50x10 evidence failed")
    config = yaml.safe_load(
        (root / "configs/duraloco_milestone_gpt2_9node_50x10.yaml").read_text(
            encoding="utf-8"
        )
    )
    if config["training"]["inner_steps"] != 50 or config["sync"]["stop_after_outer_steps"] != 10:
        raise RuntimeError("terminal run config is not 50 local x 10 global")
    executor_wait_renewals = sum(
        path.read_text(encoding="utf-8").count('"substage": "executor_result_wait"')
        for path in d8_root.glob("member-*_committer.log")
    )
    if executor_wait_renewals < 1:
        raise RuntimeError("D8 has no in-wait lease-renewal evidence")

    patch = _run(
        ["git", "diff", args.base_commit, "HEAD", "--", "tests"],
        cwd=root,
        check=True,
    ).stdout
    patch_path = artifact_root / "h0-tests.patch"
    patch_path.write_text(patch, encoding="utf-8")
    base_worktree = Path(tempfile.mkdtemp(prefix="h0-base-"))
    shutil.rmtree(base_worktree)
    red_results: list[dict[str, object]] = []
    try:
        _run(
            ["git", "worktree", "add", "--detach", str(base_worktree), args.base_commit],
            cwd=root,
            check=True,
        )
        apply_result = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", "-"],
            cwd=base_worktree,
            input=patch,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if apply_result.returncode != 0:
            raise RuntimeError(f"failed to overlay H0 tests on baseline: {apply_result.stdout}")
        base_env = os.environ.copy()
        base_env["PYTHONPATH"] = str(base_worktree)
        for index, node_id in enumerate(BASELINE_TESTS, start=1):
            result = _run(
                [args.python, "-m", "pytest", "-q", node_id],
                cwd=base_worktree,
                env=base_env,
                output=artifact_root / f"red-{index:02d}.log",
            )
            red_results.append(
                {"node_id": node_id, "returncode": result.returncode, "failed_on_base": result.returncode != 0}
            )
        if not all(result["failed_on_base"] for result in red_results):
            raise RuntimeError("one or more H0 RED tests unexpectedly passed on c099adc")

        identity_script = root / "scripts/agent/h0_identity_tape.py"
        base_identity = _identity_probe(
            python=args.python,
            script=identity_script,
            cwd=base_worktree,
            output=artifact_root / "identity-base.json",
        )
    finally:
        _run(
            ["git", "worktree", "remove", "--force", str(base_worktree)],
            cwd=root,
        )

    green_junit = artifact_root / "green-junit.xml"
    green = _run(
        [args.python, "-m", "pytest", "-q", *BASELINE_TESTS, f"--junitxml={green_junit}"],
        cwd=root,
        output=artifact_root / "green.log",
    )
    if green.returncode != 0:
        raise RuntimeError("one or more H0 GREEN tests failed")
    green_counts = _junit_counts(green_junit)
    if green_counts["failures"] or green_counts["errors"]:
        raise RuntimeError(f"H0 GREEN JUnit failed: {green_counts}")

    runtime_identity = _identity_probe(
        python=args.python,
        script=root / "scripts/agent/h0_identity_tape.py",
        cwd=root,
        output=artifact_root / "identity-runtime.json",
    )
    if runtime_identity != base_identity:
        raise RuntimeError("committed identities changed across H0")

    report = {
        "schema": "duraloco-h0-checker-v1",
        "status": "PASS",
        "base_commit": args.base_commit,
        "runtime_commit": runtime_commit,
        "checker_commit": _run(["git", "rev-parse", "HEAD"], cwd=root, check=True).stdout.strip(),
        "red": {"expected_failures": len(BASELINE_TESTS), "observed_failures": len(red_results), "results": red_results},
        "green": green_counts,
        "identity_equal": True,
        "identity": runtime_identity,
        "unit": unit_counts,
        "d2_inventory_counter_evidence": {
            "cycles": len(d2_cycles),
            "predicted_legacy_payload_bytes": predicted_d2_legacy_bytes,
            "observed_inventory_payload_bytes": observed_d2_inventory_payload_bytes,
        },
        "cross_node_lock": lock,
        "d8_50x10": {
            "elapsed_seconds": d8_runtime["elapsed_seconds"],
            "optimizer_transitions": d8_runtime["optimizer_transitions"],
            "lifecycle_cycles": len(d8_cycles),
            "executor_wait_renewal_heartbeats": executor_wait_renewals,
            "max_recovery_seconds": d8_runtime["max_recovery_seconds"],
        },
        "manifests": {name: manifest["run_id"] for name, manifest in manifests.items()},
        "required_gate_followups": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
