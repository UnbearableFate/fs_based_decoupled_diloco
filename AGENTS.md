# AGENTS.md

Use the `miyabi-development` Codex skill for all Miyabi-related work.

Do not run training, model loading, CUDA checks, torch imports, transformers imports, datasets preprocessing, `torchrun`, `mpirun`, or pytest runtime tests on Miyabi login nodes. Login nodes are control-plane only: inspect files, edit, run `bash -n`, review configs, submit jobs, inspect logs.

For runtime validation, use PBS interactive/debug or batch compute nodes. Start with 1-node checks, then 2-node checks, then 9-node batch.

This repository implements a filesystem-based Decoupled DiLoCo prototype:

Before submitting PBS scripts, run `bash -n scripts/miyabi/*.pbs` on a safe node. Fill real `#PBS -W group_list=<group_id>` values before submission.

## DuraLoCo phase execution

For DuraLoCo work, read `plans/duraloco/STATE.yaml`, `plans/duraloco/DECISIONS.md`,
`plans/duraloco/BLOCKERS.md`, the current phase report under
`plans/duraloco/phases/`, and the phase plan bundle before editing. Treat the
committed DuraLoCo log as the target authority; legacy `latest.json` and SQLite
state remain compatibility baselines until a later phase explicitly promotes
Protocol v2.

Use the phase loop `ORIENT -> SPECIFY/RED -> IMPLEMENT/GREEN -> HARDEN -> CHECK
-> PERSIST`. A phase may be marked completed only when every required
acceptance ID has evidence and an independent checker report says `PASS` (or
`PASS_WITH_FOLLOWUPS` with no required-gate follow-up). Never infer a pass for
an unrun Miyabi check. Do not merge `main` automatically.
