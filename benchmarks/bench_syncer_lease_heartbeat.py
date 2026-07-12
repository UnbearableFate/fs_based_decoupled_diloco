#!/usr/bin/env python3
"""Targeted proof that a long non-authoritative stage outlives its initial lease."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import time

from fs_diloco.coordination import LeaseManager, LeaseMutation
from fs_diloco.log.layout import LogLayout
from fs_diloco.storage import InMemoryStorageBackend
from fs_diloco.syncer import _run_non_authoritative_substage


class _Logger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def event(self, event_type: str, **fields: object) -> None:
        self.events.append((event_type, fields))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-seconds", type=float, default=1.3)
    parser.add_argument("--lease-ttl-seconds", type=float, default=0.5)
    parser.add_argument("--renew-interval-seconds", type=float, default=0.1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 0 < args.renew_interval_seconds < args.lease_ttl_seconds < args.stage_seconds:
        raise ValueError("benchmark requires renew interval < TTL < stage duration")

    manager = LeaseManager(
        InMemoryStorageBackend(),
        LogLayout("p08-lease-heartbeat", 0),
        max_clock_skew_ns=0,
    )
    acquired_at = time.time_ns()
    initial = manager.acquire(
        LeaseMutation(
            operation="acquire",
            request_id="benchmark-acquire",
            owner_id="syncer-a",
            owner_session_id="session-a",
            observed_fencing_epoch=0,
            requested_at_utc_ns=acquired_at,
            ttl_ns=int(args.lease_ttl_seconds * 1_000_000_000),
        )
    )
    config = SimpleNamespace(
        coordination=SimpleNamespace(
            renew_interval_seconds=args.renew_interval_seconds,
            lease_ttl_seconds=args.lease_ttl_seconds,
        )
    )
    logger = _Logger()
    started = time.monotonic()
    result, final = _run_non_authoritative_substage(
        lambda: (time.sleep(args.stage_seconds), "complete")[1],
        substage="benchmark_long_prepare",
        lease_manager=manager,
        loaded_lease=initial,
        config=config,
        logger=logger,
    )
    elapsed = time.monotonic() - started
    renewals = [
        fields
        for event, fields in logger.events
        if event == "coordination_stage_completed" and fields.get("stage") == "lease_renew"
    ]
    payload = {
        "schema": "duraloco-syncer-lease-heartbeat-benchmark-v1",
        "status": "PASS",
        "stage_seconds": args.stage_seconds,
        "elapsed_seconds": elapsed,
        "lease_ttl_seconds": args.lease_ttl_seconds,
        "renew_interval_seconds": args.renew_interval_seconds,
        "renewal_count": len(renewals),
        "initial_lease_sequence": initial.record.lease_sequence,
        "final_lease_sequence": final.record.lease_sequence,
        "final_expiry_is_future": final.record.expires_at_utc_ns > time.time_ns(),
        "result": result,
    }
    if (
        result != "complete"
        or elapsed <= args.lease_ttl_seconds
        or not renewals
        or not payload["final_expiry_is_future"]
    ):
        raise AssertionError("long stage did not retain a renewable live lease")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
