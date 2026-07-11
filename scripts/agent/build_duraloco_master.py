#!/usr/bin/env python3
"""Build or check the canonical DuraLoCo master plan from ordered source plans."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys


SOURCES = (
    "README.md",
    "00_CODEX_LOOP_OPERATING_CONTRACT.md",
    "SQLITE_FREE_SYSTEM_DESIGN.md",
    "P00_P04_IMPLEMENTATION_LESSONS.md",
    "01_P00_BASELINE_AND_RESEARCH_CONTRACT.md",
    "02_P01_PROTOCOL_V2_SCHEMAS_AND_VALIDATION.md",
    "03_P02_REFERENCE_SIMULATOR_AND_IN_MEMORY_BACKEND.md",
    "04_P03_STORAGE_ABSTRACTION_AND_POSIX_LUSTRE_CONTRACT.md",
    "05_P04_TRANSACTIONAL_FRAGMENT_LOG_AND_PREFIX_RECOVERY.md",
    "06_M00_SQLITE_FREE_RUNTIME_REBASE_AND_P00_P04_REQUALIFICATION.md",
    "M00_IMPLEMENTATION_LESSONS.md",
    "07_P05_SYNCER_LEASE_FENCING_AND_FAILOVER.md",
    "08_P06_LEARNER_INTERVALS_ADOPTION_AND_RECOVERY.md",
    "09_P07_COMPACTION_GC_ACKS_AND_LEARNER_CAPSULES.md",
    "10_P08_DIRECT_FRAGMENT_IO_STREAMING_REDUCER_AND_TELEMETRY.md",
    "11_P10_SACC_AND_ALGORITHM_SYSTEM_CODESIGN.md",
    "12_P11_MIYABI_INTEGRATION_CHAOS_AND_9NODE_ACCEPTANCE.md",
    "13_P12_FORMAL_EXPERIMENTS_ARTIFACT_AND_PAPER_EVIDENCE.md",
    "14_P09_OBJECT_STORE_BACKEND_AND_HYBRID_BASELINE_OPTIONAL.md",
)
OUTPUT = "DuraLoCo_Codex_Master_Plan.md"
CHECKSUM_OUTPUT = "SHA256SUMS.txt"
SEPARATOR = "\n\n---\n\n"
CHECKSUM_SOURCES = (
    "00_CODEX_LOOP_OPERATING_CONTRACT.md",
    "01_P00_BASELINE_AND_RESEARCH_CONTRACT.md",
    "02_P01_PROTOCOL_V2_SCHEMAS_AND_VALIDATION.md",
    "03_P02_REFERENCE_SIMULATOR_AND_IN_MEMORY_BACKEND.md",
    "04_P03_STORAGE_ABSTRACTION_AND_POSIX_LUSTRE_CONTRACT.md",
    "05_P04_TRANSACTIONAL_FRAGMENT_LOG_AND_PREFIX_RECOVERY.md",
    "06_M00_SQLITE_FREE_RUNTIME_REBASE_AND_P00_P04_REQUALIFICATION.md",
    "07_P05_SYNCER_LEASE_FENCING_AND_FAILOVER.md",
    "08_P06_LEARNER_INTERVALS_ADOPTION_AND_RECOVERY.md",
    "09_P07_COMPACTION_GC_ACKS_AND_LEARNER_CAPSULES.md",
    "10_P08_DIRECT_FRAGMENT_IO_STREAMING_REDUCER_AND_TELEMETRY.md",
    "11_P10_SACC_AND_ALGORITHM_SYSTEM_CODESIGN.md",
    "12_P11_MIYABI_INTEGRATION_CHAOS_AND_9NODE_ACCEPTANCE.md",
    "13_P12_FORMAL_EXPERIMENTS_ARTIFACT_AND_PAPER_EVIDENCE.md",
    "14_P09_OBJECT_STORE_BACKEND_AND_HYBRID_BASELINE_OPTIONAL.md",
    OUTPUT,
    "M00_IMPLEMENTATION_LESSONS.md",
    "P00_P04_IMPLEMENTATION_LESSONS.md",
    "README.md",
    "SQLITE_FREE_SYSTEM_DESIGN.md",
    "references/DuraLoCo_research_draft_zh.md",
    "templates/BLOCKER.md",
    "templates/PHASE_REPORT.md",
    "templates/PHASE_STATE.yaml",
    "templates/RUN_MANIFEST.json",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    default_bundle = (
        Path(__file__).resolve().parents[2]
        / "plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans"
    )
    parser.add_argument("--bundle", type=Path, default=default_bundle)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def render(bundle: Path) -> str:
    return SEPARATOR.join(
        (bundle / relative).read_text(encoding="utf-8") for relative in SOURCES
    )


def render_checksums(bundle: Path) -> str:
    lines = []
    for relative in CHECKSUM_SOURCES:
        digest = hashlib.sha256((bundle / relative).read_bytes()).hexdigest()
        lines.append(f"{digest}  {relative}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    bundle = args.bundle.resolve()
    output = bundle / OUTPUT
    checksums = bundle / CHECKSUM_OUTPUT
    try:
        rendered = render(bundle)
        if args.check:
            if not output.is_file() or output.read_text(encoding="utf-8") != rendered:
                print(f"master plan is stale: {output}", file=sys.stderr)
                return 2
            expected_checksums = render_checksums(bundle)
            if (
                not checksums.is_file()
                or checksums.read_text(encoding="utf-8") != expected_checksums
            ):
                print(f"plan checksums are stale: {checksums}", file=sys.stderr)
                return 2
            return 0
        output.write_text(rendered, encoding="utf-8")
        checksums.write_text(render_checksums(bundle), encoding="utf-8")
        return 0
    except OSError as exc:
        print(f"build_duraloco_master: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
