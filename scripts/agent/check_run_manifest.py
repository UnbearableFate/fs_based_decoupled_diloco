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


REQUIRED_V1 = {
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
V2_FIELDS = {
    "validation_shape",
    "termination_kind",
    "authority_head_before",
    "authority_head_after",
    "stage_metrics_path",
    "workflow_review_path",
    "same_commit_qualification",
    "pbs_queue",
    "requested_resources",
    "last_qstat_state",
    "termination_detail",
}
REQUIRED_V2 = REQUIRED_V1 | V2_FIELDS
TERMINATION_KINDS = {
    "success",
    "test_failure",
    "operator_terminated",
    "scheduler_timeout",
    "infrastructure",
    "pre_allocation_cancelled",
    "unknown",
}
QUALIFICATION_FIELDS = {"targeted_1node_benchmark", "miyabi_1node", "miyabi_2node"}
V2_PHASES = {
    "P05",
    "P06",
    "P06A",
    "P06B",
    "P06C",
    "P07",
    "P08",
    "P09",
    "P10",
    "P11",
    "P12",
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
    schema_version = payload.get("schema_version")
    if schema_version == 1:
        required = REQUIRED_V1
    elif schema_version == 2:
        required = REQUIRED_V2
    else:
        raise ManifestError("unsupported schema_version")
    missing = required - payload.keys()
    unknown = payload.keys() - required
    if missing or unknown:
        raise ManifestError(
            f"schema fields differ: missing={sorted(missing)} extra={sorted(unknown)}"
        )
    if str(payload["phase"]) != "M00" and not re.fullmatch(
        r"P(?:(?:0[0-9]|1[0-2])|06[ABC])", str(payload["phase"])
    ):
        raise ManifestError("invalid phase")
    if payload["phase"] in V2_PHASES and schema_version != 2:
        raise ManifestError(f"{payload['phase']} requires schema_version 2")
    if not re.fullmatch(r"[0-9a-f]{40}", str(payload["git_commit"])):
        raise ManifestError("git_commit must be 40 lowercase hex")
    if payload["result"] not in {"pass", "fail", "inconclusive"}:
        raise ManifestError("invalid result")
    if schema_version == 2:
        validation_shape = payload["validation_shape"]
        if not isinstance(validation_shape, str) or not validation_shape.strip():
            raise ManifestError("validation_shape must be a non-empty stable identifier")
        termination = payload["termination_kind"]
        if termination not in TERMINATION_KINDS:
            raise ManifestError("invalid termination_kind")
        allowed_terminations = {
            "pass": {"success"},
            "fail": {
                "test_failure",
                "operator_terminated",
                "scheduler_timeout",
                "infrastructure",
            },
            "inconclusive": {
                "operator_terminated",
                "scheduler_timeout",
                "infrastructure",
                "pre_allocation_cancelled",
                "unknown",
            },
        }
        if termination not in allowed_terminations[payload["result"]]:
            raise ManifestError(
                f"termination_kind {termination!r} is inconsistent with "
                f"result {payload['result']!r}"
            )
        for field in ("authority_head_before", "authority_head_after"):
            value = payload[field]
            if value is not None and (not isinstance(value, str) or not value):
                raise ManifestError(f"{field} must be null or a non-empty identity")
        for field in ("stage_metrics_path", "workflow_review_path"):
            value = payload[field]
            if value is not None and (not isinstance(value, str) or not value):
                raise ManifestError(f"{field} must be null or a non-empty path")
        for field in (
            "pbs_queue",
            "requested_resources",
            "last_qstat_state",
            "termination_detail",
        ):
            value = payload[field]
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ManifestError(f"{field} must be null or a non-empty string")
        if termination == "pre_allocation_cancelled":
            cancelled_fields = (
                "pbs_job_id",
                "pbs_queue",
                "requested_resources",
                "last_qstat_state",
                "termination_detail",
            )
            missing_cancelled = [field for field in cancelled_fields if not payload[field]]
            if missing_cancelled:
                raise ManifestError(
                    "pre-allocation cancellation is missing scheduler evidence: "
                    + ", ".join(missing_cancelled)
                )
        qualification = payload["same_commit_qualification"]
        if not isinstance(qualification, dict) or set(qualification) != QUALIFICATION_FIELDS:
            raise ManifestError("same_commit_qualification fields differ from schema")
        for field, value in qualification.items():
            if value is not None and (not isinstance(value, str) or not value):
                raise ManifestError(
                    f"same_commit_qualification.{field} must be null or a non-empty reference"
                )
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
