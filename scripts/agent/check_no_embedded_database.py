#!/usr/bin/env python3
"""Fail closed when active runtime surfaces retain an embedded-database dependency."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


ACTIVE_ROOTS = (
    "fs_diloco",
    "configs",
    "scripts",
    "tests",
    "README.md",
    "docs/miyabi_runbook.md",
    "docs/experiments.md",
    "docs/user-guide",
    "docs/duraloco/transaction_log.md",
    "docs/duraloco/migration_map.md",
)
TEXT_SUFFIXES = {".py", ".sql", ".yaml", ".yml", ".toml", ".sh", ".pbs", ".md", ".json"}
SELF = Path("scripts/agent/check_no_embedded_database.py")
REJECTION_FIXTURE = Path("tests/test_removed_config_keys.py")


def _patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    engine = "sql" + "ite"
    dump_key = "d" + "b_dump"
    return (
        ("engine import", re.compile(rf"\b{engine}3\b", re.IGNORECASE)),
        ("legacy store", re.compile(rf"\b{engine}_store\b", re.IGNORECASE)),
        ("legacy schema", re.compile(rf"\bschema\.{engine}\b", re.IGNORECASE)),
        ("dump surface", re.compile(rf"\b(?:resume_)?{dump_key}\w*\b", re.IGNORECASE)),
        ("local engine path", re.compile(rf"\b{engine}_local_dir\b", re.IGNORECASE)),
        ("legacy command option", re.compile(rf"--{engine}-local-dir\b", re.IGNORECASE)),
        ("legacy rebuild command", re.compile(r"\brebuild-cache\b", re.IGNORECASE)),
        ("database artifact", re.compile(rf"\.(?:{engine}|{engine}3|d" + r"b)\b", re.IGNORECASE)),
    )


def _files(root: Path):
    for raw in ACTIVE_ROOTS:
        path = root / raw
        if path.is_file():
            yield path
        elif path.is_dir():
            for candidate in path.rglob("*"):
                if candidate.is_file() and candidate.suffix.lower() in TEXT_SUFFIXES:
                    yield candidate


def check(root: Path) -> dict[str, object]:
    findings: list[dict[str, object]] = []
    scanned = 0
    for path in sorted(set(_files(root))):
        relative = path.relative_to(root)
        if relative in {SELF, REJECTION_FIXTURE}:
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for name, pattern in _patterns():
                if pattern.search(line):
                    findings.append(
                        {
                            "path": relative.as_posix(),
                            "line": line_number,
                            "rule": name,
                            "text": line.strip()[:240],
                        }
                    )
    return {
        "status": "PASS" if not findings else "FAIL",
        "scanned_files": scanned,
        "finding_count": len(findings),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = check(args.root.resolve())
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
