# P08 nine-node validation review — PBS 2370521

## Classification

- Shape: repaired matched C9/no-LFE GPT-2/WikiText-2 50x10 shadow.
- Clean commit: `60e9687a07dfb1a22ce06408c87b74c8769eb570`.
- Runtime result: ten optimizer transitions and a normal terminal completed.
- Acceptance result: **inconclusive/fail closed** because the terminal stop CAS
  was not protected by the new long-substage lease guard.

## Evidence and root cause

The P08-E019 repair worked for every optimizer transition: 45
`transaction_substage_heartbeat` events kept preparation and post-CAS replay
alive through ten transitions. The dedicated benchmark (`2370503`), targeted
one-node (`2370506`), full one-node (`2370512`), and D2 (`2370520`) gates all
passed on the same commit.

The terminal path still called the convenience `commit_stop`, which performs a
strict prepare internally before its CAS. At history depth ten, the reported
`authoritative_stop` stage took 101.495 seconds, more than twice the 45-second
lease TTL. The stop was semantically correct and the job manifest says `pass`,
but the owner had no proven live lease at that CAS. Therefore this run is not
accepted as matched no-LFE evidence.

Preserved evidence:

- `artifacts/duraloco/P08/20260713_p08_nolfe_60e9687_r2/manifest.json`
- `artifacts/duraloco/P08/20260713_p08_nolfe_60e9687_r2/p08_nolfe_report.json`
- `artifacts/duraloco/P08/20260713_p08_nolfe_60e9687_r2/stdout.log`
- `artifacts/duraloco/P08/20260713_p08_nolfe_60e9687_r2_storage/training/`
- `tracejob 2370521.opbs`

## Repair and retry gate

Split terminal stop into non-authoritative strict preparation, a final
successful lease renewal, caller-thread `commit_prepared` CAS, and guarded
read-only post-CAS replay. The existing fail-closed lease-loss rule remains:
loss cannot publish a stop.

Before another C9 attempt, rerun the dedicated targeted benchmark, full
one-node qualification, and D2 on one clean commit. The next C9 report must
record a normal terminal and heartbeat evidence spanning stop preparation and
post-CAS replay. Factor-one and R2 remain unauthorized until then.
