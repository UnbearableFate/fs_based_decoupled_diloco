# P07 D8-R2 retry workflow review — job 2366101

## Preserved failure

- Commit: `287a7796aa893dfcb0cc513c7c195cb09739f3fb`
- Artifact: `artifacts/duraloco/P07/20260712_p07_retry_287a779_d8`
- Qualification chain: targeted job 2366075, unit job 2366079, D1 job 2366080, D2-R2 job 2366091
- Safe authority prefix: four optimizer transitions, two fencing epochs, membership revision one, two snapshots, and eight exact capsules
- Failure manifest: `manifest.json` (`result=fail`, `exit_code=1`)

## Result of the first repair

The metadata-only reachability repair passed its targeted I/O test and removed capsule component reads from GC graph construction. It did not make the complete lifecycle transaction shorter than the lease:

| Optimizer transition | Lifecycle seconds | Inventory bytes | Result |
|---:|---:|---:|---|
| 2 | 46.345 | 9,208,952,113 | completed |
| 4 | 69.733 | 18,417,809,257 | completed; subsequent renewal rejected the expired lease |

The remaining time is distributed across snapshot publication, accelerated replay, empty-cache strict replay, mark/reachability, and inventory measurement. Treating the whole sequence as one non-renewable stage is therefore the defect; optimizing one reader cannot establish a safe upper bound as history and tensor bytes grow.

## Second repair and gate

Renew the same fenced lease between every durable/read-only lifecycle substage: after snapshot commit, after accelerated replay, after strict replay, after mark/reachability, and after inventory measurement. No background thread or new authority is introduced. Each renewal still uses the same owner/session/epoch and fails closed if ownership changed.

Before another nine-node attempt:

1. Run a one-node real GPT-2 lifecycle benchmark and require the new renewal-stage events.
2. Run the full one-node unit gate and two-node D2-R2 on the same clean commit.
3. Preserve all manifests and authorize one new nine-node attempt only after both pass.
