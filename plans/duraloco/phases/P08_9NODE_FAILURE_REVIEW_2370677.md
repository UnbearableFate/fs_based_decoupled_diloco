# P08 D8 factor-one root-cause review — PBS 2370677

## Classification

- Shape: optimized D8 factor-one GPT-2/WikiText-2 50x10.
- Clean commit: `a01b18bfe43049be700c21c05d6863821f5c42b9`.
- Result: non-transient runtime failure after four optimizer transitions.
- Authority: the run committed a truthful error stop at sequence 6 with four
  optimizer transitions; the namespace is terminal and will not be reused.

PBS first rejected one candidate allocation because two nodes failed its GPU
memory prologue, then started a replacement allocation. That pre-runtime retry
did not touch authority. The replacement runtime failure is independent and
reproducible from its causal stage trace.

## Preserved evidence

- `artifacts/duraloco/P08/20260713_p08_d8_a01b18b_r1/manifest.json`
- `artifacts/duraloco/P08/20260713_p08_d8_a01b18b_r1_storage/training/`
- `artifacts/duraloco/P08/20260713_p08_d8_a01b18b_r1/member-001_committer.log`
- `duraloco_p08_d8.o2370677`
- `tracejob 2370677.opbs`

## Stage timing and root cause

Publish-to-commit grew 21.240 → 31.368 → 41.845 → 52.292 seconds. On the
fourth work order the committer-local spans were 8.042 seconds waiting for the
executor, 1.365 seconds validating the winner, and 19.961 seconds preparing the
successor; post-CAS replay supplied the remaining growth. The existing
heartbeat helper covered executor-result wait, but not winner validation,
successor preparation, or post-CAS replay. The next loop renewal therefore
correctly rejected the expired 45-second lease. The stale process then used the
old unguarded finalizer to commit an error stop, the distributed analogue of
P08-E019/P08-E020.

## Repair and retry gate

Use the existing main-thread lease heartbeat helper for winner validation,
immutable successor preparation, and read-only post-CAS replay. Require a
final renewal immediately before optimizer CAS. Split distributed stop into
guarded prepare, final renewal, caller-thread CAS, and guarded replay. A process
that loses lease authority cannot commit stop.

Before one fresh D8 attempt, run the dedicated targeted guard benchmark/tests,
the complete one-node gates, and D2 on one clean commit. Do not submit R2 until
factor one passes and produces ten complete raw timelines.
