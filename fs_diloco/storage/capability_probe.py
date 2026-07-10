"""Fail-closed storage capability probe and JSON CLI."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import platform
from typing import Iterable

from .base import StorageBackend
from .errors import CapabilityError, ImmutableConflict, PreconditionFailed
from .layout import normalize_key
from .posix import PosixStorageBackend


@dataclass(frozen=True)
class CapabilityReport:
    schema_version: int
    backend: str
    prefix: str
    capabilities: dict[str, bool | str]
    assertions: dict[str, bool]
    hostname: str
    filesystem_id: int | None
    filesystem_block_size: int | None

    @property
    def passed(self) -> bool:
        return all(self.assertions.values())

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "passed": self.passed}


def require_capabilities(report: CapabilityReport, required: Iterable[str]) -> None:
    missing = [name for name in required if report.capabilities.get(name) is not True]
    if missing:
        raise CapabilityError(
            "required storage capabilities are unavailable: " + ", ".join(missing)
        )
    if not report.passed:
        failed = [name for name, passed in report.assertions.items() if not passed]
        raise CapabilityError("storage capability assertions failed: " + ", ".join(failed))


def probe_backend(
    backend: StorageBackend,
    *,
    prefix: str,
    filesystem_path: Path | None = None,
) -> CapabilityReport:
    prefix = normalize_key(prefix).rstrip("/")
    immutable_key = f"{prefix}/immutable"
    head_key = f"{prefix}/control/head"
    first = backend.put_immutable(immutable_key, b"immutable")
    same = backend.put_immutable(immutable_key, b"immutable")
    immutable_conflict = False
    try:
        backend.put_immutable(immutable_key, b"different")
    except ImmutableConflict:
        immutable_conflict = True
    control = backend.put_if_absent(head_key, b"zero")
    winner = backend.conditional_replace(
        head_key,
        expected_version=control.version,
        data=b"one",
    )
    stale_rejected = False
    try:
        backend.conditional_replace(
            head_key,
            expected_version=control.version,
            data=b"two",
        )
    except PreconditionFailed:
        stale_rejected = True
    assertions = {
        "immutable_idempotent": first == same,
        "immutable_conflict_detected": immutable_conflict,
        "verified_get": backend.get(immutable_key) == b"immutable",
        "head_matches_get": backend.head(head_key) == winner,
        "range_get": backend.range_get(immutable_key, 1, 4) == b"mmu",
        "stale_cas_rejected": stale_rejected,
        "listing_discovers_objects": set(backend.list_prefix(prefix + "/"))
        >= {immutable_key, head_key},
    }
    stat = None
    if filesystem_path is not None:
        stat = os.statvfs(filesystem_path)
    return CapabilityReport(
        schema_version=1,
        backend=backend.capabilities.backend,
        prefix=prefix,
        capabilities=backend.capabilities.to_dict(),
        assertions=assertions,
        hostname=platform.node(),
        filesystem_id=getattr(stat, "f_fsid", None) if stat is not None else None,
        filesystem_block_size=stat.f_bsize if stat is not None else None,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--require",
        action="append",
        default=[],
        help="required boolean capability name; may be repeated",
    )
    parser.add_argument("--allow-missing-directory-fsync", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    backend = PosixStorageBackend(
        args.root,
        require_directory_fsync=not args.allow_missing_directory_fsync,
    )
    report = probe_backend(backend, prefix=args.prefix, filesystem_path=args.root)
    required = args.require or [
        "immutable_create",
        "conditional_replace",
        "verified_reads",
        "atomic_replace",
        "advisory_lock",
        "directory_fsync",
    ]
    require_capabilities(report, required)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n")
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
