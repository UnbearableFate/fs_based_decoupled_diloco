# P08R D8-R2 terminal failure review — PBS 2372217

## Classification

PBS `2372217.opbs` was the first P08R eight-node R2 fault/lifecycle arm on
qualified runtime commit `16e8c4242022c965db3c6fdf30021a5f0c8f4958`.
It is a non-transient terminal performance failure. The artifact, reports,
stage telemetry, and authority are frozen. No immediate D8-R2 resubmission is
authorized.

## What completed

The run used exactly eight learner nodes, recovered the controlled executor
failure in 18.350 seconds, recorded all twenty attempt envelopes and nineteen
successful prepared results, completed ten optimizer transitions, preserved
five snapshot/reachability/inventory dry-run cycles, published normal stop,
and passed terminal accelerated-versus-strict replay. The R2 performance,
interference, bundle-gate, P07 lifecycle, and 30 lifecycle regression tests all
reported PASS.

The wrapper correctly failed the frozen elapsed contract:

- runtime: `670.007937869` seconds;
- post-runtime: `24.275678011` seconds;
- complete experiment: `695.344515011` seconds;
- target: at most `440` seconds.

## Root cause and stage timings

Each lifecycle cadence still performed an empty-cache `force_full=True` strict
replay synchronously on the authoritative committer path, even though every
cycle already pinned a verified snapshot, replayed its suffix, and the terminal
path performed the required fresh strict equality audit. The five cycles took
`12.318`, `43.431`, `54.433`, `65.201`, and `76.011` seconds: `251.394` seconds
total. They reread `142,382,668,678` payload bytes. Periodic explicit strict
replay also invalidated the owner-bound memo and caused four later post-CAS
replay heartbeat intervals.

This is the unfinished P08R Loop 3 critical path identified in the plan. It is
not a learner, LFE, fault-recovery, topology, authority, or reporting failure.
GPU mean was 26.353 ms, all reports passed, and post-runtime work remained
inside its 25-second budget.

## Proposed repair and retry gate

Add an explicit opt-in deferred lifecycle-audit mode for the P08R R2 committer.
Periodic cycles must retain snapshot CAS, accelerated replay, reachability,
inventory, dry-run evidence, leases, roots, capsules, and bounds, but defer the
redundant empty-cache strict comparison to the already mandatory read-only
terminal strict audit. The default and historical P07/P08 behavior remains
unchanged. Enabling deferral without lifecycle cadence and terminal strict
audit must fail closed.

Before one fresh D8-R2 retry:

1. benchmark accelerated lifecycle plus one final strict equality audit on the
   frozen `2372217` authority using one compute node;
2. run focused regressions for opt-in/default/fail-closed behavior;
3. rerun the full one-node, D1, and D2 qualification on one clean repair
   commit;
4. persist the PASS manifests and explicitly authorize one D8-R2 retry.

Any failure in that ladder is a new error-ledger entry. No ninth node and no
second immediate D8-R2 retry are authorized.
