# Apply Instructions

1. Start from a clean or intentionally preserved checkout of `fs_based_decoupled_diloco`.
2. Back up the existing `plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans` directory.
3. Copy the directory under `repo_patch/plans/...` into the same repository-relative location.
4. Replace `scripts/agent/build_duraloco_master.py` with the supplied version.
5. Do not replace `plans/duraloco/STATE.yaml`, `DECISIONS.md` or `BLOCKERS.md`.
6. Run `python3 scripts/agent/build_duraloco_master.py --check` and
   `sha256sum -c SHA256SUMS.txt`.
7. Review `CURRENT_REPOSITORY_ALIGNMENT_REVIEW.md`, `PLAN_REWRITE_CHANGELOG.md`,
   `DISTRIBUTED_SYNCER_SYSTEM_DESIGN.md` and the P06A handoff before resuming Codex.
8. Keep the completed P06 A01–A20 verdict unchanged and start P06A from archive commit `06e3ca2`.
   P07 becomes eligible only after P06C; P08 becomes eligible only after P07.
9. Reconcile only the live route fields in `plans/duraloco/STATE.yaml`: keep `phase: P06`,
   `status: completed`, all checks/acceptance/evidence and Checker report unchanged, but replace the
   stale `next_action: start P07 and P08 independently...` with `start P06A from archive commit
   06e3ca2 using the verified P06 evidence baseline`. Record this as a plan-route handoff, not a new
   P06 runtime pass.

The bundle does not modify or push the GitHub repository by itself.
