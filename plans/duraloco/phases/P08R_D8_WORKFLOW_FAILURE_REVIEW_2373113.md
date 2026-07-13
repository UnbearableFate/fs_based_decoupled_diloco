# P08R D8 rerun startup failure review — PBS 2373113

## Classification

PBS `2373113.opbs` was a matched factor-one rerun requested after P08R
completion to measure the qualified snapshot-suffix repair end to end. It used
clean commit `ac2d961f148841b14ba7bc628ce1566695571bf0`, requested exactly eight
learner nodes, and terminated before runtime setup. This is a deterministic
workflow failure, not a training, authority, replay, MPI, CUDA, or performance
failure. No immediate eight-node resubmission is authorized.

## Preserved evidence

- PBS state: `F`, exit status `2`, wall time `00:00:01`;
- allocation: eight nodes and eight GPUs, with zero GPU utilization and zero
  GPU memory use;
- preserved joined PBS output:
  `/work/xg24i002/x10041/duraloco_worktrees/p08r-rerun-ac2d961/duraloco_p08r_d8.o2373113`;
- scheduler accounting: `qstat -f -H 2373113.opbs` and `tracejob 2373113`;
- no authority namespace, model load, worker launch, optimizer transition, or
  timing experiment began.

The wrapper failed before creating `ARTIFACT_ROOT` and before installing its
EXIT trap. Consequently no manifest or stage-timing artifact could be emitted.
The PBS output and accounting above are the complete available failure record.

## Confirmed root cause

The detached clean worktree contained `artifacts/duraloco` but not its untracked
`P08R` child. The wrapper called non-recursive `mkdir "$STORAGE_ROOT"` without
first creating the caller-independent parent. `mkdir` returned `ENOENT`; the
wrapper then used its generic reused-root error for that unrelated failure and
exited with status 2.

This defect affects both final wrappers because both made the same assumption.
It had remained hidden when earlier worktrees already contained the untracked
parent directory.

## Repair and retry gate

Both D8 wrappers create only the two parent directories recursively, then retain
the existing non-recursive atomic `mkdir` calls for the caller-supplied leaf
roots. Reusing either experiment root therefore still fails before authority
access, preserving D-0818, while a clean worktree no longer depends on an
untracked directory.

Before another eight-node attempt:

1. run shell syntax checks and the wrapper contract test;
2. rerun the real historical snapshot-suffix benchmark on one compute node;
3. rerun the full one-node suite, D1, and D2 on the same clean commit;
4. run one matched factor-one experiment on that commit;
5. only after it passes, run one repaired D8-R2 experiment on the same commit.

Every namespace must be fresh, and no ninth node is authorized.

## Qualification and retry outcome

The repair gate passed on clean commit
`8ebece36bd65c75ffb2b0b057d1f36e42cebcb1a`: targeted real-prefix PBS
`2373361`, full one-node PBS `2373379` (526 passed, one skipped), D1 PBS
`2373399`, and D2 PBS `2373419` all passed. Matched factor-one PBS `2373434`
then passed in `335.535577393` seconds. The single authorized repaired D8-R2
PBS `2373631` passed in `410.779549171` seconds, using exactly eight nodes and
retaining every fault, lifecycle, terminal-strict, interference, and regression
gate. The detailed comparison is in
`P08R_D8R2_REPAIRED_RERUN_2373631.md`.
