"""Two-rank, dependency-free Lustre CAS and visibility contract worker."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
from pathlib import Path
import time

from .errors import NotFound, PreconditionFailed
from .posix import PosixStorageBackend


def _rank_and_world() -> tuple[int, int]:
    rank_text = os.environ.get("OMPI_COMM_WORLD_RANK", os.environ.get("PMI_RANK", ""))
    world_text = os.environ.get("OMPI_COMM_WORLD_SIZE", os.environ.get("PMI_SIZE", ""))
    if not rank_text or not world_text:
        raise RuntimeError("worker must run under MPI with rank/size environment")
    rank, world = int(rank_text), int(world_text)
    if world != 2 or rank not in {0, 1}:
        raise RuntimeError(f"P03 contract requires exactly two ranks, got rank={rank} size={world}")
    return rank, world


def _wait_for_key(backend: PosixStorageBackend, key: str, timeout: float = 60.0) -> bytes:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return backend.get(key)
        except NotFound:
            time.sleep(0.01)
    raise TimeoutError(f"timed out waiting for shared key {key}")


def _wait_for_both(
    backend: PosixStorageBackend,
    prefix: str,
    name: str,
    round_index: int,
) -> tuple[bytes, bytes]:
    return tuple(
        _wait_for_key(backend, f"{prefix}/rounds/{round_index:04d}/{name}/{rank}")
        for rank in range(2)
    )


def _lock_owner_crash(root: str, key: str, marker: str) -> None:
    backend = PosixStorageBackend(root)
    with backend._locked(key):
        backend.put_immutable(marker, b"locked")
        os._exit(73)


def run_contract(
    *,
    root: Path,
    prefix: str,
    rounds: int,
    output_dir: Path,
) -> dict[str, object]:
    rank, world = _rank_and_world()
    backend = PosixStorageBackend(root)
    head_key = f"{prefix}/control/head"
    init_key = f"{prefix}/control/initialized"
    if rank == 0:
        backend.put_if_absent(head_key, b"bootstrap")
        backend.put_immutable(init_key, b"ready")
    _wait_for_key(backend, init_key)

    winners = [0, 0]
    for round_index in range(rounds):
        round_prefix = f"{prefix}/rounds/{round_index:04d}"
        if rank == 0:
            current = backend.head(head_key)
            base = backend.conditional_replace(
                head_key,
                expected_version=current.version,
                data=f"base:{round_index}".encode("ascii"),
            )
            backend.put_immutable(f"{round_prefix}/ready", base.version.encode("ascii"))
        expected_version = _wait_for_key(backend, f"{round_prefix}/ready").decode("ascii")
        backend.put_immutable(f"{round_prefix}/arrived/{rank}", expected_version.encode("ascii"))
        if rank == 0:
            arrivals = _wait_for_both(backend, prefix, "arrived", round_index)
            if len(set(arrivals)) != 1:
                raise AssertionError("ranks did not race from the same expected version")
            backend.put_immutable(f"{round_prefix}/start", b"start")
        _wait_for_key(backend, f"{round_prefix}/start")

        value = f"winner:{round_index}:rank:{rank}".encode("ascii")
        try:
            metadata = backend.conditional_replace(
                head_key,
                expected_version=expected_version,
                data=value,
            )
        except PreconditionFailed:
            result = {"rank": rank, "status": "conflict", "value": value.decode("ascii")}
        else:
            result = {
                "rank": rank,
                "status": "winner",
                "value": value.decode("ascii"),
                "version": metadata.version,
            }
            winners[rank] += 1
        backend.put_immutable(
            f"{round_prefix}/results/{rank}",
            json.dumps(result, sort_keys=True).encode("utf-8"),
        )
        encoded_results = _wait_for_both(backend, prefix, "results", round_index)
        results = [json.loads(item) for item in encoded_results]
        round_winners = [item for item in results if item["status"] == "winner"]
        if len(round_winners) != 1:
            raise AssertionError(f"round {round_index} had {len(round_winners)} winners")
        if backend.get(head_key) != round_winners[0]["value"].encode("ascii"):
            raise AssertionError("rank observed a head value different from the CAS winner")
        backend.put_immutable(f"{round_prefix}/verified/{rank}", b"verified")
        if rank == 0:
            _wait_for_both(backend, prefix, "verified", round_index)
            backend.put_immutable(f"{round_prefix}/complete", b"complete")
        _wait_for_key(backend, f"{round_prefix}/complete")

    stale_prefix = f"{prefix}/stale-lock"
    if rank == 0:
        context = multiprocessing.get_context("spawn")
        owner = context.Process(
            target=_lock_owner_crash,
            args=(str(root), head_key, f"{stale_prefix}/owner-acquired"),
        )
        owner.start()
        owner.join(30)
        if owner.exitcode != 73:
            raise AssertionError(f"stale lock owner exit code was {owner.exitcode}")
        backend.put_immutable(f"{stale_prefix}/owner-exited", b"released")
    _wait_for_key(backend, f"{stale_prefix}/owner-exited")
    if rank == 1:
        current = backend.head(head_key)
        takeover = backend.conditional_replace(
            head_key,
            expected_version=current.version,
            data=b"stale-lock-takeover-rank-1",
        )
        backend.put_immutable(
            f"{stale_prefix}/takeover",
            takeover.version.encode("ascii"),
        )
    takeover_version = _wait_for_key(backend, f"{stale_prefix}/takeover").decode("ascii")
    if backend.get(head_key, expected_version=takeover_version) != b"stale-lock-takeover-rank-1":
        raise AssertionError("stale-lock takeover was not visible on both ranks")

    report = {
        "rank": rank,
        "world_size": world,
        "hostname": os.uname().nodename,
        "rounds": rounds,
        "winner_count": winners[rank],
        "double_winner_rounds": 0,
        "visibility_failures": 0,
        "stale_lock_takeover": "pass",
        "operation_count": len(backend.history),
        "capabilities": backend.capabilities.to_dict(),
        "operation_trace": f"rank_{rank}_operations.jsonl",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"rank_{rank}_operations.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "sequence": record.sequence,
                    "operation": record.operation,
                    "key": record.key,
                    "outcome": record.outcome,
                    "version": record.version,
                },
                sort_keys=True,
            )
            + "\n"
            for record in backend.history
        ),
        encoding="utf-8",
    )
    (output_dir / f"rank_{rank}.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True), flush=True)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--rounds", type=int, default=100)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.rounds < 100:
        raise ValueError("P03 two-node gate requires at least 100 rounds")
    run_contract(
        root=args.root,
        prefix=args.prefix,
        rounds=args.rounds,
        output_dir=args.output_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
