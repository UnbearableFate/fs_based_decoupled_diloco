# P07 D8-R2 workflow review — job 2366037

## Preserved failure

- Commit: `4b0def4598aa89342e56fa801fafe26214776a1d`
- Allocation: nine Miyabi nodes; eight learner/LFE members
- Artifact: `artifacts/duraloco/P07/20260712_p07_final_4b0def4_d8`
- Failure manifest: `manifest.json` (`result=fail`, `exit_code=1`)
- Safe authority prefix: four optimizer transitions, two fencing epochs, membership revision one, two committed snapshot pins, and eight complete exact learner capsules
- Fault tape: primary executor loss followed by whole learner/committer-host loss; takeover and reconfiguration both completed

## Stage timings and terminal symptom

| Optimizer transition | Lifecycle seconds | Inventory bytes | Result |
|---:|---:|---:|---|
| 2 | 47.793 | 9,208,951,991 | completed, already longer than the 45-second lease TTL |
| 4 | 72.011 | 18,417,809,135 | completed; the next renewal rejected the expired lease |

The active committer then raised `CoordinationConflict: expired lease cannot be renewed`. No other surviving process had a committer role after the prior whole-host fault, so the workflow could not reach ten transitions. The allocation was terminated after the failure manifest and logs were persisted.

## Root cause

`build_reachability` called `load_capsule` for every marker. That exact-restore API rereads and hashes every model/optimizer/RNG/data component. Eight GPT-2 capsules therefore added approximately 16 GiB of component I/O to every lifecycle mark. Reachability needs the marker, verified manifest ObjectRef, and component ObjectRefs to root objects; it does not need to deserialize component bytes during each mark. Exact restore and the terminal lifecycle report remain responsible for full component validation.

## Repair and retry gate

1. Parse and verify each capsule marker and manifest during reachability, add typed edges to component ObjectRefs, and avoid component payload reads.
2. Prove the repair with a one-node targeted capsule-reachability I/O benchmark on the repaired commit.
3. Rerun the full one-node P07 qualification and the two-node D2-R2 qualification on that same clean commit.
4. Only then authorize one new nine-node D8-R2 attempt. Do not reuse the failed storage root.

The repair changes lifecycle observation cost only. It does not change optimizer, ownership, lease, snapshot, capsule identity, or GC deletion semantics.
