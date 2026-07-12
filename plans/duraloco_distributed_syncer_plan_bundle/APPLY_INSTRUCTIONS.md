# Apply Instructions

1. Start from a clean or intentionally preserved checkout of `fs_based_decoupled_diloco`.
2. Back up the existing `plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans` directory.
3. Copy the directory under `repo_patch/plans/...` into the same repository-relative location.
4. Replace `scripts/agent/build_duraloco_master.py` with the supplied version.
5. Do not replace `plans/duraloco/STATE.yaml`, `DECISIONS.md` or `BLOCKERS.md`.
6. Run `python3 scripts/agent/build_duraloco_master.py --check` and
   `sha256sum -c SHA256SUMS.txt`.
7. Review `CURRENT_REPOSITORY_ALIGNMENT_REVIEW.md`, `PLAN_REWRITE_CHANGELOG.md`,
   `DISTRIBUTED_SYNCER_SYSTEM_DESIGN.md`, the P07 completion addendum, and the P08 readiness update
   before resuming Codex.
8. Keep the completed P07 A01–A24 verdict unchanged and start P08 from verified commit `c099adc`.
   Preserve the P07 lifecycle contract; P10 becomes eligible only after P08 and its P07 regressions.
9. Reconcile only live route fields if the target repository still has stale state: keep
   `phase: P07`, `status: completed`, all checks/acceptance/evidence and Checker report unchanged,
   and set `next_action` to the P08 profile-first loop. Record this as a plan-route handoff, not a
   new P07 runtime pass.

The bundle does not modify or push the GitHub repository by itself.
