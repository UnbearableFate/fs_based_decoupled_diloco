# P08 nine-node workflow/root-cause review — PBS 2370465

## Classification

- Shape: matched C9/no-LFE GPT-2/WikiText-2 50x10 shadow on nine nodes.
- Clean commit: `0664a4f8ae28b8b5747af82ef9d31002e1d0985b`.
- Result: non-transient terminal runtime failure after four optimizer transitions.
- Authority: the sole committed head truthfully contains an `error` stop at
  commit sequence 6 with optimizer-transition count 4. No retry will reuse this
  run namespace.

## Preserved evidence

- `artifacts/duraloco/P08/20260713_p08_nolfe_0664a4f_r1/manifest.json`
- `artifacts/duraloco/P08/20260713_p08_nolfe_0664a4f_r1/stdout.log`
- `artifacts/duraloco/P08/20260713_p08_nolfe_0664a4f_r1_storage/training/`
- `duraloco_p08_c9.o2370465`
- `tracejob 2370465.opbs`

## Stage timing and root cause

The centralized no-LFE shadow renews a 45-second observational lease only at
the outer loop boundary. As immutable history grew, successor preparation and
post-CAS replay grew together:

| committed seq | successor prepare | post-CAS replay |
| --- | ---: | ---: |
| 2 | 4.408 s | 6.221 s |
| 3 | 9.286 s | 11.256 s |
| 4 | 14.152 s | 16.064 s |
| 5 | 19.073 s | 21.130 s |

The last lease renewal completed at `1783883232.014`; transition 5 completed at
`1783883281.036`, 49.023 seconds later. The next renewal correctly rejected the
expired lease. This is not a GPU, learner, Lustre-integrity, or optimizer
failure; it is a missing long-substage renewal guard in the legacy centralized
syncer path. The D8 learner-hosted committer already has an equivalent guard
for long lifecycle reads.

## Repair and proof obligations

The repair runs successor preparation and post-CAS replay as explicitly
non-authoritative worker substages while the main owner thread renews the
lease. Prepared objects remain immutable/unreachable until the caller performs
a final successful renewal immediately before the only head CAS. Replay is
read-only. If any renewal loses authority, the stale process exits without
committing an `error` stop.

Before one new nine-node attempt:

1. Run the dedicated one-node benchmark with a stage longer than its initial
   TTL using real conditional lease mutations.
2. Run the full P08 targeted and full one-node gates on the same clean commit.
3. Run the D2 error-resume qualification on that same clean commit.
4. Only then retry C9/no-LFE once in a fresh namespace.

No factor-one or R2 nine-node job is authorized until the C9 retry passes.
