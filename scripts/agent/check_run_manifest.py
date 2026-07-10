#!/usr/bin/env python3
"""Verify a DuraLoCo run manifest's schema, self-digest, and evidence paths."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


REQUIRED = {
    "schema_version",
    "run_id",
    "parent_run_id",
    "purpose",
    "phase",
    "git_commit",
    "git_branch",
    "dirty_tree",
    "dirty_paths",
    "hostname",
    "python_version",
    "pbs_job_id",
    "pbs_nodefile_digest",
    "config_path",
    "config_digest",
    "dataset_revision",
    "model_revision",
    "backend",
    "seed",
    "commands_log",
    "stdout",
    "stderr",
    "exit_code",
    "started_at_utc",
    "ended_at_utc",
    "result",
    "assertions",
    "manifest_sha256",
}


class ManifestError(RuntimeError):
    pass


def _digest(payload: dict[str, Any]) -> str:
    body = dict(payload)
    body.pop("manifest_sha256", None)
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(
    path: Path,
    *,
    root: Path,
    require_evidence_files: bool = True,
) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ManifestError("manifest root must be an object")
    missing = REQUIRED - payload.keys()
    unknown = payload.keys() - REQUIRED
    if missing or unknown:
        raise ManifestError(f"schema fields differ: missing={sorted(missing)} extra={sorted(unknown)}")
    if payload["schema_version"] != 1:
        raise ManifestError("unsupported schema_version")
    if str(payload["phase"]) != "M00" and not re.fullmatch(
        r"P(0[0-9]|1[0-2])", str(payload["phase"])
    ):
        raise ManifestError("invalid phase")
    if not re.fullmatch(r"[0-9a-f]{40}", str(payload["git_commit"])):
        raise ManifestError("git_commit must be 40 lowercase hex")
    if payload["result"] not in {"pass", "fail", "inconclusive"}:
        raise ManifestError("invalid result")
    if payload["result"] == "pass":
        if payload["exit_code"] != 0:
            raise ManifestError("pass result requires exit_code 0")
        if not payload["assertions"]:
            raise ManifestError("pass result requires assertions")
    if payload["manifest_sha256"] != _digest(payload):
        raise ManifestError("manifest self-digest mismatch")
    if not isinstance(payload["config_path"], str) or not payload["config_path"]:
        raise ManifestError("config_path must bind every run to a configuration")
    if not re.fullmatch(r"[0-9a-f]{64}", str(payload["config_digest"])):
        raise ManifestError("config_digest must be 64 lowercase hex")
    config = Path(payload["config_path"])
    config = config if config.is_absolute() else root / config
    if not config.is_file():
        raise ManifestError(f"bound config does not exist: {payload['config_path']}")
    if _file_digest(config) != payload["config_digest"]:
        raise ManifestError("bound config digest does not match its bytes")
    if require_evidence_files:
        for field in ("commands_log", "stdout", "stderr"):
            relative = payload[field]
            if not isinstance(relative, str) or not relative:
                raise ManifestError(f"{field} must be a non-empty path")
            evidence = Path(relative)
            evidence = evidence if evidence.is_absolute() else path.parent / evidence
            if not evidence.is_file():
                raise ManifestError(f"evidence file does not exist for {field}: {relative}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--allow-missing-evidence-files", action="store_true")
    args = parser.parse_args(argv)
    try:
        validate(
            args.manifest,
            root=args.root.resolve(),
            require_evidence_files=not args.allow_missing_evidence_files,
        )
        return 0
    except (OSError, json.JSONDecodeError, ManifestError) as exc:
        print(f"check_run_manifest: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
