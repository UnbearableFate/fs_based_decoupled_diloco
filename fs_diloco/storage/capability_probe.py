"""Fail-closed storage capability probe and JSON CLI."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import tempfile
import time
from typing import Iterable

from .base import StorageBackend
from .errors import CapabilityError, ImmutableConflict, PreconditionFailed
from .layout import RESERVED_ROOT, normalize_key
from .posix import PosixStorageBackend


_LOCK_PROBE_SCHEMA = "duraloco-cross-node-lock-probe-v1"


def _write_probe_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _wait_for_probe_json(path: Path, *, deadline: float) -> dict[str, object]:
    while time.monotonic() < deadline:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            time.sleep(0.01)
            continue
        if isinstance(payload, dict):
            return payload
        raise CapabilityError(f"lock probe marker is not a JSON object: {path}")
    raise TimeoutError(f"timed out waiting for lock probe marker: {path}")


def probe_cross_node_advisory_lock(
    root: Path,
    *,
    prefix: str,
    rank: int,
    world_size: int,
    timeout_seconds: float = 60.0,
    require_distinct_hosts: bool = True,
) -> dict[str, object]:
    """Prove that one process' ``flock`` excludes a process on another host."""

    if world_size != 2 or rank not in {0, 1}:
        raise ValueError("cross-node lock probe requires exactly two ranks")
    if timeout_seconds <= 0:
        raise ValueError("cross-node lock probe timeout must be positive")
    root = root.expanduser().resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    probe_identity = f"{prefix}\0{os.environ.get('PBS_JOBID', '')}"
    probe_id = hashlib.sha256(probe_identity.encode("utf-8")).hexdigest()[:24]
    probe_root = root / RESERVED_ROOT / "scope-probes" / probe_id
    probe_root.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    host_path = probe_root / f"host-{rank}.json"
    _write_probe_json(host_path, {"hostname": socket.gethostname(), "rank": rank})
    lock_path = probe_root / "scope.lock"
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    blocked_while_held = False
    acquired_after_release = False
    try:
        if rank == 0:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            _write_probe_json(probe_root / "holder-ready.json", {"ready": True})
            contender = _wait_for_probe_json(
                probe_root / "contender-blocked.json", deadline=deadline
            )
            blocked_while_held = contender.get("blocked") is True
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            _write_probe_json(probe_root / "holder-released.json", {"released": True})
            takeover = _wait_for_probe_json(
                probe_root / "contender-acquired.json", deadline=deadline
            )
            acquired_after_release = takeover.get("acquired") is True
        else:
            _wait_for_probe_json(probe_root / "holder-ready.json", deadline=deadline)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                blocked_while_held = True
            else:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            _write_probe_json(
                probe_root / "contender-blocked.json",
                {"blocked": blocked_while_held},
            )
            _wait_for_probe_json(probe_root / "holder-released.json", deadline=deadline)
            while time.monotonic() < deadline:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    time.sleep(0.01)
                    continue
                acquired_after_release = True
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                break
            _write_probe_json(
                probe_root / "contender-acquired.json",
                {"acquired": acquired_after_release},
            )
    finally:
        os.close(descriptor)

    _write_probe_json(
        probe_root / f"result-{rank}.json",
        {
            "acquired_after_release": acquired_after_release,
            "blocked_while_held": blocked_while_held,
            "hostname": socket.gethostname(),
            "rank": rank,
        },
    )
    if rank == 0:
        rank_reports = [
            _wait_for_probe_json(probe_root / f"result-{item}.json", deadline=deadline)
            for item in range(2)
        ]
        hosts = sorted({str(item["hostname"]) for item in rank_reports})
        report = {
            "schema": _LOCK_PROBE_SCHEMA,
            "root": str(root),
            "prefix": prefix,
            "hosts": hosts,
            "world_size": world_size,
            "distinct_hosts": len(hosts) == 2,
            "blocked_while_held": all(
                item.get("blocked_while_held") is True for item in rank_reports
            ),
            "acquired_after_release": all(
                item.get("acquired_after_release") is True for item in rank_reports
            ),
            "pbs_job_id": os.environ.get("PBS_JOBID"),
        }
        report["passed"] = (
            (len(hosts) == 2 or not require_distinct_hosts)
            and report["blocked_while_held"] is True
            and report["acquired_after_release"] is True
        )
        _write_probe_json(probe_root / "summary.json", report)
    report = _wait_for_probe_json(probe_root / "summary.json", deadline=deadline)
    if report.get("passed") is not True:
        raise CapabilityError("cross-node advisory-lock exclusion probe failed")
    return report


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
    operation_trace: tuple[dict[str, object], ...]

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
        request_id="capability-probe-winner",
    )
    stale_rejected = False
    try:
        backend.conditional_replace(
            head_key,
            expected_version=control.version,
            data=b"two",
            request_id="capability-probe-stale",
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
        operation_trace=tuple(asdict(record) for record in backend.history),
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
    parser.add_argument("--cross-node-lock-rank", type=int)
    parser.add_argument("--cross-node-lock-world-size", type=int, default=2)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.cross_node_lock_rank is not None:
        report = probe_cross_node_advisory_lock(
            args.root,
            prefix=args.prefix,
            rank=args.cross_node_lock_rank,
            world_size=args.cross_node_lock_world_size,
        )
        if args.cross_node_lock_rank == 0:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(report, sort_keys=True))
        return 0
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
