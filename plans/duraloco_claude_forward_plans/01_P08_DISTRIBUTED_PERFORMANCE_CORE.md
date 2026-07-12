---
plan_id: "P08"
title: "Distributed Performance Core: Direct Fragment I/O, Streaming Reducer, Bounded Bundling, Telemetry"
status: "ready"
date: "2026-07-12"
planning_basis_commit: "f167a07c49339ba42d14f8a5873fe2c8781884d4"
planning_basis_checker_commit: "04e0a8634b0e9d7c4cd55c5593081a0ca969a060"
target_branch: "codex/duraloco-p08-distributed-performance"
depends_on: ["H0"]
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
next_phase: "P10"
agent_decision_gates:
  - "multi-FWO preparation / one-CAS bundle only if profile crosses the preregistered bottleneck threshold; otherwise close A16–A18 as checker-accepted not_applicable"
  - "any CUDA/C++/layout/precision change requires profile, numeric equivalence, and a fallback path"
human_approval_gates: []
---

# P08 — Distributed Performance Core

## 1. Mission

Make the learner-hosted fragment executor (LFE) and Floating Committer critical
path scale with **fragment size** rather than model size or pending-proposal
count: working memory, copies, payload I/O, and metadata scans. Build
telemetry that can reconstruct the full publish → plan → prepare → commit →
adopt timeline per transition and per loser attempt. Quantify and bound LFE
interference with learner GPU throughput. Only implement bounded concurrent
prepare + one-CAS `CommitBundlePlan` if profiles prove single-FWO/head
serialization is the bottleneck.

Research claim: D8/D8-R2 performance is not dominated by whole-model copies,
q×fragment residency, or unbounded metadata scans; a dispersed syncer can reuse
learner CPU with acceptable GPU-goodput cost and precisely attributed
redundancy/storage cost.

Everything P07 froze stays frozen: single-head authority, empty-cache strict
fallback, two-snapshot retention, typed reachability, unknown quarantine,
guarded GC, exact capsules, marker-last ordering, long-substage lease
heartbeats. Every cache, cursor, token, or prefetch introduced here must be
deletable without correctness impact.

## 2. Preconditions

- [x] H0-A01–A09 pass; H0 commit is the runtime baseline (honest listing
      costs, truthful stop facts).
- [x] Factor-1 / R2 / lifecycle raw baselines exist (P06B 470 s, P06C 528 s,
      P07 1100 s D8 references) — these will be re-measured on the H0 commit
      because H0 changes listing cost; the re-measured numbers are the
      baseline of record.
- [x] CRS/LFE numeric equivalence harness re-runnable.
- [ ] Profilers must not alter authority or timing-sensitive selection.

## 3. Design decisions to freeze first

- [ ] **D-0800 (new): error-stop semantics.** Decide review-M8: either an
      `"error"` stop is not committed (lease lapse → standby/restart resumes)
      or a fenced `resume` control transition is added. If a control-kind is
      added it is a schema change: new ADR + generation-compatibility note +
      P07 lifecycle extension. Freeze before Loop 4 (interference kills will
      hit this path constantly).
- [ ] D-0801: fragment layout cache + canonical layout identity.
- [ ] D-0802: reduction order, accumulation dtype, deterministic mode
      (bfloat16 transport / float32 accumulation contract preserved).
- [ ] D-0803: LFE core affinity, NUMA, thread/RSS/I/O budgets.
- [ ] D-0804: typed validation-token lifetime and invalidation (epoch/head
      change, corruption suspicion → token discard + strict revalidation).
- [ ] D-0805: scanner cursor is process-local and reconstructible from
      storage; `range_get` chunk-verification policy (whole-object digest at
      finalize vs per-chunk).
- [ ] D-0806: telemetry event schema, monotonic-clock spans + causal IDs (no
      fabricated global clock), sampling overhead budget.
- [ ] D-0807: multi-FWO trigger thresholds + maximum speculative window.
- [ ] D-0808: bundle canonical fragment order, parent binding, proposal
      consumption, serial-equivalence proof obligation.
- [ ] D-0809: bundle failure/cancellation/lifecycle interface.
- [ ] D-0810: matched topology/resource accounting for every performance claim.

## 4. Expected repository changes

```text
fs_diloco/optimizer/        fragment_access.py, streaming_reduce.py, buffers.py
fs_diloco/distributed_syncer/ scanner.py, prefetch.py, execution_budget.py,
                              bundle_plan.py + bundle_commit.py (gate-only)
fs_diloco/telemetry/        events.py, recorder.py, summaries.py,
                            topology_metrics.py, interference.py
fs_diloco/storage/posix.py  true range_get (seek-based)
fs_diloco/proposal_catalog.py  cross-scan validation cache, digest-only entries
fs_diloco/learner.py + learner_protocol/publication.py  single-copy payload publication
fs_diloco/syncer.py         cadence-gated full materialization, skip-unchanged fragments
fs_diloco/log/production.py O(selected) lineage check via replay-maintained maps
benchmarks/                 bench_fragment_access.py, bench_streaming_reduce.py,
                            bench_lfe_pipeline.py, bench_bundle_commit.py
scripts/miyabi/             profile_d8.sh, profile_d8_r2.sh
tests/performance_core/     test_fragment_equivalence.py, test_streaming_memory_bound.py,
                            test_validation_reuse.py, test_epoch_cancellation.py,
                            test_bundle_serial_equivalence.py, test_catalog_cache_coherence.py
```

Extend the existing `param_index` / `fragment_index` / `fragment_codec`,
`ProposalCatalog`'s `ValidatedProductionPayload`, and
`ProductionTransactionalLog` — no parallel layouts, scanners, or validation
truths. Direct gather/scatter must cover **both** learner publication and LFE
parent loading; optimizing only the LFE while learners still whole-model
flatten does not qualify as fragment-scope end-to-end copy.

## 5. Explicitly not doing

No per-fragment heads by default. No durable-authority performance caches. No
synthetic bandwidth numbers substituting for D8 E2E. No CUDA kernels without
evidence. No changes to selection/quorum/outer-optimizer semantics. No trading
validation, fsync, digests, or fencing for speed. No prefetch reuse across
epochs/heads.

## 6. Execution loops

### Loop 1 — Critical-path baseline (profile-first)

Freeze matched C9/D8/D8-R2 workloads and the stage schema; instrument
discovery, validation, read, reduce, outer step, object publication, PFT
visibility, winner validation, coordination, CAS, materialization, adoption.
Record copy bytes, read/SHA/finite-check counts, peak RSS, storage-op
counters (from the H0 header-only backend), GPU step interference, and the
lifecycle scan breakdown. Run targeted 1-node benchmarks, then D1, then D2.
Analysis fails closed when any metric lacks stage/role/epoch/FWO identity or
topology/resource attribution. Telemetry writer crash or lag must not perturb
training. **Stop when:** every committed transition and loser attempt can be
reconstructed from raw events.

### Loop 2 — Direct fragment access, single-copy publication, buffer isolation

Direct gather/scatter over cached canonical layout for LFE parent loading
*and* learner publication; bounded pinned CPU buffers with explicit
ownership/lifetime. Fold in review M19/M20: learners serialize the payload
once and publish one authoritative copy (mailbox sidecar points at it);
`publish_materialized_view` skips unchanged fragment versions and honors
`fragments.materialize_full_every_events` (or the key is deleted by explicit
decision). Decide/land review M10 (control-plane sidecar dir-fsync or
RunSpec-derived rebuild) here — it is the same publication path.
RED harness: legacy-vs-direct across layouts/dtypes, updated/unupdated
fragments, optimizer-state mapping, copy-byte and RSS assertions; HARDEN:
non-contiguous tensors, shared parameters, mixed dtype, cancel/crash,
concurrent learner training, NUMA placement. **Stop when:** copies and I/O
grow with fragment (not model) size and learner GPU state is never corrupted.

### Loop 3 — Streaming reducer, validation reuse, bounded prefetch

Per-proposal streaming accumulation (typed validated input → accumulator →
release) so peak working set stays near O(fragment), not O(q × fragment).
Typed validation token: the same ObjectRef is read/SHA'd/finite-checked once
per attempt (review M18 — this includes the **committer's catalog scan loop**:
cache validated entries across rescans keyed by
(path, size, mtime, metadata_sha256); entries hold digests, payload bytes are
loaded per selected quorum). Cheap rejections precede payload I/O. True
seek-based `range_get` (review M17) per D-0805. Replace the O(N²) lineage scan
in `prepare_transition` with replay-maintained per-lineage maps (review M21).
HARDEN: midstream corruption, cancellation, stale-epoch token, slow Lustre,
listing duplicates/omissions. **Stop when:** reference equivalence holds,
object-read counters are bounded as specified, and the memory curve is flat
in q.

### Loop 4 — LFE resource-interference control

Sweep cores/threads/NUMA/prefetch/RSS/hedge modes; record GPU step time, CPU
utilization, memory-bandwidth proxy; assert budget violations. Explicit
resource budgets in launch/config; backpressure, priority/affinity, hedge
suppression; manifests record actual placement (audited, not declared).
Compare no-LFE shadow, factor-1, R2 matched runs. **Stop when:** default
budgets are chosen with evidence and negative trade-offs are reported.

### Loop 5 — Bounded concurrency / bundle evidence gate

First prove (or fail to prove) the single-FWO/head-serialization bottleneck
from Loop 1/3/4 traces against D-0807 thresholds. If not triggered: archive
why single-FWO suffices, keep interface tests, close A16–A18 as
checker-accepted `not_applicable`; no bundle schema is written. If triggered:
bounded multi-FWO prepare from one parent; `CommitBundlePlan` fixes ordered
fragments and consumption; pure simulator proves equivalence with canonical
serial application; one final bundle transition, one head CAS. A bundle
changes commit/frontier/replay/reachability identity → new ADR, new
protocol-generation compatibility strategy, P07 lifecycle extension. HARDEN:
partial PFT sets, stale members, duplicate results, cancellation, large
manifests, lifecycle roots.

### Loop 6 — Optimized D8/D8-R2 acceptance

On the final clean commit: D8 factor-1 and D8-R2 50×10 with matched C9, at
least one executor/committer fault, raw stage profiles collected.
Head/epoch change cancels prefetch; strict fallback exercised; corrupt
successor; telemetry-missing fails closed. Full P07 lifecycle regression suite
runs on this commit. **Stop when:** optimized paths change no digests or
invariants and performance numbers are reproducible.

## 7. Invariants and failure injection

Optimized/reference/CRS share policy and numeric semantics. Validation,
digests, fencing cannot be disabled by performance switches. Every
cache/prefetch/cursor is deletable. Head/epoch changes invalidate tokens and
prepared planning windows. Bundles (if any) keep exactly one global head CAS
and serial equivalence. LFE budgets protect the learner GPU first. Telemetry
never participates in correctness.

## 8. Acceptance

- [ ] P08-A01: direct fragment access equivalent to legacy/reference.
- [ ] P08-A02: measured copies/I/O at fragment scope end-to-end (learner
      publication included; single authoritative payload copy).
- [ ] P08-A03: streaming reducer equivalent to reference.
- [ ] P08-A04: peak working set no longer O(q × fragment).
- [ ] P08-A05: typed validation reuse with hard read/SHA/finite-check bounds,
      covering both LFE attempts and committer catalog rescans.
- [ ] P08-A06: cheap rejection precedes payload I/O.
- [ ] P08-A07: scanner restart/duplicates/list omission never affect
      correctness; cursors reconstructible from storage.
- [ ] P08-A08: head/epoch jump cancels prefetch/tokens and strict-revalidates.
- [ ] P08-A09: every commit and loser attempt reconstructible from telemetry.
- [ ] P08-A10: raw manifests/events keep fail/inconclusive/retry lineage.
- [ ] P08-A11: LFE affinity/NUMA/RSS/threads/in-flight budgets in manifests
      and audited against actual placement.
- [ ] P08-A12: GPU interference measured with no-LFE, factor-1, R2 matched
      data.
- [ ] P08-A13: bfloat16-transport/float32-accumulation contract unchanged.
- [ ] P08-A14: same-FWO primary/backup honor frozen backend/thread/reduction
      identity bitwise; numerics-affecting resource settings form a distinct
      implementation identity and go through numeric comparison.
- [ ] P08-A15: single-FWO bottleneck gate has an explicit archived conclusion.
- [ ] P08-A16–A18: bundle schema/equivalence/fault suites pass **or** are
      checker-accepted `not_applicable` with the profile evidence.
- [ ] P08-A19: still no per-fragment heads or second authority.
- [ ] P08-A20: D1/D2 optimized correctness gates pass.
- [ ] P08-A21: D8 50×10 optimized terminal + raw profile.
- [ ] P08-A22: D8-R2 controlled-fault optimized terminal.
- [ ] P08-A23: no SQLite/embedded DB on the active surface or artifacts.
- [ ] P08-A24: D-0800 error-stop decision implemented and tested (crash →
      restart → resume path exercised end-to-end under the chosen semantics).
- [ ] P08-A25: report/checksums/clean commit; P07 regressions pass;
      `STATE.yaml.next_action = P10`.

## 9. Maker–Checker

Checker verifies benchmarks cannot disable validation/fsync, manually triggers
a head jump to invalidate prefetch, audits PBS/affinity actuals versus
declarations, and re-runs the P07 lifecycle regressions on the P08 verified
commit. Checker signs the Loop 5 gate conclusion either way.

## 10. Startup instruction (copyable)

```text
Execute P08 from the H0 verified commit. Re-measure baselines first (H0 changed
listing costs), then: direct fragment I/O for learner publication and LFE
loading with single-copy payload publication; streaming reducer with typed
validation reuse covering committer catalog rescans; true range_get; bounded
prefetch and CPU/NUMA isolation; O(selected) lineage checks; cadence-gated
materialization; full-path telemetry. Freeze D-0800 error-stop semantics.
Profile before deciding the multi-FWO/one-CAS bundle gate; not_applicable with
evidence is a valid closure. Keep single global head and all validation and
fencing. Pass P07 regressions and the P08 checker, then proceed to P10.
```
