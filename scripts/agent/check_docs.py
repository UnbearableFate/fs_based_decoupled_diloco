#!/usr/bin/env python3
"""Audit current documentation links, retired paths, invariant owners, and stale claims."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


RETIRED_PATHS = (
    "docs/USER_GUIDE.zh-en.md",
    "docs/design.md",
    "docs/experiments.md",
    "docs/miyabi_runbook.md",
    "docs/duraloco/drift_report.md",
    "docs/duraloco/p03_drift_report.md",
)

CURRENT_DOCS = (
    "README.md",
    "docs/README.md",
    "docs/status.md",
    "docs/user-guide",
    "docs/duraloco/architecture.md",
    "docs/duraloco/failure_model.md",
    "docs/duraloco/invariants.md",
    "docs/duraloco/lifecycle.md",
    "docs/duraloco/migration_map.md",
    "docs/duraloco/numeric_contract.md",
    "docs/duraloco/protocol_v2.md",
    "docs/duraloco/reference_model.md",
    "docs/duraloco/research_contract.md",
    "docs/duraloco/storage_contract.md",
    "docs/duraloco/transaction_log.md",
    "docs/reviews/20260712_code_review.md",
)

STALE_CLAIMS = (
    "one GPU-backed syncer process",
    "syncer-local SQLite",
    "failover is not yet claimed",
    "exact learner restart is a later lifecycle feature",
    "P07 compaction",
)

LINK_PATTERN = re.compile(r"\[[^]]+\]\(([^)]+)\)")
TEST_OWNER_PATTERN = re.compile(r"`(tests/[^`]+\.py)`")


def _markdown_files(root: Path) -> tuple[Path, ...]:
    files: set[Path] = set()
    for raw in CURRENT_DOCS:
        path = root / raw
        if path.is_file():
            files.add(path)
        elif path.is_dir():
            files.update(item for item in path.rglob("*.md") if item.is_file())
    return tuple(sorted(files))


def _link_target(path: Path, target: str) -> Path | None:
    target = target.strip()
    if not target or target.startswith(("#", "mailto:")) or "://" in target:
        return None
    without_anchor = target.split("#", 1)[0]
    if not without_anchor:
        return None
    return (path.parent / without_anchor).resolve()


def check(root: Path) -> list[str]:
    failures: list[str] = []
    current_files = _markdown_files(root)
    all_files = tuple(sorted({root / "README.md", *(root / "docs").rglob("*.md")}))
    if not current_files:
        return ["no current documentation files found"]

    for raw in RETIRED_PATHS:
        if (root / raw).exists():
            failures.append(f"retired documentation still exists: {raw}")
    old_guides = sorted((root / "docs/user-guide").glob("[0-9][0-9]-*.zh-en.md"))
    failures.extend(
        f"retired numbered user guide still exists: {path.relative_to(root)}"
        for path in old_guides
    )

    for path in all_files:
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(root)
        for match in LINK_PATTERN.finditer(text):
            target = _link_target(path, match.group(1))
            if target is not None and not target.exists():
                failures.append(f"broken link in {relative}: {match.group(1)}")
    for path in current_files:
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(root)
        for stale in STALE_CLAIMS:
            if stale.casefold() in text.casefold():
                failures.append(f"stale claim in {relative}: {stale}")

    invariants = root / "docs/duraloco/invariants.md"
    invariant_text = invariants.read_text(encoding="utf-8")
    for owner in TEST_OWNER_PATTERN.findall(invariant_text):
        if not (root / owner).is_file():
            failures.append(f"missing invariant test owner: {owner}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    failures = check(args.root.resolve())
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 2
    print("check_docs: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
