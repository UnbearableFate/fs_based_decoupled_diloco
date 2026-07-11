#!/usr/bin/env python3
"""Check frozen DuraLoCo terms, invariant IDs, owners, and P0 traceability."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


REQUIRED_TERMS = (
    "Proposal",
    "Commit",
    "Frontier",
    "Head",
    "Logical inclusion",
    "Global exact recovery",
    "Warm learner restart",
    "Exact learner restart",
)
REQUIRED_INVARIANTS = {f"I-{number:03d}" for number in range(1, 13)}
REQUIRED_CLAIMS = {f"P0-C{number:03d}" for number in range(1, 13)}


def _links(path: Path, text: str) -> list[str]:
    failures = []
    for target in re.findall(r"\[[^]]+\]\(([^)#]+)(?:#[^)]+)?\)", text):
        if "://" in target or target.startswith("mailto:"):
            continue
        if not (path.parent / target).exists():
            failures.append(target)
    return failures


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    contract_path = root / "docs/duraloco/research_contract.md"
    invariant_path = root / "docs/duraloco/invariants.md"
    trace_path = root / "plans/duraloco/TRACEABILITY.md"
    failures: list[str] = []
    try:
        contract = contract_path.read_text(encoding="utf-8")
        invariants = invariant_path.read_text(encoding="utf-8")
        traceability = trace_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"check_research_contract: {exc}", file=sys.stderr)
        return 2
    for term in REQUIRED_TERMS:
        if term.casefold() not in contract.casefold():
            failures.append(f"missing term: {term}")
    invariant_rows = [line for line in invariants.splitlines() if re.match(r"\| I-\d{3} \|", line)]
    found_invariants = [re.search(r"I-\d{3}", line).group(0) for line in invariant_rows]
    if len(found_invariants) != len(set(found_invariants)):
        failures.append("duplicate invariant ID")
    if set(found_invariants) != REQUIRED_INVARIANTS:
        failures.append(
            f"invariant set differs: missing={sorted(REQUIRED_INVARIANTS - set(found_invariants))} "
            f"extra={sorted(set(found_invariants) - REQUIRED_INVARIANTS)}"
        )
    for line in invariants.splitlines():
        if re.match(r"\| I-\d{3} \|", line) and "`tests/" not in line:
            failures.append(f"invariant has no future test owner: {line}")
    found_claims = set(re.findall(r"\bP0-C\d{3}\b", traceability))
    if found_claims != REQUIRED_CLAIMS:
        failures.append(
            f"P0 claim set differs: missing={sorted(REQUIRED_CLAIMS - found_claims)} "
            f"extra={sorted(found_claims - REQUIRED_CLAIMS)}"
        )
    for path, text in (
        (contract_path, contract),
        (invariant_path, invariants),
        (trace_path, traceability),
    ):
        failures.extend(f"broken link in {path.relative_to(root)}: {item}" for item in _links(path, text))
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
