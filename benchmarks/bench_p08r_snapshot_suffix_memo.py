#!/usr/bin/env python3
"""Replay a frozen real two-transition snapshot suffix twice, read-only."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

from fs_diloco.log import ProductionTransactionalLog
from fs_diloco.log.codec import content_ref
from fs_diloco.protocol.canonical_json import canonical_bytes
from fs_diloco.protocol.schemas import ControlCommitManifest, HeadManifest
from fs_diloco.storage import PosixStorageBackend
from fs_diloco.storage.base import ObjectMetadata
from fs_diloco.storage.errors import PreconditionFailed


class _HistoricalHeadBackend:
    """Read-only backend view with one synthetic historical head."""

    def __init__(self, backend, *, head_key: str, head_data: bytes) -> None:
        self._backend = backend
        self._head_key = head_key
        self._head_data = head_data
        self._metadata = ObjectMetadata(
            key=head_key,
            size=len(head_data),
            sha256=hashlib.sha256(head_data).hexdigest(),
            version="historical-head-overlay-v1",
        )

    def __getattr__(self, name):
        return getattr(self._backend, name)

    def head(self, key: str) -> ObjectMetadata:
        if key == self._head_key:
            return self._metadata
        return self._backend.head(key)

    def get(self, key: str, *, expected_version: str | None = None) -> bytes:
        if key == self._head_key:
            if expected_version not in {None, self._metadata.version}:
                raise PreconditionFailed("historical head version differs")
            return self._head_data
        return self._backend.get(key, expected_version=expected_version)

    def put_immutable(self, *_args, **_kwargs):
        raise RuntimeError("historical head benchmark is read-only")

    def compare_and_swap(self, *_args, **_kwargs):
        raise RuntimeError("historical head benchmark is read-only")

    def delete(self, *_args, **_kwargs):
        raise RuntimeError("historical head benchmark is read-only")


def _call(log: ProductionTransactionalLog) -> dict[str, object]:
    started = time.monotonic_ns()
    result = log.replay_from_snapshot()
    elapsed_ns = time.monotonic_ns() - started
    if result.telemetry is None:
        raise RuntimeError("snapshot suffix replay omitted causal telemetry")
    return {
        "elapsed_seconds": elapsed_ns / 1_000_000_000,
        "mode": result.mode,
        "snapshot_id": result.snapshot_id,
        "covered_commit_seq": result.covered_commit_seq,
        "suffix_length": result.suffix_length,
        "state_digest": result.replay.committed_state_digest,
        "tensor_payload_bytes": result.telemetry.tensor_payload_bytes,
        "storage_payload_bytes": result.telemetry.storage_payload_bytes,
        "cache_entries_before": result.telemetry.cache_entries_before,
        "cache_entries_after": result.telemetry.cache_entries_after,
        "promoted_entries": result.telemetry.promoted_entries,
        "replay": result.replay,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-generation", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    backend = PosixStorageBackend(args.training_root / "authority")
    source = ProductionTransactionalLog.open(
        backend, args.run_id, args.run_generation
    )
    source_head_before = hashlib.sha256(
        backend.get(source.layout.head_key)
    ).hexdigest()
    terminal = source.replay(force_full=True)
    pins = [
        commit
        for commit in terminal.commits
        if isinstance(commit, ControlCommitManifest)
        and commit.control_kind == "snapshot_pin"
    ]
    if len(pins) != 5:
        raise RuntimeError("frozen R2 authority does not contain five snapshot pins")
    selected_pin = pins[-2]
    next_pin = pins[-1]
    target_seq = next_pin.commit_seq - 1
    if target_seq <= selected_pin.commit_seq:
        raise RuntimeError("historical snapshot has no optimizer suffix")
    target = terminal.frontiers[target_seq]
    frontier_data = canonical_bytes(target.to_dict())
    frontier_ref = content_ref(
        source.layout.frontier_key(target.commit_seq, target.frontier_sha256),
        frontier_data,
    )
    historical_head = HeadManifest(
        protocol_version=2,
        run_id=args.run_id,
        run_generation=args.run_generation,
        fencing_epoch=target.fencing_epoch,
        commit_seq=target.commit_seq,
        commit_id=target.commit_id,
        frontier_ref=frontier_ref,
    )
    overlay = _HistoricalHeadBackend(
        backend,
        head_key=source.layout.head_key,
        head_data=canonical_bytes(historical_head.to_dict()),
    )
    log = ProductionTransactionalLog.open(
        overlay, args.run_id, args.run_generation
    )
    first = _call(log)
    second = _call(log)
    strict_started = time.monotonic_ns()
    strict = log.replay(force_full=True)
    strict_seconds = (time.monotonic_ns() - strict_started) / 1_000_000_000
    source_head_after = hashlib.sha256(
        backend.get(source.layout.head_key)
    ).hexdigest()

    optimizer_suffix = sum(
        commit.__class__.__name__ == "CommitManifest"
        for commit in first["replay"].commits[selected_pin.commit_seq :]
    )
    if first["mode"] != "snapshot_suffix" or second["mode"] != "snapshot_suffix":
        raise RuntimeError("historical head did not use snapshot suffix replay")
    if optimizer_suffix != 2:
        raise RuntimeError("historical benchmark suffix is not two optimizer transitions")
    if first["replay"] != strict or second["replay"] != strict:
        raise RuntimeError("memoized historical suffix differs from strict replay")
    if int(first["tensor_payload_bytes"]) <= 10_000_000_000:
        raise RuntimeError("first historical suffix did not reproduce real tensor reads")
    if int(second["tensor_payload_bytes"]) != 0:
        raise RuntimeError("second historical suffix reread verified tensor payloads")
    if source_head_before != source_head_after:
        raise RuntimeError("historical head benchmark changed source authority")

    for call in (first, second):
        del call["replay"]
    report = {
        "schema": "duraloco-p08r-real-snapshot-suffix-memo-v1",
        "status": "PASS",
        "training_root": str(args.training_root),
        "run_id": args.run_id,
        "source_head_sha256_before": source_head_before,
        "source_head_sha256_after": source_head_after,
        "historical_head_commit_seq": target_seq,
        "snapshot_pin_commit_seq": selected_pin.commit_seq,
        "optimizer_suffix_transitions": optimizer_suffix,
        "first_call": first,
        "second_call": second,
        "strict_seconds": strict_seconds,
        "strict_state_digest": strict.committed_state_digest,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
