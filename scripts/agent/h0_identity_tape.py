#!/usr/bin/env python3
"""Emit deterministic committed identities for the H0 P07 regression tape."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fs_diloco.runtime_view import build_runtime_view
from tests.distributed_syncer.test_distributed_transition_binding import (
    _initialize,
    _prepare,
    _proposal,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log = _initialize(distributed=True)
    proposal = _proposal(log)
    prepared = _prepare(log, proposal)
    log.commit_prepared(prepared)
    replay = log.replay(force_full=True)
    view = build_runtime_view(log, force_full=True)
    payload = {
        "commit_ids": [commit.commit_id for commit in replay.commits],
        "committed_state_digest": replay.committed_state_digest,
        "frontier_digest": view.frontier_sha256,
        "head_commit_id": view.commit_id,
        "head_commit_seq": view.commit_seq,
        "prepared_commit_id": prepared.commit.commit_id,
        "proposal_id": proposal.proposal_id,
        "view_digest": view.view_digest,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
