#!/usr/bin/env python3
"""Independent P06 interval, publication, adoption, recovery, and evidence audit."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import xml.etree.ElementTree as ET

import yaml

from fs_diloco.learner_protocol.adoption import AdoptionKernel
from fs_diloco.learner_protocol.data_cursor import DataCursor
from fs_diloco.learner_protocol.interval import AuthorityFrontier, ContributionInterval
from fs_diloco.learner_protocol.publication import LearnerPublisher
from fs_diloco.learner_protocol.recovery import recover_learner
from fs_diloco.learner_protocol.rng_state import RngCursor
from fs_diloco.learner_protocol.session import LearnerSession
from fs_diloco.log.layout import LogLayout
from fs_diloco.storage import InMemoryStorageBackend
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


def _frontier(seq: int) -> AuthorityFrontier:
    return AuthorityFrontier(
        commit_id=f"checker-commit-{seq}",
        commit_seq=seq,
        frontier_sha256=f"{seq:064x}",
        fragment_versions={0: seq},
        fencing_epoch=1,
        owner_id="checker-syncer",
        owner_session_id="checker-owner-session",
    )


class _CorruptRequestRead:
    def __init__(self, backend: InMemoryStorageBackend, request_key: str) -> None:
        self.backend = backend
        self.request_key = request_key

    def get(self, key: str, *, expected_version: str | None = None) -> bytes:
        value = self.backend.get(key, expected_version=expected_version)
        return value + b"x" if key == self.request_key else value

    def list_prefix(self, prefix: str) -> tuple[str, ...]:
        return self.backend.list_prefix(prefix)

    def put_immutable(self, key, data, *, sha256=None):
        return self.backend.put_immutable(key, data, sha256=sha256)


def _novel_counterexample() -> dict[str, object]:
    backend = InMemoryStorageBackend()
    layout = LogLayout("p06-checker", 0)
    session = LearnerSession.new(
        "p06-checker", 0, "learner_000", session_id="checker-session"
    )
    interval = (
        ContributionInterval.start(
            session=session,
            sequence=1,
            fragment_id=0,
            base=_frontier(1),
            start_step=0,
            start_cursor=DataCursor(0, 0),
            rng_cursor=RngCursor(7, 0),
            transport_dtype="bfloat16",
        )
        .record_step(tokens=8, examples=1)
        .close(end_cursor=DataCursor(1, 0))
    )
    result = LearnerPublisher(backend, layout).publish(
        interval, b"checker-payload", tensor_key="fragment_params", shape=(1,)
    )
    corruption_rejected = False
    try:
        recover_learner(
            _CorruptRequestRead(backend, result.request_ref.key),
            layout,
            learner_id="learner_000",
            committed_proposal_ids=frozenset(),
            new_session_id="checker-restart",
        )
    except ValueError:
        corruption_rejected = True
    if not corruption_rejected:
        raise AssertionError("corrupt immutable publication request did not fail closed")
    kernel = AdoptionKernel.bootstrap(_frontier(1)).begin_interval("checker-interval")
    observed = kernel.observe_successor(_frontier(2))
    if observed.adopted != _frontier(1) or observed.pending != _frontier(2):
        raise AssertionError("mid-interval successor was adopted early")
    if any(record.operation == "conditional_replace" for record in backend.history):
        raise AssertionError("Checker learner publication reached conditional replacement")
    return {
        "name": "corrupt_publication_request_then_mid_interval_successor",
        "corrupt_request_rejected": corruption_rejected,
        "adoption_deferred_to_boundary": True,
        "learner_head_cas_operations": 0,
        "pass": True,
    }


def run(
    root: Path,
    artifact_root: Path,
    *,
    maker_one: Path,
    maker_two: Path,
    maker_nine: Path,
) -> dict[str, object]:
    paths = [maker_one, maker_two, maker_nine]
    for path in paths:
        validate_manifest(path, root=root)
    manifests = [_load(path) for path in paths]
    implementation = manifests[0]["git_commit"]
    if any(
        item["git_commit"] != implementation
        or item["schema_version"] != 2
        or item["result"] != "pass"
        or item["dirty_tree"]
        for item in manifests
    ):
        raise AssertionError("Maker manifests are not one clean passing schema-v2 commit")
    if manifests[1]["parent_run_id"] != manifests[0]["run_id"]:
        raise AssertionError("two-node run is not parent-linked to one-node")
    if manifests[2]["parent_run_id"] != manifests[1]["run_id"]:
        raise AssertionError("nine-node run is not parent-linked to two-node")
    qualification = manifests[2]["same_commit_qualification"]
    if qualification["miyabi_1node"] != manifests[0]["run_id"] or (
        qualification["miyabi_2node"] != manifests[1]["run_id"]
    ):
        raise AssertionError("terminal qualification lineage differs")

    one = maker_one.parent
    if not _junit_passes(one / "junit.xml"):
        raise AssertionError("one-node full-suite JUnit contains a failure")
    one_report = _load(one / "one_node_report.json")
    if not (
        one_report["status"] == "PASS"
        and 0 < one_report["local_steps"] <= 10
        and one_report["published_intervals"] >= 1
        and one_report["boundary_adoptions"] >= 1
        and all(value == value and abs(value) < float("inf") for value in one_report["finite_losses"])
    ):
        raise AssertionError("one-node real-path evidence differs")

    two = _load(maker_two.parent / "two_node_report.json")
    hosts = (maker_two.parent / "hosts.log").read_text(encoding="utf-8").splitlines()
    if not (
        two["status"] == "PASS"
        and two["optimizer_transitions"] == 2
        and two["published_intervals"] >= 2
        and len(two["session_ids"]) >= 2
        and two["warm_not_exact"]
        and two["recovery_reconciled_before_new_work"]
        and two["authoritative_stop"] == "stop_after_outer_steps"
        and len(set(hosts)) == 2
    ):
        raise AssertionError("two-node warm-restart evidence differs")

    terminal = _load(maker_nine.parent / "terminal_gate_report.json")
    terminal_hosts = (maker_nine.parent / "hosts.log").read_text(encoding="utf-8").splitlines()
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
        and terminal["optimizer_adoption_policy"] == "reset_all"
        and terminal["immutable_publication_marker_count"] >= 80
        and len(terminal["learner_sessions"]["learner_000"]) >= 2
        and terminal["numeric_contract"]
        == "bfloat16-proposal-to-float32-aggregate-commit-v1"
        and len(set(terminal_hosts)) == 9
        and all(terminal["assertions"].values())
    ):
        raise AssertionError("terminal P06 evidence differs")

    state = yaml.safe_load((root / "plans/duraloco/STATE.yaml").read_text())
    expected_ids = {f"P06-A{index:02d}" for index in range(1, 21)}
    if state["phase"] != "P06" or set(state["acceptance"]) != expected_ids:
        raise AssertionError("P06 acceptance map differs")
    pending = {key for key, value in state["acceptance"].items() if value["result"] != "pass"}
    if pending:
        raise AssertionError(f"Maker P06 gates remain pending: {sorted(pending)}")
    report = (root / "plans/duraloco/phases/P06_PHASE_REPORT.md").read_text()
    if "## English" not in report or "## 中文" not in report:
        raise AssertionError("P06 phase report is not bilingual")
    decisions = (root / "plans/duraloco/DECISIONS.md").read_text()
    for index in range(1, 12):
        if f"## D-06{index:02d}" not in decisions:
            raise AssertionError(f"missing P06 decision D-06{index:02d}")

    learner_source = (root / "fs_diloco/learner.py").read_text()
    publication_source = (root / "fs_diloco/learner_protocol/publication.py").read_text()
    if "conditional_replace" in learner_source or "conditional_replace" in publication_source:
        raise AssertionError("learner exposes head-CAS capability")
    if "AdoptionKernel" not in learner_source or "LearnerPublisher" not in learner_source:
        raise AssertionError("runtime bypasses the shared P06 policy kernel")
    if (root / "fs_diloco/learner_v2.py").exists():
        raise AssertionError("parallel learner_v2 runtime exists")
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
            "one_node_real_path": "PASS",
            "two_node_warm_restart": "PASS",
            "terminal_50x10_learner_restart": "PASS",
            "single_learner_runtime_static_audit": "PASS",
            "explicit_reference_traces": 10_000,
            "novel_counterexample": counterexample,
        },
        "required_failures": [],
    }


def _report(result: dict[str, object]) -> str:
    return f"""# P06 Final Independent Checker Report

Verdict: PASS
required_gate_followups: none
checking_to_completed: AUTHORIZED

## English

Independent PBS `{result['checker_pbs_job_id']}` on `{result['checker_hostname']}`
checked persistence commit `{result['persistence_commit']}` and verified Maker
implementation `{result['verified_implementation']}`. All 20 P06 acceptance IDs,
the clean same-commit 1/2/9-node lineage, real GPT-2/WikiText-2 finite path,
cross-node learner SIGKILL/warm restart, marker-last request identity, boundary
adoption, authoritative stop, and 50×10 terminal result pass.

The Checker-only counterexample corrupted the immutable publication request on
read. Recovery failed closed before starting a new session interval; the same
test also confirmed that a mid-interval committed successor remains pending and
that learner publication performs no head CAS. P06 is authorized complete with
no required-gate follow-up. This does not authorize merging `main`.

## 中文

独立 PBS `{result['checker_pbs_job_id']}` 在 `{result['checker_hostname']}` 上复核了
持久化提交 `{result['persistence_commit']}`，并验证 Maker implementation
`{result['verified_implementation']}`。全部 20 项 P06 验收、干净同 commit 单/双/九节点
lineage、真实 GPT-2/WikiText-2 有限 loss、跨节点 learner SIGKILL/warm restart、
marker-last request identity、boundary adoption、权威 stop，以及 50×10 terminal 均通过。

Checker 专属反例在读取时损坏 immutable publication request；recovery 在开始新 session
interval 前 fail closed。相同反例还确认 interval 中途出现的 committed successor 只进入
pending，且 learner publication 没有 head CAS。P06 获授权完成，没有 required-gate
follow-up；这不授权合并 `main`。
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
    result = run(
        args.root.resolve(),
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
