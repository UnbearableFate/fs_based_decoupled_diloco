---
plan_id: P08R-440
title: Pre-P10 50x10 Replay and Lifecycle Performance Recovery
status: ready
date: 2026-07-13
planning_basis_runtime_commit: 8492eb4163b406baf67d6d56f100b693dd6aa781
planning_basis_checker_job: 2371170.opbs
planning_basis_persistence_commit: c6ec3571bdc240fff8dd26e2dd7580bca8f69336
target_branch: codex/duraloco-p08r-replay-440s
depends_on: [P08]
blocks_execution_of: [P10]
execution_mode: single-writer maker + independent checker
next_phase: P10
---

# P08R — 50×10 wall-clock recovery

## 1. Objective and scope

Recover the P06B/M00 50×10 wall-clock envelope without weakening any P08
correctness guarantee. Factor one retains the **440 seconds or less** target.
Per the user's 2026-07-13 scope amendment, the fault-recovery R2 arm uses a
practical **600-second complete-experiment envelope** rather than treating 440
seconds as a strict failure boundary:

1. D8 factor-one;
2. D8-R2 with the frozen controlled executor failure and P07 lifecycle
   integration.

No current or future P08R run may allocate a ninth node. Historical C9 and
P08 nine-node-allocation artifacts remain evidence of completed phases only;
they are not rerun, are not an acceptance dependency, and do not define the
forward production topology.

P08 remains completed. P08R is a pre-P10 performance qualification overlay,
not a rewrite of the P08 verdict or protocol generation. P10 execution waits
until P08R has a clean same-commit Maker ladder and an independent Checker
PASS.

## 2. Frozen metric contract

The target cannot be met by redefining elapsed time. Every final wrapper must
record both:

- `runtime_elapsed_seconds`: immediately before worker launch through normal
  authoritative stop and all worker exits;
- `experiment_elapsed_seconds`: wrapper start through required summary,
  performance/lifecycle reports, regressions, and successful manifest-ready
  completion.

The factor-one acceptance value is `experiment_elapsed_seconds <= 440`; the
R2 error-recovery acceptance value is `experiment_elapsed_seconds <= 600`.
Queue wait is excluded; PBS prologue/epilogue is archived separately as scheduler wall time.
The report must also retain runtime-only time so report work cannot be hidden
inside or outside the claim.

The following are immutable across comparisons:

- config: `configs/duraloco_milestone_gpt2_8node_50x10.yaml`;
- config digest: `532dabdeaf3f100ff57eea0f469ab63520197d93f95a6ca797d729c55e2c84d1`;
- GPT-2, WikiText-2 raw-v1, seed 1337;
- eight learners, 50 local steps × ten optimizer transitions;
- exactly eight allocated nodes and eight learner hosts for every final run;
- no dedicated syncer, control, audit, spare, or idle ninth node;
- bfloat16 proposal transport, float32 accumulation/committed parameters;
- one global head, the frozen selection/weighting/outer-optimizer policy, and
  the existing factor-one or hedged-R2 identities;
- validation, SHA/finite checks, marker-last publication, fsync, lease/fence,
  head CAS, strict fallback, P07 reachability/capsules, and the R2 fault tape.

No acceptance run may reduce steps, transitions, payload size, learners,
validation, reports, lifecycle obligations, or fault coverage. Increasing a
timeout or excluding a stage does not improve performance.

## 3. Measured baseline and confirmed bottleneck

| Shape | Current P08 | Historical reference | Key observation |
|---|---:|---:|---|
| D8 factor-one | 950 s | P06B 427 s report / 470 s phase summary | GPU and LFE are faster, commit loop is slower |
| D8-R2 | 725 s | P06C 528 s | snapshots bound replay, lifecycle audits cost 280.82 s |

The historical C9/no-LFE result (834 s) remains diagnostic evidence that the
regression is in authority/replay rather than learner compute. It is not a
forward acceptance run.

The P08 factor-one run proves this is not a learner or LFE regression:

- GPU step mean is 26.04 ms versus P06B's 27.75 ms;
- LFE preparation is 6.39–6.47 s versus P06B's 17.8–18.2 s;
- factor-one GPU interference versus matched no-LFE is 0.49%.

The regression is in authority reconstruction:

- publish→commit grows from 20.83 s to 113.71 s instead of P06B's stable
  17.8–18.2 s;
- successor preparation grows from 4.30 s to 50.89 s, approximately 5 s for
  each additional ~1 GiB committed params/outer-state pair;
- 25 post-CAS replay heartbeats prove at least 250 s of additional guarded
  replay waits;
- the tenth commit to normal terminal stop takes 105.53 s.

`replay_snapshot_suffix()` currently constructs an empty
`ProductionReplayCache` on every no-valid-snapshot fallback. Thus factor-one
revalidates all historical large tensors during prepare and again after CAS,
despite M00 permitting ownership-bound process-local memoization after one
complete successful strict replay. R2 avoids the unbounded successor curve by
pinning a snapshot every two optimizer transitions, but its five synchronous
strict/reachability/inventory lifecycle cycles cost 36.24, 44.38, 55.48,
66.50, and 78.22 seconds.

## 4. Performance budget

Each final arm must fit this end-to-end budget; unused budget is slack, not a
license for another stage to grow without bound.

| Component | Hard budget |
|---|---:|
| wrapper setup, model/data open, first eligible FWO | 90 s |
| first eligible FWO through tenth optimizer CAS | 285 s |
| tenth CAS through normal terminal and worker exit | 25 s |
| required summary/reports/regressions/manifest preparation | 25 s |
| unallocated tail reserve | 15 s |
| **Total** | **440 s** |

Supporting substage gates:

- factor-one successor preparation: p95 ≤ 7 s, max ≤ 10 s;
- same-owner post-CAS replay: p95 ≤ 2 s, max ≤ 4 s;
- guarded terminal prepare + CAS + replay: ≤ 15 s;
- LFE prepare: p95 ≤ 7 s, max ≤ 9 s;
- warm same-owner replay must read zero bytes from previously verified
  params/outer-state ObjectRefs; it may read manifests and newly introduced
  objects;
- GPU-step mean regression versus the accepted historical D8 baseline and the
  new same-commit factor-one repetitions: ≤ 2% for factor one and ≤ 5% for R2;
- telemetry/report overhead: ≤ 2% runtime and ≤ 25 s absolute post-run.

## 5. Decisions to freeze before implementation

### D-4401 — Ownership-bound verified replay memo

The no-snapshot fallback starts empty only on fresh open, takeover, explicit
verification, CAS conflict/response ambiguity, external head/epoch jump,
manual cache clear, or corruption suspicion. After a complete successful
strict replay, verified immutable tensor identities may be reused inside that
same process and ownership scope. Manifests, head, causal rules, and all new
ObjectRefs are still validated on every replay. The memo is never serialized
and is discarded before any ownership boundary.

### D-4402 — Transactional cache promotion

Replay uses a scratch copy of the current memo. New entries become reusable
only after the entire replay succeeds and its head binding is proven. Failed,
partial, cancelled, corrupt, or stale-head replay cannot modify the live memo.

### D-4403 — Normal self-CAS versus suspicious head jump

A successful caller-thread CAS of the exact prepared transition is a normal
same-owner head advance and may retain previously verified immutable objects.
Any head change not reconciled to that exact request/commit is suspicious and
forces empty-cache strict replay.

### D-4404 — Snapshot and lifecycle separation within eight nodes

Snapshot pinning may remain on the authoritative committer path, but strict
replay, reachability, inventory, and dry-run analysis are read-only audits.
They may be overlapped only within the fixed CPU/RSS budget of the existing
eight learner hosts, or deferred until learner/LFE processes exit. They may
not justify another allocation. A stale audit result is discarded and never
affects authority. The terminal report still requires a final audit equal to
fresh strict replay.

### D-4405 — No incremental-view shortcut without proof

First attempt the smaller memo/snapshot repair. Incremental post-CAS RuntimeView
application is allowed only if the measured projection still exceeds 440 s;
it must be a deletable optimization checked against strict replay for every
prefix and must fall back on ambiguity.

### D-4406 — Practical R2 error-recovery envelope

Factor one retains its 440-second diagnostic and acceptance target. The R2 arm
must still record exact runtime, post-runtime, and complete-experiment spans,
pass every fault/lifecycle/numeric/topology gate, and keep post-runtime work at
or below 25 seconds, but its complete-experiment pass boundary is 600 seconds.
This reflects the user's explicit instruction that error recovery be shortened
to a reasonable range rather than held to a fixed 440-second requirement.

## 6. Execution loop

### Loop 0 — SPECIFY and RED instrumentation

Add replay-call telemetry with call ID, owner/session/head/epoch scope,
`strict_fallback`/`memoized_prefix`/`snapshot_suffix` mode, reason, cache
entries before/after, promoted entries, storage get/header/payload bytes, and
elapsed time. Split successor prepare, post-CAS replay, stop prepare/replay,
fresh summary replay, and lifecycle audit in the final reports.

RED proof on a compute node:

- construct or read a real ten-transition GPT-2 prefix;
- show current no-snapshot fallback rereads historical tensor payloads and
  grows approximately linearly per call/quadratically over the run;
- archive strict first-open, second same-owner, one normal self-CAS advance,
  external head jump, takeover, CAS ambiguity, and distinct-ObjectRef
  corruption cases.

Stop only when every byte and elapsed-time claim can be attributed to one
causal replay call.

### Loop 1 — GREEN no-snapshot memo reuse

Implement D-4401/D-4402 in the existing `ProductionReplayCache` and production
log; do not create a second replay authority or cache schema. Preserve full
manifest/causal replay while skipping only previously verified immutable large
tensor payload validation.

Required tests:

- first replay is empty-cache strict;
- second same-owner replay has identical digest and zero prior-tensor payload
  reads;
- one exact self-CAS validates only new objects;
- external head/epoch jump, takeover, conflict, ambiguity, cache clear, and
  corruption suspicion start empty;
- failed replay never promotes scratch entries;
- deleting the memo changes only cost, never result;
- every prefix remains strict/memoized/snapshot digest-equivalent.

Decision gate: run the real-prefix benchmark. If projected factor-one total is
≤ 410 s, skip incremental-view work and retain 30 s of final-run margin.

### Loop 2 — Terminal and fresh-summary replay

Apply the same proven memo path to guarded stop preparation and post-CAS replay.
Provide a final ancestry-pinned snapshot suitable for a fresh report process,
or prove that fresh strict summary replay itself fits the 25 s reporting
budget. A report process must never inherit process-local memo state.

Stop when guarded terminal time is ≤ 15 s and a fresh report independently
reconstructs the exact terminal digest without rereading an unbounded prefix.

### Loop 3 — Snapshot/lifecycle critical-path removal

Keep snapshot pins, single-head CAS, two-snapshot retention, reachability
types, capsule roots, and dry-run deletion unchanged. First remove redundant
same-owner replay. If lifecycle work still exceeds budget, run a bounded
read-only audit worker on an existing learner host using the audited LFE CPU/
RSS envelope, or defer the final audit until local learner/LFE exit. Reconcile
the final head before PASS; a ninth host is prohibited.

Failure/cancellation cases:

- head advances while an audit is running;
- owner takeover during audit;
- corrupt/missing newest snapshot;
- response loss after snapshot pin CAS;
- audit worker crash or telemetry loss;
- final audit misses the 25 s report budget.

No audit worker may hold an owner token, write the global head, delete an
object, or publish a lifecycle result for a different head.

### Loop 4 — Conditional incremental post-CAS view

Run only if Loops 1–3 still project above 440 s. Derive the next process-local
RuntimeView from the exact committed prepared transition, then verify the next
head observation. Periodically and at terminal compare against independent
strict replay. Any mismatch, conflict, timeout, ambiguity, or ownership change
deletes the derived view and performs empty-cache strict replay.

### Loop 5 — Conditional metadata/catalog optimization

Run only if replay and lifecycle meet budget but the complete experiment does
not. Current catalog discovery costs roughly 4–5 s per transition. Optimize
only reconstructible process-local observations or safe concurrent header
reads. Directory cursors may reduce repeated work but cannot filter the
correctness inventory, and cheap rejection must still precede payload reads.

### Loop 6 — Qualification and final matched runs

On one clean implementation commit, execute strictly in order:

1. targeted real-prefix replay/memo benchmark on one compute node;
2. full one-node suite and large-object benchmark;
3. D1 real GPT-2 smoke;
4. D2 ownership/takeover/ambiguity qualification;
5. D8 factor-one 50×10 twice, sequentially, with fresh namespaces;
6. D8-R2 controlled-fault/lifecycle 50×10;
7. independent Checker on a later persistence commit.

Final jobs request exactly `select=8:mpiprocs=1` and launch exactly eight
learner-host ranks. Do not run final arms concurrently; shared-Lustre
interference would invalidate the 440-second claim. Both factor-one repeats
must be ≤ 440 s and their experiment elapsed times must differ by no more than
10%. Factor-one and R2 must use the same runtime commit/config/seed and matched
telemetry.

After any non-transient 8-node terminal failure, preserve the failure manifest
and stage timings, write a root-cause review, prove the repair with the smallest
compute benchmark, rerun clean 1-node and 2-node qualification, and make only
one fresh 8-node retry. Never reuse a run namespace.

## 7. Acceptance IDs

- [ ] P08R-A01: metric contract records runtime and complete-experiment time;
- [ ] P08R-A02: current quadratic replay RED evidence and byte attribution archived;
- [ ] P08R-A03: first open/takeover/explicit verify remain empty-cache strict;
- [ ] P08R-A04: same-owner memoized replay reads no prior tensor payload bytes;
- [ ] P08R-A05: cache promotion is all-or-nothing after complete replay;
- [ ] P08R-A06: head/epoch/conflict/ambiguity/corruption invalidation fails closed;
- [ ] P08R-A07: memo is process-local, non-authoritative, deletable, and never serialized;
- [ ] P08R-A08: strict/memoized/snapshot results match for every prefix;
- [ ] P08R-A09: successor prepare/post-CAS replay satisfy substage budgets;
- [ ] P08R-A10: guarded terminal and fresh summary satisfy their budgets;
- [ ] P08R-A11: lifecycle/audit overlap preserves P07 roots, bounds, and final equality;
- [ ] P08R-A12: telemetry overhead remains ≤ 2% and all expensive work is attributed;
- [ ] P08R-A13: one-node real-prefix/full and D1 gates pass;
- [ ] P08R-A14: D2 takeover/ambiguity/lease qualification passes;
- [ ] P08R-A15: every final manifest proves exactly eight allocated/active learner nodes and zero dedicated/idle control nodes;
- [ ] P08R-A16: two sequential D8 factor-one complete experiments are each ≤ 440 s;
- [ ] P08R-A17: D8-R2 fault+lifecycle complete experiment ≤ 600 s under D-4406;
- [ ] P08R-A18: GPU/LFE numeric, interference, affinity, RSS, and I/O gates do not regress;
- [ ] P08R-A19: no SQLite, second authority, per-fragment head, disabled validation/fsync, or changed optimizer trajectory;
- [ ] P08R-A20: report, checksums, clean runtime commit, independent Checker PASS, and P10 handoff persisted.

## 8. Checker obligations

The independent Checker must:

- delete all process-local state and reproduce every final digest;
- trigger takeover, external head jump, CAS response ambiguity, and distinct
  corrupt successor, verifying empty-cache fallback each time;
- prove memo entries appear only after a complete replay and never cross owner;
- compare every prefix under strict, memoized, and snapshot modes;
- verify no benchmark switch disables validation, SHA/finite checks, fsync,
  fencing, lease renewal, or lifecycle roots;
- recompute elapsed time from raw monotonic events and reject missing stages;
- verify both factor-one repetitions and the R2 matched binding;
- rerun P07/P08 lifecycle, recovery, and active-surface database regressions;
- return only `PASS`, `PASS_WITH_FOLLOWUPS`, or `BLOCKED`; completion requires
  PASS or PASS_WITH_FOLLOWUPS with no required-gate follow-up.

## 9. Expected implementation surface

Prefer changes to the existing paths:

```text
fs_diloco/log/replay.py                 transactional memo reuse and telemetry
fs_diloco/log/production.py             owner/head scope and invalidation
fs_diloco/runtime_view.py               existing replay selection only
fs_diloco/distributed_syncer/committer.py  stage integration and audit handoff
fs_diloco/telemetry/                     replay/lifecycle performance events
benchmarks/                              real-prefix replay scaling benchmark
tests/log/                               strict/memo/snapshot equivalence
tests/distributed_syncer/                owner/head/ambiguity invalidation
scripts/miyabi/                          1-node, D2, D8, R2, Checker wrappers
```

Do not introduce an embedded database, durable replay cache, parallel log,
alternate head, or compatibility runtime.

## 10. Immediate first action

Create branch `codex/duraloco-p08r-replay-440s` from the clean P08 persistence
tip. Before modifying replay, add the real-prefix replay scaling benchmark and
RED tests proving that no-snapshot fallback currently discards reusable
verified tensor identities. The first compute allocation is one node only; no
new 8-node job is authorized until RED→GREEN, full one-node, and D2 pass on one
clean commit. No ninth-node job is part of P08R.
