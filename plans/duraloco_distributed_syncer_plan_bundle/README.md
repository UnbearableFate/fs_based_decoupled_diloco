# DuraLoCo Distributed-Syncer Plan Rewrite Bundle

Version: 3.2
Date: 2026-07-12
Basis commit: `codex/duraloco-p07-distributed-lifecycle@c099adc3c3a99127569a7d9bf38a58547022173c`
Planning transition: P07 completed → P08 profile-first distributed performance route

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

Historical P00–P06 plans, reports, and implementation lessons remain authoritative. P06A, P06B,
P06C, and P07 are now completed. P07-A01–A24 passed on the distributed R2 lifecycle path; its
independent Checker ran as PBS `2369002.opbs` against `c099adc`. P08 is now ready and remains
sequential so performance work preserves one verified lifecycle schema and authority baseline.

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

P07 is complete in the current repository. Do not alter its verdict. Start P08 sequentially from
`c099adc`, retain `2295467` as the qualified lifecycle runtime and PBS `2368976`/`2369002` as the
report/Checker evidence, and execute P08 Loop 1 as a profile-first gate. Preserve the single global
head, strict replay, two-snapshot retention, typed reachability, guarded GC, exact-capsule, and
long-substage lease-heartbeat contracts. Do not implement bundling unless the preregistered profile
gate triggers.

## Verify this package

```bash
./verify_package.sh
```

The script validates the generated master plan, route invariants, internal plan checksums and the package-level checksum list.
