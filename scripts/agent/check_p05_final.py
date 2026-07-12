#!/usr/bin/env python3
"""Independent P05 evidence, authority, timing, and counterexample audit."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import socket
import xml.etree.ElementTree as ET

import yaml

from fs_diloco.coordination import (
    CoordinationConflict,
    LeaseManager,
    LeaseMutation,
)
from fs_diloco.log import CommitConflict, ProductionTransactionalLog
from fs_diloco.runtime_view import build_runtime_view
from tests.coordination.test_production_fencing import _initialize

from scripts.agent.check_run_manifest import validate as validate_manifest


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _lease_corruption_counterexample() -> dict[str, object]:
    """A corrupted lease must fail closed without becoming commit authority."""

    backend, active = _initialize("p05-checker-corrupt-lease")
    manager = LeaseManager(backend, active.layout, max_clock_skew_ns=5)
    lease_a = manager.acquire(
        LeaseMutation(
            operation="acquire",
            request_id="checker-lease-a",
            owner_id="checker-a",
            owner_session_id="checker-session-a",
            observed_fencing_epoch=0,
            requested_at_utc_ns=100,
            ttl_ns=50,
        )
    )
    active.activate_owner(token=lease_a.record.owner_token, request_id="checker-fence-a")
    before = build_runtime_view(active, force_full=True)

    stored = backend._objects[active.layout.lease_key]
    backend._objects[active.layout.lease_key] = replace(stored, data=b"not-canonical-json")
    rejected = False
    try:
        manager.load()
    except CoordinationConflict:
        rejected = True
    after_rejection = build_runtime_view(active, force_full=True)
    backend._objects[active.layout.lease_key] = stored
    if not rejected or after_rejection != before:
        raise AssertionError("corrupt lease changed authority or did not fail closed")

    lease_b = manager.acquire(
        LeaseMutation(
            operation="acquire",
            request_id="checker-lease-b",
            owner_id="checker-b",
            owner_session_id="checker-session-b",
            observed_fencing_epoch=before.fencing_epoch,
            requested_at_utc_ns=155,
            ttl_ns=50,
        )
    )
    standby = ProductionTransactionalLog.open(backend, active.spec.run_id, 0)
    standby.activate_owner(token=lease_b.record.owner_token, request_id="checker-fence-b")
    stale_rejected = False
    try:
        active.commit_stop(reason="stale", request_id="checker-stale-stop")
    except CommitConflict:
        stale_rejected = True
    standby.commit_stop(reason="checker-complete", request_id="checker-stop-b")
    final = build_runtime_view(standby, force_full=True)
    if (
        not stale_rejected
        or final.fencing_epoch != 2
        or final.owner_id != "checker-b"
        or final.authoritative_stop is None
    ):
        raise AssertionError("recovered lease takeover did not preserve fencing")
    return {
        "name": "corrupt_observational_lease_then_recover_and_take_over",
        "corruption_rejected": rejected,
        "authority_unchanged_after_rejection": after_rejection == before,
        "stale_owner_stop_rejected": stale_rejected,
        "final_fencing_epoch": final.fencing_epoch,
        "final_owner_id": final.owner_id,
        "pass": True,
    }


def _junit_passes(path: Path) -> bool:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    return not any(
        int(suite.attrib.get("failures", 0)) or int(suite.attrib.get("errors", 0))
        for suite in suites
    )


def run(
    root: Path,
    artifact_root: Path,
    *,
    maker_one: Path,
    maker_two: Path,
    maker_nine: Path,
) -> dict[str, object]:
    maker_paths = [maker_one, maker_two, maker_nine]
    for path in maker_paths:
        validate_manifest(path, root=root)
    manifests = [_load(path) for path in maker_paths]
    implementation = manifests[0]["git_commit"]
    if any(
        manifest["git_commit"] != implementation
        or manifest["result"] != "pass"
        or manifest["schema_version"] != 2
        or manifest["dirty_tree"]
        for manifest in manifests
    ):
        raise AssertionError("Maker 1/2/9 manifests are not one clean schema-v2 commit")
    if manifests[1]["parent_run_id"] != manifests[0]["run_id"]:
        raise AssertionError("two-node Maker manifest is not parent-linked to one-node")
    if manifests[2]["parent_run_id"] != manifests[1]["run_id"]:
        raise AssertionError("terminal Maker manifest is not parent-linked to two-node")
    qualifications = manifests[2]["same_commit_qualification"]
    if (
        qualifications["miyabi_1node"] != manifests[0]["run_id"]
        or qualifications["miyabi_2node"] != manifests[1]["run_id"]
    ):
        raise AssertionError("terminal same-commit qualifications differ")

    one_root = maker_one.parent
    if not _junit_passes(one_root / "junit.xml"):
        raise AssertionError("one-node Maker JUnit contains failures")
    before_after = [
        (
            _load(one_root / f"{manifests[0]['run_id']}-{kind}_before_recovery.json"),
            _load(one_root / f"{manifests[0]['run_id']}-{kind}_after_recovery.json"),
        )
        for kind in ("full", "fragment")
    ]
    expected_counts = (2, 4)
    for (before, after), expected in zip(before_after, expected_counts, strict=True):
        if (
            before["committed_state_digest"] != after["committed_state_digest"]
            or before["optimizer_transition_count"] != expected
            or after["optimizer_transition_count"] != expected
            or before["stop_reason"] != "stop_after_outer_steps"
        ):
            raise AssertionError("one-node derived-state recovery evidence differs")

    ranks = [_load(maker_two.parent / "ranks" / f"rank_{rank}.json") for rank in (0, 1)]
    if not (
        len({item["hostname"] for item in ranks}) == 2
        and len({item["committed_state_digest"] for item in ranks}) == 1
        and len({item["view_digest"] for item in ranks}) == 1
        and all(item["status"] == "PASS" for item in ranks)
        and all(item["fencing_epoch"] == 2 for item in ranks)
        and all(item["optimizer_transition_count"] == 1 for item in ranks)
        and all(item["split_brain_commits"] == 0 for item in ranks)
        and all(item["double_inclusions"] == 0 for item in ranks)
    ):
        raise AssertionError("two-node failover rank evidence differs")

    terminal = _load(maker_nine.parent / "terminal_gate_report.json")
    hosts = (maker_nine.parent / "hosts.log").read_text(encoding="utf-8").splitlines()
    if not (
        terminal["status"] == "PASS"
        and terminal["model"] == "gpt2"
        and terminal["dataset"] == "wikitext-2-raw-v1"
        and terminal["learners"] == 8
        and terminal["inner_steps"] == 50
        and terminal["optimizer_transition_count"] == 10
        and terminal["control_transition_count"] == 3
        and terminal["final_fencing_epoch"] == 2
        and terminal["final_owner_id"] == "terminal-standby"
        and terminal["checkpoint_count"] == 11
        and terminal["nonfinite_or_invalid_loss_count"] == 0
        and terminal["split_brain_commits"] == 0
        and terminal["double_inclusions"] == 0
        and terminal["takeover_seconds"] <= 75.0
        and len(set(hosts)) == 9
        and all(terminal["assertions"].values())
    ):
        raise AssertionError("terminal P05 evidence differs")

    state = yaml.safe_load((root / "plans/duraloco/STATE.yaml").read_text())
    expected_ids = {f"P05-A{index:02d}" for index in range(1, 21)}
    if state["phase"] != "P05" or set(state["acceptance"]) != expected_ids:
        raise AssertionError("P05 state acceptance map differs")
    pending = {
        key for key, value in state["acceptance"].items() if value["result"] != "pass"
    }
    if pending - {"P05-A09", "P05-A13"}:
        raise AssertionError(f"non-Checker P05 gates remain pending: {sorted(pending)}")

    report = (root / "plans/duraloco/phases/P05_PHASE_REPORT.md").read_text()
    timing = (root / "plans/duraloco/reviews/P05_COORDINATION_TIMING_AND_SAFETY_REVIEW.md").read_text()
    decisions = (root / "plans/duraloco/DECISIONS.md").read_text()
    m00_report = (root / "plans/duraloco/phases/M00_PHASE_REPORT.md").read_text()
    if "## English" not in report or "## 中文" not in report:
        raise AssertionError("P05 report is not bilingual")
    if "## English" not in timing or "## 中文" not in timing:
        raise AssertionError("P05 timing review is not bilingual")
    for decision in ("D-0501", "D-0511", "D-M0010", "D-M0011", "D-M0012"):
        if f"## {decision}" not in decisions:
            raise AssertionError(f"missing decision section: {decision}")
    for observed in ("6.177", "6.875", "4.835", "4.940"):
        if observed not in timing or observed not in m00_report:
            raise AssertionError(f"M00 timing attribution is missing: {observed}")

    learner_source = (root / "fs_diloco/learner.py").read_text()
    syncer_source = (root / "fs_diloco/syncer.py").read_text()
    commit_source = (root / "fs_diloco/log/commit.py").read_text()
    production_source = (root / "fs_diloco/log/production.py").read_text()
    if "conditional_replace(" in learner_source:
        raise AssertionError("learner exposes a conditional mutation surface")
    if "conditional_replace(" in syncer_source:
        raise AssertionError("syncer bypasses the audited transactional API")
    if commit_source.count("self.backend.conditional_replace(") != 1:
        raise AssertionError("transaction commit path is not exactly one head CAS")
    if "self.backend.conditional_replace(" in production_source:
        raise AssertionError("production adapter bypasses TransactionalLog head CAS")

    reference = _load(artifact_root / "reference_10000.json")
    if reference["count"] != 10_000 or reference["unique_state_digests"] < 100:
        raise AssertionError("Checker reference trace evidence differs")
    counterexample = _lease_corruption_counterexample()
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
            "maker_lineage": [manifest["run_id"] for manifest in manifests],
            "one_node_recovery": "PASS",
            "two_node_failover": "PASS",
            "terminal_50x10_active_standby": "PASS",
            "single_head_cas_static_audit": "PASS",
            "clock_safety_review": "PASS",
            "m00_decision_attribution": {
                "D-M0010": "M00 strict/memoized replay and corrupt-successor evidence",
                "D-M0011": "M00 marker-last publication and committed-successor backpressure evidence",
                "D-M0012": "M00 stage timing and terminal retry evidence",
            },
            "explicit_reference_traces": 10_000,
            "novel_counterexample": counterexample,
        },
        "required_failures": [],
    }


def _report(result: dict[str, object]) -> str:
    return f"""# P05 Final Independent Checker Report

Verdict: PASS
required_gate_followups: none
P05-A09: PASS
P05-A13: PASS
checking_to_completed: AUTHORIZED

## English

Independent PBS `{result['checker_pbs_job_id']}` on `{result['checker_hostname']}`
checked persistence commit `{result['persistence_commit']}` and verified Maker
implementation `{result['verified_implementation']}`. The complete 20-ID P05
map, clean schema-v2 1/2/9-node lineage, derived-state reconstruction, real
two-node old-owner rejection, terminal GPT-2/WikiText-2 50×10 active/standby
takeover, single-head-CAS audit, clock-safety boundary, 10,000 reference traces,
and D-M0010–D-M0012 evidence attribution pass.

The Checker-only counterexample corrupted the observational lease after epoch 1.
Lease parsing failed closed without changing committed authority; after restoring
the lease bytes, epoch 2 takeover succeeded and the old owner's stop mutation was
rejected. P05-A01 through P05-A20 are authorized complete with no required-gate
follow-up. This does not authorize merging `main`.

## 中文

独立 PBS `{result['checker_pbs_job_id']}` 在 `{result['checker_hostname']}` 上复核了
持久化提交 `{result['persistence_commit']}`，并验证 Maker implementation
`{result['verified_implementation']}`。完整 20 项 P05 映射、干净 schema-v2
单/双/九节点 lineage、派生状态重建、真实双节点旧 owner 拒绝、GPT-2/WikiText-2
50×10 active/standby terminal takeover、唯一 head-CAS 审计、时钟安全边界、
10,000 条参考 trace，以及 D-M0010–D-M0012 证据归属均通过。

Checker 专属反例在 epoch 1 后损坏观测性 lease。lease 解析 fail closed，且 committed
authority 不变；恢复 lease bytes 后 epoch 2 takeover 成功，旧 owner 的 stop mutation
被拒。Checker 授权 P05-A01 至 P05-A20 全部完成，且没有 required-gate follow-up；
这不授权合并 `main`。
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--maker-one", type=Path, required=True)
    parser.add_argument("--maker-two", type=Path, required=True)
    parser.add_argument("--maker-nine", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    result = run(
        root,
        args.artifact_root.resolve(),
        maker_one=args.maker_one.resolve(),
        maker_two=args.maker_two.resolve(),
        maker_nine=args.maker_nine.resolve(),
    )
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    args.report.write_text(_report(result), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
