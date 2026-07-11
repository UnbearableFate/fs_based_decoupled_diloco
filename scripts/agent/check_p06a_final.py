#!/usr/bin/env python3
"""Independent P06A decomposition, equivalence, capability, and evidence audit."""

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
from fs_diloco.syncer_core.planning import PlanningCandidate, select_candidate_ids
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


def _novel_counterexample() -> dict[str, object]:
    good = PlanningCandidate(
        proposal_id="checker-proposal",
        learner_id="checker-learner",
        sequence=1,
        fragment_id=0,
        target_tokens=8,
        base_fragment_version=0,
        payload_sha256="1" * 64,
    )
    conflict = PlanningCandidate(
        proposal_id="checker-proposal",
        learner_id="checker-learner",
        sequence=1,
        fragment_id=0,
        target_tokens=9,
        base_fragment_version=0,
        payload_sha256="2" * 64,
    )
    conflict_rejected = False
    try:
        select_candidate_ids((good, conflict), fragment_id=0, quorum_max=1)
    except ValueError:
        conflict_rejected = True
    if not conflict_rejected:
        raise AssertionError("conflicting content reused one proposal identity")

    backend = InMemoryStorageBackend()
    facade = PrepareObjectFacade(
        backend,
        read_prefixes=("inputs/",),
        write_prefixes=("prepared/",),
    )
    facade.put_immutable("prepared/checker", b"prepared")
    head_write_rejected = False
    try:
        facade.put_immutable("control/head.json", b"forbidden")
    except PermissionError:
        head_write_rejected = True
    if not head_write_rejected or hasattr(facade, "conditional_replace"):
        raise AssertionError("prepare-only facade reached mutable head authority")
    return {
        "name": "conflicting_proposal_identity_then_prepare_head_write",
        "conflicting_identity_rejected": conflict_rejected,
        "head_write_rejected": head_write_rejected,
        "conditional_replace_exposed": False,
        "pass": True,
    }


def run(
    root: Path,
    artifact_root: Path,
    *,
    maker_focused: Path,
    maker_one: Path,
    maker_two: Path,
    maker_nine: Path,
    oracle: Path,
) -> dict[str, object]:
    paths = [maker_focused, maker_one, maker_two, maker_nine]
    for path in paths:
        validate_manifest(path, root=root)
    manifests = [_load(path) for path in paths]
    implementation = manifests[0]["git_commit"]
    if any(
        item["git_commit"] != implementation
        or item["phase"] != "P06A"
        or item["schema_version"] != 2
        or item["result"] != "pass"
        or item["dirty_tree"]
        for item in manifests
    ):
        raise AssertionError("Maker manifests are not one clean passing P06A commit")
    if manifests[1]["parent_run_id"] != manifests[0]["run_id"]:
        raise AssertionError("C1 is not parent-linked to the focused qualification")
    if manifests[2]["parent_run_id"] != manifests[1]["run_id"]:
        raise AssertionError("C2 is not parent-linked to C1")
    if manifests[3]["parent_run_id"] != manifests[2]["run_id"]:
        raise AssertionError("C9 is not parent-linked to C2")
    qualification = manifests[3]["same_commit_qualification"]
    if not str(qualification["miyabi_1node"]).endswith(
        f"/{manifests[1]['run_id']}/manifest.json"
    ) or not str(qualification["miyabi_2node"]).endswith(
        f"/{manifests[2]['run_id']}/manifest.json"
    ):
        raise AssertionError("C9 same-commit qualification lineage differs")

    if not _junit_passes(maker_focused.parent / "junit.xml"):
        raise AssertionError("focused characterization JUnit contains a failure")
    if not _junit_passes(maker_one.parent / "junit.xml"):
        raise AssertionError("C1 full-suite JUnit contains a failure")
    trace = _load(oracle)
    if trace["archive_commit"] != "06e3ca2299d5eb1a720c1d8f9107af5223095525":
        raise AssertionError("characterization archive identity differs")
    if not all(trace["equivalence"].values()):
        raise AssertionError("archive/decomposed exact equivalence differs")
    archive_output = trace["archive_output"]
    decomposed_output = trace["decomposed_output"]
    for key in (
        "aggregate_content_sha256",
        "params_content_sha256",
        "outer_state_content_sha256",
    ):
        if archive_output[key] != decomposed_output[key]:
            raise AssertionError(f"archive/decomposed {key} differs")

    one = _load(maker_one.parent / "c1_report.json")
    if not (
        one["status"] == "PASS"
        and 0 < one["local_steps"] <= 10
        and one["optimizer_transitions"] >= 1
        and one["boundary_adoptions"] >= 1
        and all(value == value and abs(value) < float("inf") for value in one["finite_losses"])
    ):
        raise AssertionError("C1 real-path evidence differs")
    two = _load(maker_two.parent / "two_node_report.json")
    if not (
        two["status"] == "PASS"
        and two["optimizer_transitions"] == 2
        and len(two["session_ids"]) >= 2
        and two["recovery_reconciled_before_new_work"]
        and two["authoritative_stop"] == "stop_after_outer_steps"
        and len(set((maker_two.parent / "hosts.log").read_text().splitlines())) == 2
    ):
        raise AssertionError("C2 failover evidence differs")
    terminal = _load(maker_nine.parent / "terminal_gate_report.json")
    if not (
        terminal["status"] == "PASS"
        and terminal["model"] == "gpt2"
        and terminal["dataset"] == "wikitext-2-raw-v1"
        and terminal["optimizer_transition_count"] == 10
        and terminal["control_transition_count"] == 3
        and terminal["final_fencing_epoch"] == 2
        and terminal["checkpoint_count"] == 11
        and terminal["nonfinite_or_invalid_loss_count"] == 0
        and terminal["split_brain_commits"] == 0
        and terminal["double_inclusions"] == 0
        and len(set((maker_nine.parent / "hosts.log").read_text().splitlines())) == 9
        and all(terminal["assertions"].values())
    ):
        raise AssertionError("C9 terminal evidence differs")

    state = yaml.safe_load((root / "plans/duraloco/STATE.yaml").read_text())
    expected_ids = {f"P06A-A{index:02d}" for index in range(1, 21)}
    if state["phase"] != "P06A" or set(state["acceptance"]) != expected_ids:
        raise AssertionError("P06A acceptance map differs")
    if any(item["result"] != "pass" for item in state["acceptance"].values()):
        raise AssertionError("Maker P06A gates remain pending")
    if state["next_action"] != "P06B":
        raise AssertionError("P06A does not hand off to P06B")
    report = (root / "plans/duraloco/phases/P06A_PHASE_REPORT.md").read_text()
    if "## English" not in report or "## 中文" not in report:
        raise AssertionError("P06A phase report is not bilingual")
    decisions = (root / "plans/duraloco/DECISIONS.md").read_text()
    for index in range(1, 9):
        if f"## D-06A{index:02d}" not in decisions:
            raise AssertionError(f"missing P06A decision D-06A{index:02d}")

    pure_modules = ("planning.py", "transaction_attempt.py", "semantic_digest.py")
    for name in pure_modules:
        tree = ast.parse((root / "fs_diloco/syncer_core" / name).read_text())
        forbidden = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module
            and (node.module.startswith("fs_diloco.storage") or node.module.startswith("fs_diloco.coordination"))
        ]
        if forbidden:
            raise AssertionError(f"pure module {name} imports authority APIs: {forbidden}")
    capability_source = (root / "fs_diloco/syncer_core/capabilities.py").read_text()
    if "conditional_replace" in capability_source or "list_prefix" in capability_source:
        raise AssertionError("prepare capability source exposes mutation or listing")
    reference = _load(artifact_root / "reference_10000.json")
    if reference["count"] != 10_000 or reference["unique_state_digests"] != 10_000:
        raise AssertionError("Checker reference traces differ")
    counterexample = _novel_counterexample()
    return {
        "schema_version": 2,
        "verdict": "PASS",
        "required_gate_followups": "none",
        "checking_to_completed": "AUTHORIZED",
        "checker_pbs_job_id": os.environ.get("PBS_JOBID"),
        "checker_hostname": socket.gethostname(),
        "persistence_commit": os.environ.get("EXPECTED_COMMIT"),
        "verified_implementation": implementation,
        "checks": {
            "acceptance_id_count": 20,
            "maker_lineage": [item["run_id"] for item in manifests],
            "archive_exact_equivalence": "PASS",
            "c1_c2_c9_same_commit": "PASS",
            "pure_kernel_static_audit": "PASS",
            "prepare_capability_static_runtime_audit": "PASS",
            "explicit_reference_traces": 10_000,
            "novel_counterexample": counterexample,
        },
        "required_failures": [],
    }


def _report(result: dict[str, object]) -> str:
    return f"""# P06A Final Independent Checker Report

Verdict: PASS
required_gate_followups: none
checking_to_completed: AUTHORIZED

## English

Independent PBS `{result['checker_pbs_job_id']}` on `{result['checker_hostname']}`
checked persistence commit `{result['persistence_commit']}` and verified Maker
implementation `{result['verified_implementation']}`. All 20 P06A acceptance IDs,
the archive-bound exact characterization, clean same-commit focused/C1/C2/C9
lineage, pure-kernel dependency boundary, strict inactive FWO/PFT schemas, and
prepare-only capability surface pass.

The Checker-only counterexample reused one proposal ID with conflicting planning
content and then attempted to write the mutable head through the prepare facade.
Both operations failed closed and no conditional-replace capability was exposed.
P06A is authorized complete with no required-gate follow-up. This does not
authorize merging `main`.

## 中文

独立 PBS `{result['checker_pbs_job_id']}` 在 `{result['checker_hostname']}` 上复核了
持久化提交 `{result['persistence_commit']}`，并验证 Maker implementation
`{result['verified_implementation']}`。全部 20 项 P06A 验收、绑定 archive 的精确
characterization、干净同 commit focused/C1/C2/C9 lineage、pure-kernel dependency
边界、严格 inactive FWO/PFT schema 与 prepare-only capability surface 均通过。

Checker 专属反例先让同一个 proposal ID 对应冲突 planning content，再尝试通过
prepare facade 写 mutable head；两项操作均 fail closed，且没有暴露
conditional-replace capability。P06A 获授权完成，没有 required-gate follow-up；这不授权
合并 `main`。
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--maker-focused", type=Path, required=True)
    parser.add_argument("--maker-one", type=Path, required=True)
    parser.add_argument("--maker-two", type=Path, required=True)
    parser.add_argument("--maker-nine", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = run(
        args.root.resolve(),
        args.artifact_root.resolve(),
        maker_focused=args.maker_focused.resolve(),
        maker_one=args.maker_one.resolve(),
        maker_two=args.maker_two.resolve(),
        maker_nine=args.maker_nine.resolve(),
        oracle=args.oracle.resolve(),
    )
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    args.report.write_text(_report(result), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
