"""Dependency-light Miyabi 1-node and 2-node P04 contract workers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from fs_diloco.log.model import ReferenceProposal
from fs_diloco.storage import InMemoryStorageBackend, NotFound, PosixStorageBackend

from .cache import rebuild_cache, verify_cache
from .commit import CRASH_POINTS, CommitConflict, TransactionalLog
from .errors import InjectedLogCrash
from .replay import inspect_orphans, replay_log
from .run import RunSpec


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _spec(run_id: str) -> RunSpec:
    return RunSpec(
        run_id=run_id,
        run_generation=0,
        model_revision="p04-miyabi-contract",
        parameter_index_digest=_digest("p04-parameter-index"),
        fragment_layout_digest=_digest("p04-fragment-layout"),
        outer_optimizer_schema_digest=_digest("p04-outer-schema"),
    )


def _proposal(
    log: TransactionalLog,
    *,
    learner: str,
    sequence: int,
    fragment_id: int,
    values: tuple[float, float],
) -> ReferenceProposal:
    current = replay_log(log).head_frontier
    proposal = ReferenceProposal.create(
        learner_id=learner,
        session_id=f"session-{learner}",
        sequence=sequence,
        fragment_id=fragment_id,
        base_commit_id=current.commit_id,
        base_commit_seq=current.commit_seq,
        base_fragment_version=current.fragments[fragment_id].version,
        target_tokens=1000 + sequence,
        values=values,
    )
    log.publish_proposal(proposal)
    return proposal


def _build_prefix(backend, run_id: str, steps: int = 10):
    log = TransactionalLog.initialize(
        backend, _spec(run_id), {0: (0.0, 0.0), 1: (0.0, 0.0)}
    )
    for sequence in range(1, steps + 1):
        fragment_id = (sequence - 1) % 2
        proposal = _proposal(
            log,
            learner=f"learner-{sequence:03d}",
            sequence=sequence,
            fragment_id=fragment_id,
            values=(float(sequence), -float(sequence) / 3.0),
        )
        log.commit_transition(
            fragment_id=fragment_id,
            selected_proposal_ids=(proposal.proposal_id,),
        )
    return log, replay_log(log)


def run_one_node(*, root: Path, run_id: str, output: Path, cache: Path) -> dict[str, object]:
    backend = PosixStorageBackend(root)
    log, posix_replay = _build_prefix(backend, run_id)
    _, memory_replay = _build_prefix(InMemoryStorageBackend(), run_id)
    if posix_replay.prefix_digests != memory_replay.prefix_digests:
        raise AssertionError("memory/POSIX committed prefix digests differ")
    first_cache = rebuild_cache(log, cache)
    cache.unlink()
    second_cache = rebuild_cache(log, cache)
    if first_cache != second_cache or verify_cache(log, cache) != first_cache:
        raise AssertionError("cache rebuild is not exact")

    orphan_proposal = _proposal(
        log,
        learner="orphan-learner",
        sequence=1,
        fragment_id=0,
        values=(99.0, -99.0),
    )
    prepared = log.prepare_transition(
        fragment_id=0, selected_proposal_ids=(orphan_proposal.proposal_id,)
    )
    orphan_report = inspect_orphans(log)
    if prepared.commit_ref.key not in orphan_report.prepared_orphans:
        raise AssertionError("prepared commit was not classified as an orphan")
    if replay_log(log).head_frontier.commit_seq != 10:
        raise AssertionError("orphan preparation changed the committed prefix")

    crash_results: dict[str, int] = {}
    for index, crash_point in enumerate(CRASH_POINTS):
        crash_log = TransactionalLog.initialize(
            backend,
            _spec(f"{run_id}-crash-{index:02d}"),
            {0: (0.0, 0.0)},
        )
        item = _proposal(
            crash_log,
            learner="crash-learner",
            sequence=1,
            fragment_id=0,
            values=(1.0, -1.0),
        )
        try:
            crash_log.commit_transition(
                fragment_id=0,
                selected_proposal_ids=(item.proposal_id,),
                crash_at=crash_point,
            )
        except InjectedLogCrash:
            pass
        else:
            raise AssertionError(f"crash point did not fire: {crash_point}")
        observed_seq = replay_log(crash_log).head_frontier.commit_seq
        expected_seq = 1 if crash_point == "after_head_cas" else 0
        if observed_seq != expected_seq:
            raise AssertionError(f"{crash_point} recovered to prefix {observed_seq}")
        crash_results[crash_point] = observed_seq

    report = {
        "status": "PASS",
        "hostname": os.uname().nodename,
        "run_id": run_id,
        "commit_seq": posix_replay.head_frontier.commit_seq,
        "prefix_digests": list(posix_replay.prefix_digests),
        "committed_state_digest": posix_replay.committed_state_digest,
        "memory_posix_equal": True,
        "crash_points": crash_results,
        "cache_rebuild_exact": True,
        "prepared_orphan_count": len(orphan_report.prepared_orphans),
        "operation_count": len(backend.history),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True), flush=True)
    return report


def _rank_and_world() -> tuple[int, int]:
    rank = int(os.environ.get("OMPI_COMM_WORLD_RANK", os.environ.get("PMI_RANK", "-1")))
    world = int(os.environ.get("OMPI_COMM_WORLD_SIZE", os.environ.get("PMI_SIZE", "-1")))
    if world != 2 or rank not in {0, 1}:
        raise RuntimeError(f"P04 two-node worker requires rank 0/1 of 2, got {rank}/{world}")
    return rank, world


def _wait(backend: PosixStorageBackend, key: str, timeout: float = 60.0) -> bytes:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return backend.get(key)
        except NotFound:
            time.sleep(0.01)
    raise TimeoutError(f"timed out waiting for {key}")


def run_two_node(
    *, root: Path, run_id: str, rounds: int, output_dir: Path
) -> dict[str, object]:
    rank, world = _rank_and_world()
    backend = PosixStorageBackend(root)
    barrier = f"coordination/{run_id}"
    if rank == 0:
        TransactionalLog.initialize(
            backend, _spec(run_id), {0: (0.0, 0.0), 1: (0.0, 0.0)}
        )
        backend.put_immutable(f"{barrier}/initialized", b"ready")
    _wait(backend, f"{barrier}/initialized")
    log = TransactionalLog.open(backend, run_id)
    wins = 0
    conflicts = 0
    for round_index in range(rounds):
        current = replay_log(log).head_frontier
        item = ReferenceProposal.create(
            learner_id=f"rank-{rank}-round-{round_index}",
            session_id=f"rank-{rank}",
            sequence=round_index + 1,
            fragment_id=round_index % 2,
            base_commit_id=current.commit_id,
            base_commit_seq=current.commit_seq,
            base_fragment_version=current.fragments[round_index % 2].version,
            target_tokens=1000 + rank,
            values=(float(rank + 1), float(round_index + 1)),
        )
        log.publish_proposal(item)
        prepared = log.prepare_transition(
            fragment_id=item.fragment_id, selected_proposal_ids=(item.proposal_id,)
        )
        backend.put_immutable(f"{barrier}/rounds/{round_index:03d}/ready/{rank}", b"ready")
        if rank == 0:
            _wait(backend, f"{barrier}/rounds/{round_index:03d}/ready/0")
            _wait(backend, f"{barrier}/rounds/{round_index:03d}/ready/1")
            backend.put_immutable(f"{barrier}/rounds/{round_index:03d}/start", b"start")
        _wait(backend, f"{barrier}/rounds/{round_index:03d}/start")
        try:
            result = log.commit_prepared(prepared)
        except CommitConflict:
            status = "conflict"
            conflicts += 1
        else:
            status = result.status
            if result.status == "committed":
                wins += 1
        backend.put_immutable(
            f"{barrier}/rounds/{round_index:03d}/result/{rank}",
            status.encode("ascii"),
        )
        left = _wait(backend, f"{barrier}/rounds/{round_index:03d}/result/0").decode()
        right = _wait(backend, f"{barrier}/rounds/{round_index:03d}/result/1").decode()
        if sum(value == "committed" for value in (left, right)) != 1:
            raise AssertionError(f"round {round_index} did not have exactly one winner")
        replay = replay_log(log)
        if replay.head_frontier.commit_seq != round_index + 1:
            raise AssertionError("committed prefix did not advance exactly once")
        backend.put_immutable(f"{barrier}/rounds/{round_index:03d}/verified/{rank}", b"ok")
        if rank == 0:
            _wait(backend, f"{barrier}/rounds/{round_index:03d}/verified/0")
            _wait(backend, f"{barrier}/rounds/{round_index:03d}/verified/1")
            backend.put_immutable(f"{barrier}/rounds/{round_index:03d}/complete", b"ok")
        _wait(backend, f"{barrier}/rounds/{round_index:03d}/complete")

    final = replay_log(log)
    report = {
        "status": "PASS",
        "rank": rank,
        "world_size": world,
        "hostname": os.uname().nodename,
        "rounds": rounds,
        "wins": wins,
        "conflicts": conflicts,
        "final_commit_seq": final.head_frontier.commit_seq,
        "committed_state_digest": final.committed_state_digest,
        "double_winners": 0,
        "double_inclusions": len(final.consumption) - len(set(final.consumption)),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"rank_{rank}.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True), flush=True)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    one = subparsers.add_parser("one-node")
    one.add_argument("--root", type=Path, required=True)
    one.add_argument("--run-id", required=True)
    one.add_argument("--output", type=Path, required=True)
    one.add_argument("--cache", type=Path, required=True)
    two = subparsers.add_parser("two-node")
    two.add_argument("--root", type=Path, required=True)
    two.add_argument("--run-id", required=True)
    two.add_argument("--rounds", type=int, default=20)
    two.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "one-node":
        run_one_node(root=args.root, run_id=args.run_id, output=args.output, cache=args.cache)
    else:
        if args.rounds < 10:
            raise ValueError("P04 two-node gate requires at least 10 rounds")
        run_two_node(
            root=args.root,
            run_id=args.run_id,
            rounds=args.rounds,
            output_dir=args.output_dir,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
