"""Separate lifecycle inspection and synthetic-GC CLI.

This module intentionally does not register commands in or shadow
``fs_diloco.cli``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fs_diloco.log.gc import GcMarkV1, apply_gc, create_gc_mark
from fs_diloco.log.production import ProductionTransactionalLog
from fs_diloco.log.reachability import build_reachability
from fs_diloco.storage import PosixStorageBackend


def _open(args: argparse.Namespace) -> ProductionTransactionalLog:
    backend = PosixStorageBackend(Path(args.storage_root))
    return ProductionTransactionalLog.open(
        backend, args.run_id, args.run_generation
    )


def _write(payload: object, output: str | None) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output:
        Path(output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


def _reachability(args: argparse.Namespace) -> int:
    log = _open(args)
    report = build_reachability(
        log, grace_eligible_keys=args.grace_eligible_key
    )
    payload = report.to_dict()
    if args.explain:
        payload["explanation"] = [
            {"source": edge.source, "target": edge.target, "reason": edge.reason}
            for edge in report.explain(args.explain)
        ]
        payload["target_retention_reasons"] = dict(report.retention_reasons).get(
            args.explain, ()
        )
    _write(payload, args.output)
    return 0


def _mark(args: argparse.Namespace) -> int:
    log = _open(args)
    mark, report = create_gc_mark(
        log, grace_eligible_keys=args.grace_eligible_key
    )
    _write(
        {"mode": "dry_run", "mark": mark.to_dict(), "report": report.to_dict()},
        args.output,
    )
    return 0


def _apply(args: argparse.Namespace) -> int:
    log = _open(args)
    mark_payload = json.loads(Path(args.mark).read_text(encoding="utf-8"))
    if isinstance(mark_payload, dict) and "mark" in mark_payload:
        mark_payload = mark_payload["mark"]
    mark = GcMarkV1.from_dict(mark_payload)
    result = apply_gc(
        log,
        mark,
        approval_token=args.approval_token,
        namespace=args.namespace,
        grace_eligible_keys=args.grace_eligible_key,
        request_id=args.request_id,
    )
    _write(result.to_dict(), args.output)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-generation", type=int, default=0)
    parser.add_argument("--output")
    parser.add_argument("--grace-eligible-key", action="append", default=[])
    subparsers = parser.add_subparsers(dest="command", required=True)
    reachability = subparsers.add_parser("reachability")
    reachability.add_argument("--explain")
    reachability.set_defaults(handler=_reachability)
    mark = subparsers.add_parser("gc-mark")
    mark.set_defaults(handler=_mark)
    apply = subparsers.add_parser("gc-apply")
    apply.add_argument("--mark", required=True)
    apply.add_argument("--approval-token", required=True)
    apply.add_argument("--namespace", required=True, choices=("synthetic",))
    apply.add_argument("--request-id", required=True)
    apply.set_defaults(handler=_apply)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
