# AGENTS.md

Use the `miyabi-development` Codex skill for all Miyabi-related work.

Do not run training, model loading, CUDA checks, torch imports, transformers imports, datasets preprocessing, `torchrun`, `mpirun`, or pytest runtime tests on Miyabi login nodes. Login nodes are control-plane only: inspect files, edit, run `bash -n`, review configs, submit jobs, inspect logs.

For runtime validation, use PBS interactive/debug or batch compute nodes. Start with 1-node checks, then 2-node checks, then 9-node batch.

This repository implements a filesystem-based Decoupled DiLoCo prototype:

Before submitting PBS scripts, run `bash -n scripts/miyabi/*.pbs` on a safe node. Fill real `#PBS -W group_list=<group_id>` values before submission.

## DuraLoCo phase execution

For DuraLoCo work, read `plans/duraloco/STATE.yaml`, `plans/duraloco/DECISIONS.md`,
`plans/duraloco/BLOCKERS.md`, the current phase report under
`plans/duraloco/phases/`, and the phase plan bundle before editing. M00 is
completed. Treat the committed DuraLoCo log plus its single head CAS as the only
persistent optimizer authority. `latest.json`, checkpoints, telemetry,
heartbeats, and process-local replay memoization are derived or observational.
SQLite and replacement embedded databases are prohibited from active source,
configuration, CLI, scripts, tests, and new artifacts; historical P00-P04
reports are evidence only and must not restore a compatibility runtime.

For P05 and later, also read
`plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/M00_IMPLEMENTATION_LESSONS.md`.
Fresh open, takeover, explicit verification, CAS ambiguity, head jump, or
corruption suspicion must start with empty-cache strict replay. Process-local
verified-object memoization may be used only after a complete successful replay
and must never cross an ownership boundary or be serialized.

Use the phase loop `ORIENT -> SPECIFY/RED -> IMPLEMENT/GREEN -> HARDEN -> CHECK
-> PERSIST`. A phase may be marked completed only when every required
acceptance ID has evidence and an independent checker report says `PASS` (or
`PASS_WITH_FOLLOWUPS` with no required-gate follow-up). Never infer a pass for
an unrun Miyabi check. Do not merge `main` automatically.

After any non-transient 9-node terminal failure, do not immediately resubmit the
same validation shape. Preserve the failure manifest and stage timings, write a
workflow or root-cause review, prove the proposed repair with the smallest
targeted compute benchmark, and rerun the 1-node then 2-node qualification on
the same clean commit before one new 9-node attempt.
