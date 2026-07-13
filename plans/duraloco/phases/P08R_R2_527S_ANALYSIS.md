# D8-R2 repair result: 410.780 seconds versus 527.044 seconds

## Repaired rerun result

The snapshot-suffix cache repair is now verified end to end. On clean commit
`8ebece36bd65c75ffb2b0b057d1f36e42cebcb1a`, matched factor-one PBS
`2373434.opbs` completed in `335.535577393 s` and repaired D8-R2 PBS
`2373631.opbs` completed in `410.779549171 s`. Both jobs used config SHA-256
`532dabdeaf3f100ff57eea0f469ab63520197d93f95a6ca797d729c55e2c84d1`,
GPT-2/WikiText-2, seed 1337, ten optimizer transitions, and exactly eight
learner nodes.

The repaired R2 run is **116.264942077 s faster**, a **22.060%** reduction from
the historical `527.044491248 s` run. Although the current D-4406 contract uses
a 600-second R2 envelope, the repaired run also fits the original 440-second
diagnostic boundary by `29.220450829 s`.

### New matched factor-one versus R2 difference

| Envelope component | Repaired factor one (s) | Repaired R2 (s) | R2 minus factor one (s) |
|---|---:|---:|---:|
| Setup | 1.110 | 1.084 | -0.026 |
| Runtime | 327.794 | 388.524 | **60.730** |
| Post-runtime reports/tests | 6.632 | 21.172 | **14.540** |
| **Complete experiment** | **335.536** | **410.780** | **75.244** |

The matched R2 premium is now `75.243971778 s`, or **22.425%**, instead of the
historical `189.491502084 s`, or 56.137%. The absolute premium shrank by
`114.247530306 s` (**60.292%**). Factor one's complete time changed by only
`-2.017411771 s` (-0.598%) between the historical and repaired campaigns, so
the large R2 change is not explained by a general faster run.

### Before and after the cache repair

| Measurement | Historical R2 | Repaired R2 | Change |
|---|---:|---:|---:|
| Runtime (s) | 504.798 | 388.524 | **-116.274 (-23.034%)** |
| Post-runtime (s) | 21.199 | 21.172 | -0.028 (-0.130%) |
| Complete experiment (s) | 527.044 | 410.780 | **-116.265 (-22.060%)** |
| Five lifecycle cycles (s) | 89.645 | 8.564 | **-81.081 (-90.447%)** |
| Lifecycle payload reads (bytes) | 47,805,060,618 | 20,581,751 | **-47,784,478,867 (-99.957%)** |
| Authority replay stage total (s) | 93.915 | 53.967 | **-39.949 (-42.537%)** |
| Successor publication stage total (s) | 50.824 | 31.050 | **-19.774 (-38.907%)** |
| Publish-to-commit total (s) | 361.334 | 241.107 | **-120.227 (-33.273%)** |
| Post-CAS replay heartbeat intervals | 4 | 0 | **-4** |

The repaired lifecycle cycle times were `0.698`, `1.110`, `1.618`, `2.230`,
and `2.907 s`; the historical times were `0.691`, `21.445`, `21.852`, `22.530`,
and `23.127 s`. Candidate counts, inventory counts, snapshot-get counts, and
the effective-live growth curve remained the same. The large tensor rereads
disappeared while required metadata and lifecycle objects were still read.

These lower-level stage totals overlap and must not be added together. They are
diagnostic attribution. Two unaffected controls remained stable:
`prepared_visibility` changed from `126.154` to `126.453 s` (+0.238%), and the
R2 GPU-step mean changed from `26.079` to `26.091 ms` (+0.046%). This directly
isolates the improvement to replay/snapshot composition and its downstream
publication critical path rather than training or hedge behavior.

### Correctness and qualification result

The rerun retained the full experiment shape and passed:

- 20 R2 attempt envelopes, 19 successful prepared attempts, and one controlled
  failed executor attempt;
- ten single-head optimizer transitions and the normal terminal stop;
- five lifecycle cycles, eight exact retained capsules, bounded reachability,
  and real-namespace GC dry runs;
- terminal fresh strict replay equal to snapshot-suffix replay;
- matched interference and bundle-gate reports;
- 32 lifecycle/replay regression tests after worker exit;
- exactly eight allocated and active learner hosts, with no ninth node.

The startup repair and retry ladder were also clean: targeted one-node PBS
`2373361`, full one-node PBS `2373379` (526 passed, one skipped), D1 PBS
`2373399`, and D2 PBS `2373419` all passed on the same commit before the two
eight-node jobs. PBS `2373113` is preserved separately as a pre-runtime wrapper
failure; it produced no timing sample.

New evidence:

- factor-one elapsed contract:
  `artifacts/duraloco/P08R/20260713_p08r_d8_8ebece3_repaired_r1/elapsed_contract.json`;
- repaired R2 elapsed contract:
  `artifacts/duraloco/P08R/20260713_p08r_d8r2_8ebece3_repaired_r1/elapsed_contract.json`;
- repaired R2 performance/lifecycle/interference reports under the same R2
  artifact directory;
- startup failure review:
  `plans/duraloco/phases/P08R_D8_WORKFLOW_FAILURE_REVIEW_2373113.md`.

## Historical explanation of the 527-second run

The sections below retain the original analysis of PBS `2372318.opbs`. They
remain useful for explaining what the repair removed.

## Historical short answer

The R2 experiment does **not intrinsically require 527 seconds**. The
`527.044 s` result is the measured complete-experiment time of a conservative
fault-recovery qualification that performs substantially more work than the
matched factor-one run. It also contains a known, avoidable snapshot-suffix
cache inefficiency.

The matched factor-one experiment completed in `337.553 s`; R2 completed in
`527.044 s`. The difference is `189.492 s`, or **56.137%**. This is not a GPU
training slowdown. It is primarily control-path, filesystem-I/O, redundancy,
lifecycle-audit, and post-run validation work.

Both measurements use commit
`ba0a5c693eb586d5db27b7e304f230d4acd826a8`, config SHA-256
`532dabdeaf3f100ff57eea0f469ab63520197d93f95a6ca797d729c55e2c84d1`,
GPT-2/WikiText-2, seed 1337, ten optimizer transitions, and exactly eight
learner nodes. Therefore this is the correct matched comparison.

## Additive top-level accounting

The elapsed-contract fields form an additive decomposition:

| Envelope component | Factor one (s) | R2 (s) | R2 minus normal (s) | Share of total increase |
|---|---:|---:|---:|---:|
| Setup | 1.051 | 1.047 | -0.004 | negligible |
| Runtime | 330.049 | 504.798 | **174.749** | **92.22%** |
| Post-runtime reports/tests | 6.453 | 21.199 | **14.747** | **7.78%** |
| **Complete experiment** | **337.553** | **527.044** | **189.492** | **100%** |

Thus almost all of the difference is inside the runtime, with a smaller but
real contribution from R2-only post-runtime validation.

## What makes the R2 runtime longer

### 1. R2 performs hedged factor-two execution

Factor one creates one executor attempt for each optimizer transition: ten
attempts total. R2 uses replication factor two, hedged mode, and a 6000 ms
hedge delay. It records 20 attempt envelopes: 19 complete prepared attempts
and one deliberately failed attempt.

The committer's result-wait policy starts with one required result. If the
primary is still incomplete when the 6000 ms hedge delay expires, the backup
becomes eligible and the committer requires both observable attempt outcomes.
Because a normal executor path itself lasts roughly seven seconds, this occurs
on the steady R2 transitions.

Measured consequences:

- aggregate `prepared_visibility` wait increased from `79.338 s` to
  `126.154 s`, a `46.816 s` or 59.0% increase;
- aggregate executor stage work increased from `71.208 s` to `127.378 s`, an
  additional `56.170 s`; this is work-time, not wall time, because the two
  executors overlap;
- the ordinary hedged transitions cost about five additional wall-clock
  seconds each relative to their matched factor-one transitions.

This is an intentional reliability cost: R2 obtains duplicate execution and
complete attempt lineage instead of only one prepared result.

### 2. R2 runs five periodic lifecycle cycles

Factor one performs the mandatory terminal snapshot/strict audit. R2 also runs
a lifecycle cycle every two optimizer transitions. Across ten transitions it
therefore performs five cycles containing:

- an ancestry-pinned snapshot;
- snapshot/suffix replay;
- reachability-root construction;
- a complete object inventory;
- capsule retention checks; and
- a real-namespace GC dry run.

The five measured cycle times were:

```text
0.691, 21.445, 21.852, 22.530, 23.127 seconds
```

They total **89.645 s**. This alone is 51.3% of the `174.749 s` runtime
increase, although it must not be added again to overlapping stage counters
below.

### 3. The accepted run still had a snapshot-suffix cache defect

In PBS `2372318.opbs`, snapshot-mode replay rebuilt its scratch cache from the
pinned snapshot and replaced the live owner cache. That discarded verified
tensor identities introduced after the snapshot. The later four lifecycle
cycles therefore reread the same live suffix instead of reusing it.

The evidence is direct:

- lifecycle payload reread: `47,805,060,618` bytes;
- later-cycle payload read: approximately `11.95 GB` per cycle;
- lifecycle time: `89.645 s` total;
- four post-CAS replay heartbeat intervals, versus zero in factor one;
- transaction `authority_replay` time increased from `53.193 s` to
  `93.915 s`, a `40.722 s` increase.

This was a process-local memo-composition defect, not an authority or numeric
failure. Every terminal digest, fault, lifecycle, and numeric check passed.

The later repair commit
`ac2d961f148841b14ba7bc628ce1566695571bf0` conflict-checks and unions the
snapshot cache with the verified live suffix. Its real-prefix benchmark showed
that the first suffix replay read `5,973,112,800` tensor bytes in `10.016 s`,
while the second replay read **zero tensor bytes** in `0.260 s` and remained
strict-digest equivalent. No new full D8-R2 run was performed after this
repair, so an exact repaired end-to-end time must not be invented.

### 4. R2 performs more post-runtime validation

After worker exit, factor one creates its summary and performance report. R2
additionally creates:

- the R2 performance report;
- the matched interference report;
- the bundle-trigger decision report;
- the complete P07 lifecycle report; and
- 30 lifecycle/replay regression tests with JUnit evidence.

This increases post-runtime work from `6.453 s` to `21.199 s`, adding
`14.747 s` to the complete experiment.

## Transition-level evidence

`publish_to_commit_seconds` nearly explains the complete runtime difference.
Its total is `184.174 s` for factor one and `361.334 s` for R2, a
`177.160 s` increase. The matched per-transition pattern is more informative
than a single average:

| Transition group | Factor-one total (s) | R2 total (s) | Increase (s) | Share of publish-to-commit increase |
|---|---:|---:|---:|---:|
| Controlled-fault transition 1 | 18.269 | 18.760 | 0.491 | 0.28% |
| Transitions without an expensive lifecycle cycle: 2, 3, 5, 7, 9 | 92.069 | 117.854 | 25.785 | 14.56% |
| Transitions containing the later expensive lifecycle cycles: 4, 6, 8, 10 | 73.836 | 224.720 | **150.884** | **85.17%** |

Normal transitions are stable at roughly `18.3-18.6 s`. Ordinary hedged R2
transitions take roughly `23.2-24.1 s`. The four transitions affected by the
expensive later lifecycle cycles take `55.2-57.2 s`. This repeated pattern is
why the total rises to 527 seconds.

The lower-level stage totals are diagnostic but are not additive because some
spans overlap or are nested inside `publish_to_commit_seconds` and lifecycle
cycles. The largest observed changes are:

| Causal stage | Factor one (s) | R2 (s) | Increase (s) |
|---|---:|---:|---:|
| Prepared-result visibility | 79.338 | 126.154 | 46.816 |
| Authority replay | 53.193 | 93.915 | 40.722 |
| Successor publication | 30.625 | 50.824 | 20.199 |
| Catalog discovery | 47.410 | 47.204 | -0.207 |

The unchanged catalog time shows that proposal discovery is not the cause.
The concentration in result visibility, replay, and publication is consistent
with factor-two execution plus the measured suffix rereads and Lustre object
traffic.

## What is *not* causing the 56% increase

- **GPU training:** both runs contain 440 GPU-step samples. R2's mean is
  `26.079 ms`, versus `26.513 ms` for factor one; R2 is 1.64% faster on this
  metric.
- **Setup:** both take approximately `1.05 s`.
- **The terminal strict audit:** both runs pay roughly 53 seconds for the
  mandatory fresh strict terminal reconstruction; R2 is not slower there.
- **The injected fault by itself:** R2 records `18.429 s` as its recovery
  interval, but that interval is nested inside the first transition rather
  than being an additional 18.429 seconds. The first R2 transition is only
  `0.491 s` slower than the matched normal transition. Most overhead comes
  from steady redundancy and repeated lifecycle work, not from the single
  injected failure.

## Conclusion

The 527-second result is reasonable for the accepted qualification shape, but
it is not a fundamental minimum. The 56.137% increase consists of:

1. intentional hedged factor-two work and its 6000 ms activation policy;
2. five required periodic lifecycle/snapshot/reachability/GC-dry-run cycles;
3. a known avoidable suffix-cache loss that reread 47.805 GB; and
4. additional post-runtime reports and regression tests.

The user-approved D-4406 adjudication therefore accepts `527.044 s` under a
practical `600 s` complete-experiment envelope while retaining every fault,
lifecycle, topology, terminal-strict, and numeric gate. The immutable source
elapsed report still says `FAIL` only because it was created under the old
440-second R2 boundary; the separate adjudication report is `PASS`.

The repaired suffix memo proves that a future full R2 run should avoid the
largest known redundant rereads. However, because no repaired eight-node R2
experiment was run, this report intentionally makes no unsupported prediction
of the new final wall-clock time.

## Evidence

- Matched factor-one elapsed contract:
  `artifacts/duraloco/P08R/20260713_p08r_d8_ba0a5c6_r3/elapsed_contract.json`
- Matched factor-one performance report:
  `artifacts/duraloco/P08R/20260713_p08r_d8_ba0a5c6_r3/p08_d8_report.json`
- R2 source elapsed contract:
  `artifacts/duraloco/P08R/20260713_p08r_d8r2_ba0a5c6_r2/elapsed_contract.json`
- R2 performance report:
  `artifacts/duraloco/P08R/20260713_p08r_d8r2_ba0a5c6_r2/p08_d8_r2_report.json`
- R2 lifecycle report:
  `artifacts/duraloco/P08R/20260713_p08r_d8r2_ba0a5c6_r2/p07_lifecycle_report.json`
- Matched interference report:
  `artifacts/duraloco/P08R/20260713_p08r_d8r2_ba0a5c6_r2/interference_report.json`
- Preserved root-cause review:
  `plans/duraloco/phases/P08R_D8R2_FAILURE_REVIEW_2372318.md`
- Repaired real suffix benchmark:
  `artifacts/duraloco/P08R/20260713_p08r_lifecycle_ac2d961_r4/snapshot_suffix_benchmark.json`
- D-4406 immutable adjudication:
  `artifacts/duraloco/P08R/20260713_p08r_lifecycle_ac2d961_r4/r2_adjudication.json`
