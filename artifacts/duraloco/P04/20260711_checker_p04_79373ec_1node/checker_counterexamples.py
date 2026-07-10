from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

from fs_diloco.log import (
    CommitConflict,
    InjectedLogCrash,
    TransactionalLog,
    VerificationError,
    load_cache,
    rebuild_cache,
    replay_log,
    verify_cache,
)
from fs_diloco.log.model import ReferenceProposal
from fs_diloco.log.run import RunSpec
from fs_diloco.storage import InMemoryStorageBackend, PosixStorageBackend


def digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def spec(run_id: str) -> RunSpec:
    return RunSpec(
        run_id=run_id,
        run_generation=0,
        model_revision="checker",
        parameter_index_digest=digest("params"),
        fragment_layout_digest=digest("layout"),
        outer_optimizer_schema_digest=digest("outer"),
    )


def initialize(backend, run_id: str) -> TransactionalLog:
    return TransactionalLog.initialize(
        backend,
        spec(run_id),
        {0: (0.0, 0.0), 1: (0.0, 0.0)},
    )


def proposal(
    log: TransactionalLog,
    *,
    learner: str,
    sequence: int = 1,
    fragment_id: int = 0,
    values: tuple[float, float] = (1.0, -1.0),
) -> ReferenceProposal:
    frontier = replay_log(log).head_frontier
    item = ReferenceProposal.create(
        learner_id=learner,
        session_id=f"session-{learner}",
        sequence=sequence,
        fragment_id=fragment_id,
        base_commit_id=frontier.commit_id,
        base_commit_seq=frontier.commit_seq,
        base_fragment_version=frontier.fragments[fragment_id].version,
        target_tokens=1000 + sequence,
        values=values,
    )
    log.publish_proposal(item)
    return item


class CountingBackend(InMemoryStorageBackend):
    def __init__(self) -> None:
        super().__init__()
        self.cas_calls: list[tuple[str, str, str | None]] = []

    def conditional_replace(
        self,
        key: str,
        *,
        expected_version: str,
        data,
        request_id: str | None = None,
    ):
        self.cas_calls.append((key, expected_version, request_id))
        return super().conditional_replace(
            key,
            expected_version=expected_version,
            data=data,
            request_id=request_id,
        )


def build(log: TransactionalLog, count: int) -> None:
    for index in range(1, count + 1):
        item = proposal(
            log,
            learner=f"build-{index}",
            sequence=index,
            fragment_id=(index - 1) % 2,
            values=(float(index), -float(index)),
        )
        log.commit_transition(
            fragment_id=item.fragment_id,
            selected_proposal_ids=(item.proposal_id,),
        )


def main() -> int:
    work = Path(sys.argv[1])
    output = Path(sys.argv[2])
    work.mkdir(parents=True, exist_ok=True)
    checks: dict[str, object] = {}
    failures: list[str] = []

    backend = CountingBackend()
    log = initialize(backend, "checker-delayed-response")
    first_item = proposal(log, learner="first")
    first = log.prepare_transition(
        fragment_id=0,
        selected_proposal_ids=(first_item.proposal_id,),
    )
    try:
        log.commit_prepared(first, crash_at="after_head_cas")
    except InjectedLogCrash:
        pass
    else:
        failures.append("after-head-CAS crash point did not fire")
    successor = proposal(log, learner="successor", fragment_id=1)
    log.commit_transition(
        fragment_id=1,
        selected_proposal_ids=(successor.proposal_id,),
    )
    before_retry_calls = len(backend.cas_calls)
    retried = log.commit_prepared(first)
    after_retry_calls = len(backend.cas_calls)
    replay = replay_log(log)
    delayed_ok = (
        retried.status == "already_committed"
        and replay.head_frontier.commit_seq == 2
        and len(replay.consumption) == 2
        and before_retry_calls == after_retry_calls == 2
        and all(call[0] == log.layout.head_key for call in backend.cas_calls)
    )
    checks["lost_response_retry_after_successor_progress"] = {
        "pass": delayed_ok,
        "status": retried.status,
        "head_seq": replay.head_frontier.commit_seq,
        "consumed": len(replay.consumption),
        "cas_calls_before_retry": before_retry_calls,
        "cas_calls_after_retry": after_retry_calls,
        "cas_keys": [call[0] for call in backend.cas_calls],
    }
    if not delayed_ok:
        failures.append("delayed response-loss retry was not ancestry-idempotent")

    duplicate_backend = CountingBackend()
    duplicate_log = initialize(duplicate_backend, "checker-identical-writers")
    duplicate_item = proposal(duplicate_log, learner="same")
    duplicate_a = duplicate_log.prepare_transition(
        fragment_id=0,
        selected_proposal_ids=(duplicate_item.proposal_id,),
    )
    duplicate_b = duplicate_log.prepare_transition(
        fragment_id=0,
        selected_proposal_ids=(duplicate_item.proposal_id,),
    )
    first_result = duplicate_log.commit_prepared(duplicate_a)
    second_result = duplicate_log.commit_prepared(duplicate_b)
    duplicate_replay = replay_log(duplicate_log)
    identical_ok = (
        first_result.status == "committed"
        and second_result.status == "already_committed"
        and len(duplicate_backend.cas_calls) == 1
        and duplicate_replay.head_frontier.commit_seq == 1
        and len(duplicate_replay.consumption) == 1
    )
    checks["identical_writers_are_one_logical_commit_and_one_cas"] = {
        "pass": identical_ok,
        "statuses": [first_result.status, second_result.status],
        "cas_calls": len(duplicate_backend.cas_calls),
        "head_seq": duplicate_replay.head_frontier.commit_seq,
        "consumed": len(duplicate_replay.consumption),
    }
    if not identical_ok:
        failures.append("identical writers produced more than one logical commit/CAS")

    conflict_backend = CountingBackend()
    conflict_log = initialize(conflict_backend, "checker-conflict-after-progress")
    left_item = proposal(conflict_log, learner="left")
    right_item = proposal(conflict_log, learner="right")
    left = conflict_log.prepare_transition(
        fragment_id=0,
        selected_proposal_ids=(left_item.proposal_id,),
    )
    right = conflict_log.prepare_transition(
        fragment_id=0,
        selected_proposal_ids=(right_item.proposal_id,),
    )
    conflict_log.commit_prepared(left)
    later_item = proposal(conflict_log, learner="later", fragment_id=1)
    conflict_log.commit_transition(
        fragment_id=1,
        selected_proposal_ids=(later_item.proposal_id,),
    )
    try:
        conflict_log.commit_prepared(right)
    except CommitConflict:
        right_rejected = True
    else:
        right_rejected = False
    conflict_replay = replay_log(conflict_log)
    conflict_ok = (
        right_rejected
        and conflict_replay.head_frontier.commit_seq == 2
        and set(conflict_replay.consumption) == {left_item.proposal_id, later_item.proposal_id}
        and right_item.proposal_id not in conflict_replay.consumption
    )
    checks["losing_writer_never_resolves_as_committed_ancestor"] = {
        "pass": conflict_ok,
        "rejected": right_rejected,
        "head_seq": conflict_replay.head_frontier.commit_seq,
        "consumed": sorted(conflict_replay.consumption),
    }
    if not conflict_ok:
        failures.append("losing writer was included or misresolved after successor progress")

    posix_root = work / "corruption-store"
    corrupt_log = initialize(PosixStorageBackend(posix_root), "checker-corruption")
    build(corrupt_log, 3)
    healthy = replay_log(corrupt_log)
    commit = healthy.commits[1]
    physical = posix_root / corrupt_log.layout.commit_key(commit.commit_seq, commit.commit_id)
    data = bytearray(physical.read_bytes())
    data[-1] ^= 1
    physical.write_bytes(data)
    try:
        replay_log(corrupt_log)
    except VerificationError as exc:
        corruption_seq = exc.commit_seq
    else:
        corruption_seq = None
    corruption_ok = corruption_seq == 2
    checks["corrupt_middle_commit_localizes_first_bad_sequence"] = {
        "pass": corruption_ok,
        "first_bad_commit_seq": corruption_seq,
    }
    if not corruption_ok:
        failures.append("middle commit corruption was not localized to commit_seq=2")

    cache_log = initialize(InMemoryStorageBackend(), "checker-cache")
    build(cache_log, 3)
    cache_path = work / "cache" / "consumption.sqlite"
    initial_cache = rebuild_cache(cache_log, cache_path)
    cache_path.write_bytes(b"corrupt cache")
    try:
        load_cache(cache_path)
    except VerificationError:
        corrupt_rejected = True
    else:
        corrupt_rejected = False
    rebuilt = rebuild_cache(cache_log, cache_path)
    cache_ok = corrupt_rejected and rebuilt == initial_cache and verify_cache(cache_log, cache_path) == initial_cache
    checks["corrupt_cache_rebuilds_from_authoritative_log"] = {
        "pass": cache_ok,
        "corrupt_rejected": corrupt_rejected,
        "head_seq": rebuilt.head_commit_seq,
    }
    if not cache_ok:
        failures.append("corrupt cache did not rebuild exactly")

    report = {
        "target_commit": "79373ecab4e051b4c9ff2ba128250d8612b9ab8b",
        "persistence_commit": "2db8a731e356f99d3c243a302674d94c8721e3c6",
        "hostname": os.uname().nodename,
        "checks": checks,
        "required_failures": failures,
    }
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
