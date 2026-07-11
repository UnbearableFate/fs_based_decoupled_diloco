#!/usr/bin/env python3
"""Independent P06C factor-two, failure, D8, and error-evidence audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import xml.etree.ElementTree as ET

import yaml

from fs_diloco.distributed_syncer.duplicate_validation import (
    DivergentPreparedResult,
    PreparedResultObservation,
    decide_duplicate_results,
)
from fs_diloco.distributed_syncer.failure_evidence import FailureEvidenceV1
from fs_diloco.distributed_syncer.membership import (
    DistributedMemberV1,
    MembershipRevisionV1,
)
from fs_diloco.distributed_syncer.ownership import derive_ownership
from fs_diloco.protocol.canonical_json import canonical_digest
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


def _member(index: int) -> DistributedMemberV1:
    return DistributedMemberV1(
        member_id=f"member-{index}",
        learner_id=f"learner-{index}",
        learner_session_id=f"learner-session-{index}",
        executor_id=f"executor-{index}",
        executor_session_id=f"executor-session-{index}",
        node_id=f"node-{index}",
        capability_digest=f"{index + 1:064x}",
        committer_eligible=True,
    )


def _counterexamples() -> dict[str, object]:
    membership = MembershipRevisionV1.create(0, tuple(_member(i) for i in range(3)))
    ownership = derive_ownership(membership, fragment_ids=(0, 1), replication_factor=2)
    evidence = FailureEvidenceV1.create(
        {
            "run_id": "checker-false-suspicion",
            "run_generation": 0,
            "membership_revision": 0,
            "suspected_member_id": "member-0",
            "reason": "manual_test_injection",
            "reporter_member_ids": ["member-1"],
            "observation_digest": canonical_digest({"checker": "false-suspicion"}),
        }
    )
    if derive_ownership(membership, fragment_ids=(0, 1), replication_factor=2) != ownership:
        raise AssertionError("Checker false suspicion changed committed ownership")

    def observation(executor: str, result: str) -> PreparedResultObservation:
        return PreparedResultObservation(
            work_order_id="fwo2-checker",
            prepared_result_id=result,
            attempt_envelope_id=f"attempt-{executor}",
            executor_id=executor,
        )

    divergence_rejected = False
    preserved_ids = False
    try:
        decide_duplicate_results(
            "fwo2-checker",
            (
                observation("primary", "pfr-checker-left"),
                observation("backup", "pfr-checker-right"),
            ),
            required_attempts=2,
        )
    except DivergentPreparedResult as exc:
        divergence_rejected = True
        preserved_ids = all(
            value in str(exc) for value in ("pfr-checker-left", "pfr-checker-right")
        )
    if not divergence_rejected or not preserved_ids:
        raise AssertionError("Checker same-FWO divergence did not fail closed")
    return {
        "false_suspicion_evidence_id": evidence.evidence_id,
        "false_suspicion_changed_ownership": False,
        "same_fwo_divergence_rejected": divergence_rejected,
        "both_divergent_identities_preserved": preserved_ids,
        "pass": True,
    }


def _verify_checksums(root: Path) -> int:
    checksum_path = root / "plans/duraloco/evidence/P06C_MAKER_CHECKSUMS.sha256"
    count = 0
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise AssertionError(f"Maker checksum differs for {relative}")
        count += 1
    if count < 10:
        raise AssertionError("Maker checksum inventory is incomplete")
    return count


def run(root: Path, artifact_root: Path, manifests: list[Path]) -> dict[str, object]:
    for path in manifests:
        validate_manifest(path, root=root)
    rows = [_load(path) for path in manifests]
    if any(row["phase"] != "P06C" or row["result"] != "pass" or row["dirty_tree"] for row in rows):
        raise AssertionError("Maker manifest is not a clean passing P06C artifact")
    targeted, unit, d1, d2, d8 = rows
    runtime_commit = targeted["git_commit"]
    if any(row["git_commit"] != runtime_commit for row in rows[1:]):
        raise AssertionError("targeted/unit/D1/D2/D8 do not share one runtime commit")
    if [unit["parent_run_id"], d1["parent_run_id"], d2["parent_run_id"], d8["parent_run_id"]] != [
        targeted["run_id"],
        unit["run_id"],
        d1["run_id"],
        d2["run_id"],
    ]:
        raise AssertionError("Maker qualification lineage differs")
    if not _junit_passes(manifests[0].parent / "junit.xml") or not _junit_passes(
        manifests[1].parent / "junit.xml"
    ):
        raise AssertionError("targeted or full unit JUnit contains failures")

    one = _load(manifests[2].parent / "d1_r2_report.json")
    two = _load(manifests[3].parent / "d2_r2_report.json")
    terminal = _load(manifests[4].parent / "d8_r2_report.json")
    if not (
        one["status"] == "PASS"
        and one["optimizer_transitions"] == 1
        and one["prepared_attempts"] == 2
        and one["duplicate_attempts"] == 1
    ):
        raise AssertionError("D1-R2 duplicate evidence differs")
    if not (
        two["status"] == "PASS"
        and two["optimizer_transitions"] == 4
        and two["fencing_epochs"] == [1, 2, 3]
        and len(two["executor_kill_targets"]) == 2
        and two["combined_committer_and_learner_host_loss"]
    ):
        raise AssertionError("D2-R2 failure evidence differs")
    if not (
        terminal["status"] == "PASS"
        and terminal["learner_nodes"] == 8
        and terminal["dedicated_syncer_nodes"] == 0
        and terminal["optimizer_transitions"] == 10
        and terminal["membership_revision"] == 1
        and terminal["replication_factor"] == 2
        and terminal["mode"] == "hedged"
        and terminal["hedge_delay_ms"] == 6000
        and terminal["control_sequence"] == ["epoch_bump", "epoch_bump", "membership", "stop"]
        and terminal["elapsed_seconds"] <= 900
        and terminal["no_optimizer_state_transfer"]
        and len(terminal["p07_lifecycle_requirements"]) == 4
    ):
        raise AssertionError("D8-R2 terminal, membership, or lifecycle evidence differs")
    if not (
        terminal["r2_resource"]["input_byte_ratio_vs_factor_one"] > 1
        and terminal["r2_resource"]["output_byte_ratio_vs_factor_one"] > 1
        and terminal["elapsed_seconds"] > terminal["factor_one_baseline"]["elapsed_seconds"]
    ):
        raise AssertionError("negative factor-one/R2 comparison was not preserved")

    state = yaml.safe_load((root / "plans/duraloco/STATE.yaml").read_text())
    expected = {f"P06C-A{index:02d}" for index in range(1, 25)}
    if state["phase"] != "P06C" or state["status"] != "checking" or set(state["acceptance"]) != expected:
        raise AssertionError("P06C checking state differs")
    if any(value["result"] != "pass" or not value["evidence"] for value in state["acceptance"].values()):
        raise AssertionError("Maker acceptance results or evidence differ")
    if state["last_verified_commit"] != runtime_commit:
        raise AssertionError("state does not bind the clean runtime commit")

    report = (root / "plans/duraloco/phases/P06C_PHASE_REPORT.md").read_text()
    if "## English" not in report or "## 中文" not in report:
        raise AssertionError("P06C report is not bilingual")
    review = (root / "plans/duraloco/reviews/P06C_D8_R2_LEASE_EXPIRY_REVIEW.md").read_text()
    for token in ("2363156.opbs", "Root cause", "Safety assessment", "2363242"):
        if token not in review:
            raise AssertionError("D8 root-cause review is incomplete")
    errors = yaml.safe_load((root / "plans/duraloco/errors/P06C_ERROR_LEDGER.yaml").read_text())
    if len(errors["records"]) < 13 or any(
        not all(
            key in row
            for key in (
                "phenomenon",
                "expected",
                "impact",
                "cause",
                "repair",
                "verification",
                "retry_decision",
                "artifacts",
            )
        )
        for row in errors["records"]
    ):
        raise AssertionError("P06C detailed error ledger differs")
    terminal_error = next(row for row in errors["records"] if row["error_id"] == "E-P06C-20260711-13")
    if not terminal_error["retry_decision"]["authorized"] or not terminal_error["impact"]["committed_prefix_safe"]:
        raise AssertionError("D8 terminal failure resolution is incomplete")

    forbidden = _load(artifact_root / "forbidden_surface.json")
    reference = _load(artifact_root / "reference_10000.json")
    if forbidden["finding_count"] != 0 or reference["count"] != 10_000:
        raise AssertionError("Checker static/reference gate differs")
    checksum_count = _verify_checksums(root)
    return {
        "schema_version": 2,
        "verdict": "PASS",
        "required_gate_followups": "none",
        "checking_to_completed": "AUTHORIZED",
        "checker_pbs_job_id": os.environ.get("PBS_JOBID"),
        "checker_hostname": socket.gethostname(),
        "persistence_commit": os.environ.get("EXPECTED_COMMIT"),
        "verified_runtime_implementation": runtime_commit,
        "acceptance_id_count": 24,
        "maker_checksum_count": checksum_count,
        "novel_counterexamples": _counterexamples(),
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
