# DuraLoCo Distributed-Syncer Plan Rewrite Bundle

Version: 3.1
Date: 2026-07-11
Basis commit: `main@06e3ca2299d5eb1a720c1d8f9107af5223095525`
Planning transition: P06 completed → P06A/P06B/P06C distributed-syncer route

## Contents

```text
repo_patch/
  plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/
    README.md
    DuraLoCo_Codex_Master_Plan.md
    DISTRIBUTED_SYNCER_SYSTEM_DESIGN.md
    RESEARCH_RELATED_WORK_AND_DIFFERENTIATION.md
    PLAN_REWRITE_CHANGELOG.md
    CURRENT_REPOSITORY_ALIGNMENT_REVIEW.md
    08_P06_...
    08A_P06A_...
    08B_P06B_...
    08C_P06C_...
    09_P07_... through 14_P09_...
    templates/
    SHA256SUMS.txt
  scripts/agent/build_duraloco_master.py
tools/
  build_duraloco_master.py
verify_package.sh
PACKAGE_SHA256SUMS.txt
```

Historical P00–P06 plans, reports and implementation lessons remain authoritative. P06 is already
complete with A01–A20; this bundle does not retrofit A21–A25. P06A builds the missing Central
Reference Syncer characterization bundle and decomposes the current syncer without changing
topology. P06B establishes a new-generation no-dedicated-syncer D8 path with replication factor 1;
P06C adds overlapping ownership, hedged execution and committed failover. P07→P08→P10 is
sequential so shared schemas evolve under one verified baseline.

## Apply to a repository checkout

From the extracted bundle root, replace the plan directory and build script in a clean checkout:

```bash
REPO=/path/to/fs_based_decoupled_diloco

cp -a "$REPO/plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans" \
  "$REPO/plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans.backup.$(date +%Y%m%d%H%M%S)"

rm -rf "$REPO/plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans"
cp -a repo_patch/plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans \
  "$REPO/plans/duraloco/codex/"
cp repo_patch/scripts/agent/build_duraloco_master.py \
  "$REPO/scripts/agent/build_duraloco_master.py"

python3 "$REPO/scripts/agent/build_duraloco_master.py" --check
(
  cd "$REPO/plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans"
  sha256sum -c SHA256SUMS.txt
)
```

Do not overwrite the repository-level runtime files `plans/duraloco/STATE.yaml`, `DECISIONS.md` or `BLOCKERS.md`. They should be updated by Codex as work proceeds.

## Current execution instruction

P06 is complete in the current repository. Do not alter its verdict. Start P06A from archive commit
`06e3ca2`, use `2581a4d` as the verified implementation reference and `030129e` as the Checker/
persistence evidence, and create the CRS characterization traces in P06A Loop 1. After applying the
bundle, update only the live `STATE.yaml` route fields so its stale P07/P08 next action points to P06A;
preserve all P06 checks, acceptance IDs and evidence.

## Verify this package

```bash
./verify_package.sh
```

The script validates the generated master plan, route invariants, internal plan checksums and the package-level checksum list.
