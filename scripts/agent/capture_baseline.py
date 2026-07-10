#!/usr/bin/env python3
"""Capture or verify an immutable, content-addressed repository baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any


DEFAULT_CRITICAL_PATHS = (
    "AGENTS.md",
    "README.md",
    "pyproject.toml",
    ".python-version",
    "fs_diloco",
    "configs",
    "scripts/local",
    "scripts/miyabi",
    "tests",
    "plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans",
)


class BaselineError(RuntimeError):
    pass


def _run_git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if proc.returncode != 0:
        raise BaselineError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.rstrip("\n")


def _run_git_bytes(root: Path, *args: str) -> bytes:
    proc = subprocess.run(["git", *args], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise BaselineError(proc.stderr.decode(errors="replace").strip())
    return proc.stdout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_files(root: Path, critical_paths: tuple[str, ...]) -> list[Path]:
    files: set[Path] = set()
    for relative in critical_paths:
        candidate = root / relative
        if not candidate.exists():
            raise BaselineError(f"critical path is missing: {relative}")
        if candidate.is_file():
            files.add(candidate)
            continue
        for path in candidate.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                files.add(path)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def _file_records(root: Path, critical_paths: tuple[str, ...]) -> list[dict[str, Any]]:
    records = []
    for path in _iter_files(root, critical_paths):
        relative = path.relative_to(root).as_posix()
        records.append(
            {
                "path": relative,
                "size": path.stat().st_size,
                "sha256": _sha256(path),
                "executable": bool(path.stat().st_mode & 0o111),
            }
        )
    return records


def _commit_file_records(
    root: Path, critical_paths: tuple[str, ...], source_commit: str
) -> list[dict[str, Any]]:
    names = _run_git(root, "ls-tree", "-r", "--name-only", source_commit).splitlines()
    selected = [
        name
        for name in names
        if any(name == item or name.startswith(item.rstrip("/") + "/") for item in critical_paths)
    ]
    for critical in critical_paths:
        if not any(
            name == critical or name.startswith(critical.rstrip("/") + "/") for name in selected
        ):
            raise BaselineError(f"critical path is missing from {source_commit}: {critical}")
    records = []
    for name in selected:
        data = _run_git_bytes(root, "show", f"{source_commit}:{name}")
        mode = _run_git(root, "ls-tree", source_commit, "--", name).split()[0]
        records.append(
            {
                "path": name,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "executable": mode == "100755",
            }
        )
    return records


def _manifest_digest(manifest: dict[str, Any]) -> str:
    body = dict(manifest)
    body.pop("manifest_sha256", None)
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def capture(
    root: Path,
    critical_paths: tuple[str, ...],
    *,
    source_commit: str | None = None,
) -> dict[str, Any]:
    status_lines = [line for line in _run_git(root, "status", "--porcelain=v1").splitlines() if line]
    files = (
        _commit_file_records(root, critical_paths, source_commit)
        if source_commit
        else _file_records(root, critical_paths)
    )
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "kind": "duraloco-baseline",
        "repository_root": str(root.resolve()),
        "git": {
            "commit": _run_git(root, "rev-parse", "HEAD"),
            "branch": _run_git(root, "branch", "--show-current"),
            "dirty": bool(status_lines),
            "status": status_lines,
            "status_sha256": hashlib.sha256("\n".join(status_lines).encode()).hexdigest(),
            "diff_sha256": hashlib.sha256(
                _run_git(root, "diff", "--binary", "--no-ext-diff").encode()
            ).hexdigest(),
        },
        "environment": {
            "hostname": platform.node(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pbs_job_id": os.environ.get("PBS_JOBID"),
            "pbs_nodefile": os.environ.get("PBS_NODEFILE"),
        },
        "critical_paths": list(critical_paths),
        "file_source": {"kind": "git_commit", "commit": source_commit}
        if source_commit
        else {"kind": "worktree"},
        "files": files,
        "counts": {
            "files": len(files),
            "python_modules": sum(
                record["path"].startswith("fs_diloco/") and record["path"].endswith(".py")
                for record in files
            ),
            "tests": sum(record["path"].startswith("tests/") for record in files),
            "configs": sum(record["path"].startswith("configs/") for record in files),
            "pbs_scripts": sum(record["path"].endswith(".pbs") for record in files),
        },
    }
    manifest["manifest_sha256"] = _manifest_digest(manifest)
    return manifest


def verify(root: Path, manifest_path: Path) -> None:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("manifest_sha256") != _manifest_digest(payload):
        raise BaselineError("baseline manifest self-digest mismatch")
    failures: list[str] = []
    for record in payload.get("files", []):
        path = root / record["path"]
        if not path.is_file():
            failures.append(f"missing: {record['path']}")
            continue
        if path.stat().st_size != record["size"]:
            failures.append(f"size: {record['path']}")
        elif _sha256(path) != record["sha256"]:
            failures.append(f"sha256: {record['path']}")
    if failures:
        raise BaselineError("baseline verification failed: " + ", ".join(failures[:20]))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--critical-path", action="append", default=[])
    parser.add_argument("--expect-branch")
    parser.add_argument("--expect-commit")
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument(
        "--source-commit",
        help="hash critical paths from this immutable Git tree while still recording worktree drift",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    try:
        if args.verify:
            verify(root, args.verify)
            return 0
        critical = tuple(args.critical_path) or DEFAULT_CRITICAL_PATHS
        manifest = capture(root, critical, source_commit=args.source_commit)
        git = manifest["git"]
        if args.expect_branch and git["branch"] != args.expect_branch:
            raise BaselineError(f"branch {git['branch']!r} != expected {args.expect_branch!r}")
        if args.expect_commit and git["commit"] != args.expect_commit:
            raise BaselineError(f"commit {git['commit']} != expected {args.expect_commit}")
        if args.require_clean and git["dirty"]:
            raise BaselineError("worktree is dirty")
        if args.output is None:
            json.dump(manifest, sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
            sys.stdout.write("\n")
            return 0
        output = args.output if args.output.is_absolute() else root / args.output
        if output.exists():
            raise BaselineError(f"refusing to overwrite immutable manifest: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return 0
    except (BaselineError, OSError, json.JSONDecodeError) as exc:
        print(f"capture_baseline: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
