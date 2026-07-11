#!/usr/bin/env python3
"""Build, lint, or check the canonical DuraLoCo master plan."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

SOURCES = (
    "README.md",
    "00_CODEX_LOOP_OPERATING_CONTRACT.md",
    "SQLITE_FREE_SYSTEM_DESIGN.md",
    "DISTRIBUTED_SYNCER_SYSTEM_DESIGN.md",
    "CURRENT_REPOSITORY_ALIGNMENT_REVIEW.md",
    "RESEARCH_RELATED_WORK_AND_DIFFERENTIATION.md",
    "PLAN_REWRITE_CHANGELOG.md",
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
    "08A_P06A_SYNCER_DECOMPOSITION_AND_REFERENCE_EQUIVALENCE.md",
    "08B_P06B_LEARNER_HOSTED_FRAGMENT_EXECUTORS_AND_DISTRIBUTED_PREPARE.md",
    "08C_P06C_REDUNDANT_FRAGMENT_OWNERSHIP_AND_FAILOVER.md",
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

CHECKSUM_SOURCES = tuple(
    sorted(
        set(SOURCES)
        | {
            OUTPUT,
            "references/DuraLoCo_research_draft_zh.md",
            "templates/BLOCKER.md",
            "templates/FAULT_MATRIX.csv",
            "templates/PHASE_REPORT.md",
            "templates/PHASE_STATE.yaml",
            "templates/RUN_MANIFEST.json",
        }
    )
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    default_bundle = (
        Path(__file__).resolve().parents[2]
        / "plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans"
    )
    parser.add_argument("--bundle", type=Path, default=default_bundle)
    parser.add_argument("--check", action="store_true", help="fail if generated files are stale")
    parser.add_argument("--lint", action="store_true", help="run route/invariant lint without writing")
    parser.add_argument("--print-sources", action="store_true")
    return parser.parse_args(argv)


def read_required(bundle: Path, relative: str) -> str:
    path = bundle / relative
    if not path.is_file():
        raise OSError(f"missing required plan source: {path}")
    return path.read_text(encoding="utf-8")


def render(bundle: Path) -> str:
    return SEPARATOR.join(read_required(bundle, relative).rstrip() for relative in SOURCES) + "\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_checksums(bundle: Path) -> str:
    lines: list[str] = []
    for relative in CHECKSUM_SOURCES:
        path = bundle / relative
        if not path.is_file():
            raise OSError(f"missing checksum source: {path}")
        lines.append(f"{sha256(path)}  {relative}")
    return "\n".join(lines) + "\n"


def lint(bundle: Path) -> list[str]:
    errors: list[str] = []
    texts = {relative: read_required(bundle, relative) for relative in SOURCES}

    required_route = "M00 → P05 → P06 → P06A → P06B → P06C → P07 → P08 → P10"
    if required_route not in texts["README.md"]:
        errors.append("README does not contain the distributed-syncer route")

    p06 = texts["08_P06_LEARNER_INTERVALS_ADOPTION_AND_RECOVERY.md"]
    if 'status: "completed_in_repository"' not in p06:
        errors.append("P06 is not aligned to the completed repository state")
    if "P06-A20" not in p06 or "- [ ] P06-A21" in p06:
        errors.append("P06 acceptance must remain the archived A01-A20 set")

    p06a = texts["08A_P06A_SYNCER_DECOMPOSITION_AND_REFERENCE_EQUIVALENCE.md"]
    if "不得改变生产拓扑" not in p06a:
        errors.append("P06A lacks the no-topology-change guard")
    for token in ("06e3ca2", "P06-A01–A20", "ProposalCatalog", "ProductionTransactionalLog"):
        if token not in p06a:
            errors.append(f"P06A missing current-repository anchor: {token}")

    p06b = texts["08B_P06B_LEARNER_HOSTED_FRAGMENT_EXECUTORS_AND_DISTRIBUTED_PREPARE.md"]
    for token in ("prepare-only", "single global head", "dedicated_syncer_nodes=0"):
        if token not in p06b:
            errors.append(f"P06B missing invariant token: {token}")

    p06c = texts["08C_P06C_REDUNDANT_FRAGMENT_OWNERSHIP_AND_FAILOVER.md"]
    for token in ("same-FWO divergent", "committed reconfiguration", "optimizer-state transfer"):
        if token not in p06c:
            errors.append(f"P06C missing redundancy invariant token: {token}")

    for relative in (
        "09_P07_COMPACTION_GC_ACKS_AND_LEARNER_CAPSULES.md",
    ):
        if '  - "P06C"' not in texts[relative]:
            errors.append(f"{relative} must depend on P06C")

    p08 = texts["10_P08_DIRECT_FRAGMENT_IO_STREAMING_REDUCER_AND_TELEMETRY.md"]
    if '  - "P07"' not in p08 or '  - "P06C"' in p08:
        errors.append("P08 must start sequentially from P07")

    p10 = texts["11_P10_SACC_AND_ALGORITHM_SYSTEM_CODESIGN.md"]
    if '  - "P08"' not in p10 or "system-only" not in p10 or "not_qualified" not in p10:
        errors.append("P10 must depend on P08 and keep the system-only-first tier")

    alignment = texts["CURRENT_REPOSITORY_ALIGNMENT_REVIEW.md"]
    for token in ("06e3ca2", "2581a4d", "030129e", "P06-A01`–`P06-A20"):
        if token not in alignment:
            errors.append(f"alignment review missing current evidence anchor: {token}")

    p11 = texts["12_P11_MIYABI_INTEGRATION_CHAOS_AND_9NODE_ACCEPTANCE.md"]
    if "0 dedicated syncer" not in p11 and "零专用syncer" not in p11:
        errors.append("P11 lacks a no-dedicated-syncer primary acceptance")

    p12 = texts["13_P12_FORMAL_EXPERIMENTS_ARTIFACT_AND_PAPER_EVIDENCE.md"]
    for baseline in ("C9", "C9-HA", "D8", "D8-R2"):
        if baseline not in p12:
            errors.append(f"P12 missing baseline {baseline}")

    design = texts["DISTRIBUTED_SYNCER_SYSTEM_DESIGN.md"]
    for invariant in ("Single authority", "At-most-one logical commit", "No local authority"):
        if invariant not in design:
            errors.append(f"distributed design missing invariant: {invariant}")

    related = texts["RESEARCH_RELATED_WORK_AND_DIFFERENTIATION.md"]
    for work in ("Decoupled DiLoCo", "GradsSharding", "BatchWeave", "Parameter Server"):
        if work not in related:
            errors.append(f"related-work document missing: {work}")

    return errors


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    bundle = args.bundle.resolve()
    output = bundle / OUTPUT
    checksums = bundle / CHECKSUM_OUTPUT

    try:
        if args.print_sources:
            print("\n".join(SOURCES))

        errors = lint(bundle)
        if errors:
            for error in errors:
                print(f"lint: {error}", file=sys.stderr)
            return 2
        if args.lint and not args.check:
            return 0

        rendered = render(bundle)
        if args.check:
            if not output.is_file() or output.read_text(encoding="utf-8") != rendered:
                print(f"master plan is stale: {output}", file=sys.stderr)
                return 2
            expected_checksums = render_checksums(bundle)
            if not checksums.is_file() or checksums.read_text(encoding="utf-8") != expected_checksums:
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
