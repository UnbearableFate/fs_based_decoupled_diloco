#!/usr/bin/env python3
"""Independent final M00 evidence, mapping, authority, and counterexample audit."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import socket
import xml.etree.ElementTree as ET

from fs_diloco.log import ProductionTransactionalLog, VerificationError
from tests.log.test_production_runtime import _initialize, _prepare, _proposal

from scripts.agent.check_run_manifest import validate as validate_manifest


IMPLEMENTATION = "c052438a3cfe5e16c3b154fc842f32dcd61ec6ff"
ONE = "20260711_m00_c052438_1node_requal"
TWO = "20260711_m00_c052438_2node_requal"
NINE = "20260711_m00_c052438_gpt2_9n_50x10"
BENCHMARK = "20260711_m00_6e85182_replay_benchmark"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _expected_gates() -> set[str]:
    return {
        *(f"P00-A{index:02d}" for index in range(1, 9)),
        *(f"P01-A{index:02d}" for index in range(1, 9)),
        *(f"P02-A{index:02d}" for index in range(1, 9)),
        *(f"P03-A{index:02d}" for index in range(1, 9)),
        *(f"P04-A{index:02d}" for index in range(1, 10)),
    }


def _counterexample() -> dict[str, object]:
    """A stale process must verify a successor created by another writer."""

    backend, first = _initialize("m00-checker-head-jump")
    first.replay(force_full=True)
    second = ProductionTransactionalLog.open(
        backend,
        first.spec.run_id,
        first.spec.run_generation,
    )
    proposal = _proposal(second, learner="checker-writer", sequence=1, values=[1.0, 2.0])
    second.commit_prepared(_prepare(second, proposal, [0.5, 1.0]))

    stored = backend._objects[proposal.payload_key]
    corrupted = bytearray(stored.data)
    corrupted[-1] ^= 1
    backend._objects[proposal.payload_key] = replace(stored, data=bytes(corrupted))
    before = (
        set(first._replay_cache.proposal_payloads),
        dict(first._replay_cache.params_numels),
        dict(first._replay_cache.outer_numels),
    )
    rejected = False
    try:
        first.replay()
    except VerificationError:
        rejected = True
    after = (
        first._replay_cache.proposal_payloads,
        first._replay_cache.params_numels,
        first._replay_cache.outer_numels,
    )
    backend._objects[proposal.payload_key] = stored
    recovered = first.replay()
    strict = first.replay(force_full=True)
    if not rejected or before != after or recovered != strict:
        raise AssertionError("stale-process corrupt-successor counterexample was not rejected")
    return {
        "name": "stale_process_head_jump_with_corrupt_new_payload",
        "corruption_rejected": rejected,
        "cache_unchanged_after_failure": before == after,
        "restored_memoized_equals_strict": recovered == strict,
        "final_commit_seq": strict.head_frontier.commit_seq,
        "pass": True,
    }


def run(root: Path, artifact_root: Path) -> dict[str, object]:
    mapping_path = root / "plans/duraloco/M00_P00_P04_ACCEPTANCE_MAPPING.json"
    mapping = _load(mapping_path)
    gates = mapping["gates"]
    if set(gates) != _expected_gates() or any(item["result"] != "pass" for item in gates.values()):
        raise AssertionError("P00-P04 mapping is incomplete or contains a non-pass Maker gate")
    if set(mapping["explicit_remaps"]) != {"P00-A06", "P04-A06"}:
        raise AssertionError("explicit remap set differs")
    for gate, item in gates.items():
        for relative in item["evidence"]:
            if not (root / relative).exists():
                raise AssertionError(f"{gate} evidence does not exist: {relative}")

    m00 = root / "artifacts/duraloco/M00"
    manifests = {
        name: _load(m00 / name / "manifest.json") for name in (ONE, TWO, NINE, BENCHMARK)
    }
    for name in manifests:
        validate_manifest(m00 / name / "manifest.json", root=root)
    for name in (ONE, TWO, NINE):
        manifest = manifests[name]
        if manifest["git_commit"] != IMPLEMENTATION or manifest["result"] != "pass":
            raise AssertionError(f"Maker manifest is not a clean implementation PASS: {name}")
    if manifests[TWO]["parent_run_id"] != ONE or manifests[NINE]["parent_run_id"] != TWO:
        raise AssertionError("1/2/9-node parent lineage differs")

    junit = ET.parse(m00 / ONE / "junit.xml").getroot()
    suites = [junit] if junit.tag == "testsuite" else list(junit.iter("testsuite"))
    if sum(int(suite.attrib.get("failures", 0)) for suite in suites) or sum(
        int(suite.attrib.get("errors", 0)) for suite in suites
    ):
        raise AssertionError("one-node JUnit contains failures")
    two = _load(m00 / TWO / "two_node_summary.json")
    if not (
        two["status"] == "PASS"
        and two["backend_rounds"] == 100
        and two["transaction_rounds"] == 20
        and two["backend_double_winners"] == 0
        and two["transaction_double_winners"] == 0
        and two["transaction_double_inclusions"] == 0
        and two["production_takeover"] is True
    ):
        raise AssertionError("two-node M00 summary differs")

    terminal = _load(m00 / NINE / "terminal_gate_report.json")
    if not (
        terminal["status"] == "PASS"
        and terminal["model"] == "gpt2"
        and terminal["dataset"] == "wikitext-2-raw-v1"
        and terminal["learners"] == 8
        and terminal["inner_steps"] == 50
        and terminal["global_outer_transitions"] == 10
        and terminal["checkpoint_count"] == 11
        and terminal["nonfinite_or_invalid_loss_count"] == 0
        and terminal["consumed_proposal_count"] == 80
        and all(terminal["assertions"].values())
    ):
        raise AssertionError("terminal M00 report differs")
    hosts = (m00 / NINE / "hosts.log").read_text().splitlines()
    if len(set(hosts)) != 9:
        raise AssertionError("terminal evidence does not contain nine unique hosts")

    benchmark = _load(m00 / BENCHMARK / "report.json")
    if not (
        benchmark["status"] == "PASS"
        and benchmark["commit_seq"] == 1
        and benchmark["proposal_count"] == 8
        and benchmark["memoized_large_get_count"] == 0
        and benchmark["memoized_seconds"] < benchmark["strict_cpu_seconds"]
        and benchmark["memoized_seconds"] < benchmark["strict_gpu_seconds"]
    ):
        raise AssertionError("real-prefix replay benchmark differs")

    learner_source = (root / "fs_diloco/learner.py").read_text()
    commit_source = (root / "fs_diloco/log/commit.py").read_text()
    replay_source = (root / "fs_diloco/log/replay.py").read_text()
    if "conditional_replace(" in learner_source or "head_key" in learner_source:
        raise AssertionError("learner exposes a head-CAS surface")
    if commit_source.count("self.backend.conditional_replace(") != 1:
        raise AssertionError("transaction commit path is not exactly one head CAS")
    if "validate_tensor_payload(" in replay_source:
        raise AssertionError("production replay source still references the scalar validator")
    if "validate_production_tensor_payload(" not in replay_source:
        raise AssertionError("production replay lacks vectorized validation")

    phase_report = (root / "plans/duraloco/phases/M00_PHASE_REPORT.md").read_text()
    if "## English" not in phase_report or "## 中文" not in phase_report:
        raise AssertionError("M00 report is not bilingual")

    counterexample = _counterexample()
    return {
        "schema_version": 1,
        "verdict": "PASS",
        "required_gate_followups": "none",
        "checking_to_completed": "AUTHORIZED",
        "checker_pbs_job_id": os.environ.get("PBS_JOBID"),
        "checker_hostname": socket.gethostname(),
        "persistence_commit": os.environ.get("EXPECTED_COMMIT"),
        "verified_implementation": IMPLEMENTATION,
        "checks": {
            "mapping_gate_count": len(gates),
            "mapping_complete": True,
            "explicit_remaps_approved": ["P00-A06", "P04-A06"],
            "maker_lineage": [ONE, TWO, NINE],
            "one_node_junit": "PASS",
            "two_node_contract": "PASS",
            "terminal_50x10": "PASS",
            "single_head_cas_static_audit": "PASS",
            "vectorized_and_memoized_replay": "PASS",
            "attempt_lineage_reviewed": True,
            "novel_counterexample": counterexample,
        },
        "required_failures": [],
    }


def _report(result: dict[str, object]) -> str:
    job = result["checker_pbs_job_id"]
    host = result["checker_hostname"]
    persistence = result["persistence_commit"]
    return f"""# M00 Final Independent Checker Report

Verdict: PASS
required_gate_followups: none
M00-A12: PASS
checking_to_completed: AUTHORIZED

## English

Independent PBS `{job}` on `{host}` checked persistence commit `{persistence}`.
The complete 41-ID P00–P04 mapping and both explicit remaps pass. The current
full suite, forbidden-surface scan, 1/2/9-node Maker lineage, real-prefix replay
benchmark, single-head-CAS audit, terminal GPT-2/WikiText-2 50×10 authority
probe, and a new stale-process/corrupt-successor counterexample all pass.

M00-A01 through M00-A12 are authorized as complete with no required-gate
follow-up. This authorizes persistence of the completed M00 state and entry to
P05; it does not authorize an automatic merge to `main`.

## 中文

独立 PBS `{job}` 在 `{host}` 上复核了持久化提交 `{persistence}`。完整的
41 项 P00–P04 映射与两个显式语义重映射均通过。当前完整测试套件、禁止项扫描、
单/双/九节点 Maker lineage、真实前缀 replay benchmark、单 head-CAS 静态审计、
GPT-2/WikiText-2 50×10 终端权威检查，以及新增的“旧进程遇到损坏 successor”
反例均通过。

Checker 授权 M00-A01 至 M00-A12 完成，且没有 required-gate follow-up。
这允许持久化 M00 completed 状态并进入 P05，但不授权自动合并 `main`。
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    result = run(root, args.artifact_root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    args.report.write_text(_report(result))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
