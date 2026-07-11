#!/usr/bin/env python3
"""Independent P06B evidence, authority, topology, and counterexample audit."""

from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import socket
import xml.etree.ElementTree as ET

import yaml

from fs_diloco.storage import InMemoryStorageBackend
from fs_diloco.syncer_core.capabilities import PrepareObjectFacade
from scripts.agent.check_run_manifest import validate as validate_manifest


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _junit_passes(path: Path) -> bool:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    return not any(
        int(suite.attrib.get("failures", 0)) or int(suite.attrib.get("errors", 0))
        for suite in suites
    )


def _counterexample() -> dict[str, object]:
    backend = InMemoryStorageBackend()
    facade = PrepareObjectFacade(
        backend, read_prefixes=("inputs/",), write_prefixes=("prepared/",)
    )
    facade.put_immutable("prepared/result-a", b"one")
    conflict_rejected = False
    try:
        facade.put_immutable("prepared/result-a", b"different")
    except Exception:
        conflict_rejected = True
    head_rejected = False
    try:
        facade.put_immutable("runs/check/control/head.json", b"forbidden")
    except PermissionError:
        head_rejected = True
    if not conflict_rejected or not head_rejected or hasattr(facade, "conditional_replace"):
        raise AssertionError("Checker conflicting prepare/head-write counterexample did not fail")
    return {
        "same_identity_conflicting_content_rejected": conflict_rejected,
        "prepare_head_write_rejected": head_rejected,
        "conditional_replace_exposed": False,
        "pass": True,
    }


def run(root: Path, artifact_root: Path, manifests: list[Path]) -> dict[str, object]:
    for path in manifests:
        validate_manifest(path, root=root)
    rows = [_load(path) for path in manifests]
    if any(row["phase"] != "P06B" or row["result"] != "pass" or row["dirty_tree"] for row in rows):
        raise AssertionError("Maker manifest is not a clean passing P06B artifact")
    unit, d1, d2, d8, comparison = rows
    runtime_commit = unit["git_commit"]
    if any(row["git_commit"] != runtime_commit for row in (d1, d2, d8)):
        raise AssertionError("unit/D1/D2/D8 do not share one runtime commit")
    if [d1["parent_run_id"], d2["parent_run_id"], d8["parent_run_id"]] != [
        unit["run_id"], d1["run_id"], d2["run_id"]
    ]:
        raise AssertionError("Maker runtime lineage differs")
    if comparison["parent_run_id"] != d8["run_id"]:
        raise AssertionError("comparison is not linked to final D8")
    if not _junit_passes(manifests[0].parent / "junit.xml"):
        raise AssertionError("focused unit JUnit contains failures")

    one = _load(manifests[1].parent / "d1_report.json")
    two = _load(manifests[2].parent / "d2_report.json")
    terminal = _load(manifests[3].parent / "d8_report.json")
    compare = _load(manifests[4].parent / "comparison.json")
    if not (one["status"] == "PASS" and one["distributed_commits"] >= 1 and one["boundary_adoptions"] >= 1):
        raise AssertionError("D1 evidence differs")
    if not (
        two["status"] == "PASS"
        and two["optimizer_transitions"] == 3
        and two["executor_kills"] == two["committer_kills"] == two["whole_node_kills"] == 1
        and two["membership_revision"] == 1
    ):
        raise AssertionError("D2 failure evidence differs")
    if not (
        terminal["status"] == "PASS"
        and terminal["learner_nodes"] == terminal["learners"] == terminal["executors"] == 8
        and terminal["dedicated_syncer_nodes"] == 0
        and terminal["optimizer_transitions"] == terminal["distributed_commits"] == 10
        and terminal["prepared_markers"] == terminal["executor_prepare_events"] == 10
        and terminal["invalid_losses"] == 0
        and terminal["elapsed_seconds"] <= 900
        and terminal["control_sequence"] == ["epoch_bump", "stop"]
        and len(terminal["resource_telemetry"]["cpu_affinity_by_executor"]) == 8
        and len(terminal["transition_latency"]) == 10
    ):
        raise AssertionError("D8 terminal/resource evidence differs")
    if not (
        compare["status"] == "PASS"
        and compare["policy_identity_exact"]
        and compare["same_fwo_lfe_to_final_exact"]
        and compare["numeric_tolerance"] == {"atol": 0.05, "rtol": 0.1, "allclose": True}
        and not compare["content_identity_claimed_across_backends"]
        and compare["distributed_control_sequence"] == ["epoch_bump", "stop"]
    ):
        raise AssertionError("C9/D8 comparison differs")

    state = yaml.safe_load((root / "plans/duraloco/STATE.yaml").read_text())
    expected = {f"P06B-A{index:02d}" for index in range(1, 24)}
    if state["phase"] != "P06B" or state["status"] != "checking" or set(state["acceptance"]) != expected:
        raise AssertionError("P06B checking state differs")
    for key, value in state["acceptance"].items():
        expected_result = "not_run" if key == "P06B-A22" else "pass"
        if value["result"] != expected_result:
            raise AssertionError(f"Maker acceptance differs for {key}")
    report = (root / "plans/duraloco/phases/P06B_PHASE_REPORT.md").read_text()
    if "## English" not in report or "## 中文" not in report:
        raise AssertionError("P06B report is not bilingual")
    errors = yaml.safe_load((root / "plans/duraloco/errors/P06B_ERROR_LEDGER.yaml").read_text())
    if len(errors["records"]) < 5 or any(
        not all(key in row for key in ("phenomenon", "cause", "repair", "verification", "artifacts"))
        for row in errors["records"]
    ):
        raise AssertionError("P06B detailed error ledger differs")
    source = (root / "fs_diloco/distributed_syncer/executor.py").read_text()
    tree = ast.parse(source)
    imports = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    if any(name.startswith(("fs_diloco.storage", "fs_diloco.coordination")) for name in imports):
        raise AssertionError("executor imports authority capability")
    forbidden = _load(artifact_root / "forbidden_surface.json")
    reference = _load(artifact_root / "reference_10000.json")
    if forbidden["finding_count"] != 0 or reference["count"] != 10_000:
        raise AssertionError("Checker static/reference gate differs")
    return {
        "schema_version": 2,
        "verdict": "PASS",
        "required_gate_followups": "none",
        "checking_to_completed": "AUTHORIZED",
        "checker_pbs_job_id": os.environ.get("PBS_JOBID"),
        "checker_hostname": socket.gethostname(),
        "persistence_commit": os.environ.get("EXPECTED_COMMIT"),
        "verified_runtime_implementation": runtime_commit,
        "verified_evidence_commit": comparison["git_commit"],
        "acceptance_id_count": 23,
        "novel_counterexample": _counterexample(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.root, args.artifact_root, args.manifest)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
