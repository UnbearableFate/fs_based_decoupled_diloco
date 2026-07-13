# P08R D8 terminal failure review — PBS 2372056

## Classification

PBS `2372056.opbs` was the first P08R eight-node factor-one attempt on
`ab605c82f2c88a377c151273cfc5f502fbfee3ef`. It is a non-transient terminal
workflow failure. Its failed artifact and authority are frozen. No immediate
eight-node resubmission is authorized.

## What completed

The allocation used exactly eight nodes and eight learner-hosted LFEs. Runtime
completed all ten optimizer transitions, the terminal snapshot pin, normal
authoritative stop, worker exit, and the in-committer accelerated-versus-strict
terminal audit. The base factor-one report passed. Exact monotonic timings were:

- runtime: `332.884591101` seconds;
- complete experiment through the failed report invocation: `340.529032553`
  seconds;
- post-runtime work: `6.524666222` seconds.

The elapsed contract therefore passed the frozen 440-second gate. The raw
committer log contains ten `optimizer_head_cas` guards, one `stop_head_cas`
guard, two terminal snapshot guards, zero lifecycle heartbeat events, and zero
lease-authority-loss events.

## Failure and root cause

The wrapper failed after runtime at
`create_p08_performance_report.py factor-one`. `_distributed_lease_guard`
required at least one lifecycle substage heartbeat even when no long substage
needed a periodic renewal. P08R memoized replay made all guarded replay
substages shorter than the renewal interval, so the correct count was zero.
The report already required a one-to-one match between emitted heartbeat
events and their lease-stage guards, plus all ten optimizer CAS guards, the
stop CAS guard, and no authority loss. The extra lower bound was an obsolete
performance-dependent proxy, not a correctness condition.

This was a report assertion defect, not an authority, lease, training, or
elapsed-time failure. The failed manifest is preserved at
`artifacts/duraloco/P08R/20260713_p08r_d8_ab605c8_r1/manifest.json`; the terminal
authority remains read-only under the detached validation worktree.

## Repair and retry gate

Remove only the fabricated minimum-heartbeat requirement. Retain exact
heartbeat-to-guard equality, ten optimizer CAS renewals, one stop CAS renewal,
and the zero-authority-loss gate. Add regressions proving both zero-heartbeat
acceptance and rejection of an unguarded heartbeat.

Before one fresh eight-node retry:

1. run a one-node report-recovery benchmark against the frozen `2372056`
   authority and artifacts;
2. rerun targeted replay and the full one-node qualification on one clean
   repair commit;
3. rerun D1 and then D2 on that same clean commit;
4. record those PASS manifests in `P08R_STATE.yaml` and explicitly authorize
   one eight-node retry.

Any failure in that ladder leaves the retry unauthorized and must be recorded
as a new error-ledger entry.
