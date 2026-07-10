"""Inspect, verify, and replay a DuraLoCo POSIX log."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from fs_diloco.storage import PosixStorageBackend

from .commit import TransactionalLog
from .errors import VerificationError
from .replay import inspect_orphans, replay_log


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "replay", "orphans"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--generation", type=int, default=0)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def _result(args: argparse.Namespace) -> dict[str, object]:
    backend = PosixStorageBackend(args.root)
    log = TransactionalLog.open(backend, args.run_id, args.generation)
    if args.command in {"verify", "replay"}:
        replay = replay_log(log)
        return {
            "status": "PASS",
            "run_id": args.run_id,
            "commit_seq": replay.head_frontier.commit_seq,
            "commit_id": replay.head_frontier.commit_id,
            "committed_state_digest": replay.committed_state_digest,
            "prefix_digests": list(replay.prefix_digests),
            "consumed_proposal_count": len(replay.consumption),
        }
    if args.command == "orphans":
        return {"status": "PASS", "run_id": args.run_id, **inspect_orphans(log).to_dict()}
    raise ValueError(f"unsupported inspect command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = _result(args)
        exit_code = 0
    except VerificationError as exc:
        result = {
            "status": "FAIL",
            "reason": str(exc),
            "first_bad_commit_seq": exc.commit_seq,
        }
        exit_code = 2
    except Exception as exc:
        result = {"status": "FAIL", "reason": str(exc), "first_bad_commit_seq": None}
        exit_code = 2
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
