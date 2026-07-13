# P08R D8-R2 terminal failure review — PBS 2372318

## Classification

PBS `2372318.opbs` was the single authorized D8-R2 retry after the `2372217`
failure. It ran on qualified commit
`ba0a5c693eb586d5db27b7e304f230d4acd826a8` with matched factor-one baseline
PBS `2372292`. It is a new non-transient terminal performance failure. Its
authority and reports are frozen, and no immediate resubmission is authorized.

## What completed

Exactly eight learner nodes completed the controlled fault, twenty attempt
envelopes, nineteen prepared results, ten optimizer transitions, five dry-run
lifecycle cycles, normal stop, terminal strict equality, matched interference,
bundle gate, P07 lifecycle report, and all lifecycle regressions. Every report
other than the elapsed contract passed.

The wrapper correctly failed:

- runtime: `504.797810859` seconds;
- post-runtime: `21.199228703` seconds;
- complete experiment: `527.044491248` seconds;
- target: at most `440` seconds.

## Root cause and stage timings

Deferring the five redundant periodic strict audits reduced lifecycle time from
251.394 to 89.645 seconds, but did not preserve the already verified live
suffix memo across snapshot-mode replay. `replay_snapshot_suffix()` rebuilt a
cache from the pinned snapshot and replaced the process cache, discarding
verified objects introduced after that snapshot. At each later cadence,
snapshot preparation therefore reread the same two-transition suffix.

The five cycles took `0.691`, `21.445`, `21.852`, `22.530`, and `23.127`
seconds and reread `47,805,060,618` payload bytes. The repeated cache loss also
caused four post-CAS replay heartbeat intervals. This is a process-local cache
composition defect; authority, snapshot validation, terminal strict equality,
fault recovery, LFE results, and numeric reports all passed.

## Proposed repair and retry gate

During snapshot replay, form a scratch verified cache by conflict-checked union
of the snapshot-embedded prefix and the ownership-bound live process cache.
Promote it only after the complete replay and head check succeed. Snapshot
identities remain authoritative for the covered prefix; ambiguous head,
takeover, corruption, explicit verification, and failed replay still clear or
leave the live cache unchanged.

Before another D8-R2 attempt:

1. on one compute node, use the frozen real authority with a read-only
   historical-head overlay to replay two optimizer transitions after a pinned
   snapshot twice, proving the second call reads zero tensor payload bytes and
   still equals strict replay;
2. run focused snapshot/cache invalidation regressions;
3. rerun full one-node, D1, and D2 on one clean repair commit;
4. record one matched factor-one report on that exact commit;
5. explicitly authorize one fresh D8-R2 attempt.

Any failure is recorded separately. No ninth node or immediate same-shape
resubmission is authorized.
