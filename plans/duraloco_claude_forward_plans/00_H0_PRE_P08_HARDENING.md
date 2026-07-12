---
plan_id: "H0"
title: "Pre-P08 Hardening: Evidence Integrity, Storage Listing Cost, Platform Lock Probe"
status: "completed"
date: "2026-07-12"
planning_basis_commit: "c099adc3c3a99127569a7d9bf38a58547022173c"
qualified_runtime_commit: "f167a07c49339ba42d14f8a5873fe2c8781884d4"
independent_checker_commit: "04e0a8634b0e9d7c4cd55c5593081a0ca969a060"
independent_checker_job: "2369726.opbs"
target_branch: "codex/duraloco-h0-pre-p08-hardening"
depends_on: ["P07"]
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
next_phase: "P08"
estimated_size: "small — one loop cycle, no protocol/schema changes"
review_findings: "docs/reviews/20260712_code_review.md (H1–H3, M4, M5, M9, M11, H15, H16, plus quick L-items)"
---

# H0 — Pre-P08 Hardening

## 1. Mission

Fix the defects that would either falsify P08+ evidence or poison P08's
profile-first baselines, without touching protocol schemas, optimizer
semantics, or committed-object identities. Everything in H0 is
behavior-preserving on the happy path; the changes are visible only under
crash, race, or cost measurement.

H0 exists so P08 Loop 1 can freeze baselines that measure the design, not a
listing pathology, and so every later committed stop fact can be trusted.

## 2. Scope — must complete

### 2.1 Committer evidence integrity (review H2, H3, M4, M5)

- [x] `run_committer` gains the same exception discipline as `run_syncer`:
      `except Exception: stop_reason = "error"; raise` before `finally`.
- [x] The `finally` block tolerates `CommitConflict` on `commit_stop`, rebuilds
      the view, and publishes `stop.json` only when
      `view.authoritative_stop is not None`; otherwise logs
      `stop_not_published_without_authority`. No exception may escape the
      `finally` and mask the original error.
- [x] Main loop handles `CommitConflict`/`InjectedTimeout` on
      `prepare_transition`/`commit_prepared` with force-full replay + continue
      (or clean exit on observed authoritative stop), mirroring `syncer.py`.
- [x] `_wait_for_result` renews the fenced lease at
      `renew_interval_seconds` cadence while polling (reuse
      `_run_lifecycle_substage` or renew inline). Assert in config validation
      that `sync.grace_window < coordination.lease_ttl_seconds -
      coordination.renew_margin_seconds`.

### 2.2 Storage listing/head cost (review H15, H16)

- [x] `PosixStorageBackend.list_prefix(prefix)` walks only the prefix subtree.
- [x] Listing and `head()` validate the checksummed envelope **header only**
      (bounded read); full payload verification remains in `get`/
      `verified_get`. `head()` returns sha/size from the header.
- [x] `put_immutable` idempotency compares header digest + size instead of full
      bytes once header-only `head` exists.
- [x] Fault-injection and storage-contract tests updated: a payload-corrupted
      object must still be *listed* (discovery) but must fail `verified_get`;
      reachability/GC behavior on such an object is asserted explicitly
      (unknown/quarantine path, never silent deletion).

This is deliberately in H0, not P08: it changes no observable semantics
(listing was already only discovery) but changes every cost number P08 will
freeze.

### 2.3 Platform lock probe (review M11)

- [x] `storage/capability_probe.py` gains a multi-process advisory-lock scope
      probe; `PosixStorageBackend` records the probe result in
      `StorageCapabilities`.
- [x] A two-node Miyabi probe job demonstrates cross-node `flock` exclusion on
      the target Lustre mount (or documents `-o flock` verification via mount
      options) and archives the evidence. Backend construction on shared roots
      fails closed when the capability is absent and
      `require_cross_node_lock=True` (default for authority roots).

### 2.4 Dormant-bug and race fixes (review H1, M6, M7, M9)

- [x] Rename the shadowing loop variable in `run_fragment_learner`
      (`learner.py:851`) and add a functional multi-fragment test
      (`num_fragments >= 2`) asserting per-update metadata `fragment_id ==
      interval.fragment_id` and round-robin coverage of all fragments.
- [x] `resolve_mutation` (and `_optimizer_transition_count` fallback) look up
      commits by `commit_seq`, never by list index; regression test resolves a
      pre-snapshot-base request id after compaction.
- [x] Heartbeats carry `run_generation`; `_heartbeat_snapshot` and
      `validate_heartbeat` filter on it. Regression test: stale
      previous-generation heartbeats cannot satisfy
      `finite_local_training_complete`.
- [x] `LeaseManager.acquire` NotFound branch converts a lost `put_if_absent`
      race (`ImmutableConflict`) into idempotent return or
      `CoordinationConflict`; two-process bootstrap race test.

### 2.5 Quick hygiene (review L12, L13, L26, L27; zero-risk only)

- [x] `ruff --fix` for unused imports; bind B023 lambdas with default args;
      move the dead `loss is None` check above the division; dtype `KeyError`
      → typed `PAYLOAD_DTYPE` protocol error.
- [x] Add ruff (F, B, PLE rule families) to the local static gate so these
      classes cannot re-enter.

## 3. Explicitly out of scope (deferred, with owners)

- `range_get` streaming, catalog validation cache, single-copy payload
  publication, materialization cadence, O(N²) lineage check → **P08**
  (they change performance-relevant behavior P08 must measure before/after).
- Error-stop semantics decision (review M8: whether an `"error"` stop should be
  terminal for the generation, or a fenced resume transition should exist) →
  frozen as a **P08 design decision D-0800** because it may need a control-kind
  addition; H0 must not touch protocol surface.
- `atomic_io` directory fsync for control-plane sidecars (review M10) →
  **P08 Loop 2** alongside the publication-path rework, OR pulled into H0 if
  trivially isolated; maker's choice, checker verifies either way.
- `merge.py` retirement, wikitext streaming validation, PBS log relocation →
  **P11** (repo/ops hygiene loop).

## 4. Loop plan (single cycle)

**RED.** Reproduce each defect as a failing test first: committer crash →
`completed` stop fact; committer CAS-loss crash; lease expiry during long
result wait (fault-injected slow executor); multi-fragment metadata mismatch;
suffix-only `resolve_mutation`; cross-generation heartbeat bleed; lease
bootstrap race; a benchmark asserting `list_prefix` byte-read upper bounds.

**GREEN.** Land fixes in §2 order; no schema or identity changes; all P07
regression suites must pass unchanged (bitwise: committed digests, view
digests, checker counterexamples).

**HARDEN.** Re-run the P07 lifecycle regressions and the P06C D2-R2 fault
tapes on the H0 commit; run one D1 and one D2 real job; run the two-node lock
probe job.

**CHECK/PERSIST.** Independent checker verifies: (a) every new test fails on
`c099adc` and passes on the H0 commit; (b) committed-object digests for a
replayed P07 tape are identical pre/post H0; (c) `list_prefix`/`head` byte
counters dropped by the predicted orders of magnitude; (d) lock probe evidence
archived. Artifacts + checksums under `artifacts/duraloco/H0/`.

## 5. Acceptance

- [x] H0-A01: committer crash paths commit `error` (never `completed`) stop
      facts; `finally` never raises over the original exception.
- [x] H0-A02: committer survives head conflict via strict replay; survives a
      lease-length executor wait without losing the lease.
- [x] H0-A03: `list_prefix`/`head` are prefix-scoped and header-only; payload
      bytes read during a D2 lifecycle cycle drop accordingly (counter
      evidence archived); corruption-detection contract tests still pass.
- [x] H0-A04: cross-node lock probe evidence archived; backend fails closed
      without the capability on authority roots.
- [x] H0-A05: multi-fragment learner test passes; round-robin restored.
- [x] H0-A06: `resolve_mutation`, heartbeat generation-scoping, and lease
      bootstrap race regressions pass.
- [x] H0-A07: all P07 acceptance regressions pass unchanged on the H0 commit;
      no committed identity changed.
- [x] H0-A08: static gate includes ruff; active surface still free of
      SQLite/embedded DBs.
- [x] H0-A09: report/checksums/clean commit; `STATE.yaml.next_action = P08`
      with H0 commit as P08's `planning_basis_runtime_commit`.

## 6. Startup instruction (copyable)

```text
Execute H0 from P07 verified commit c099adc. Fix committer stop-fact integrity,
head-conflict replay, and in-wait lease renewal; make posix list_prefix/head
prefix-scoped and header-only without weakening get-path verification; probe
cross-node flock on Lustre and fail closed without it; fix the fragment_id
shadowing bug with a real multi-fragment test; fix resolve_mutation indexing,
heartbeat generation scoping, and the lease bootstrap race. No schema or
committed-identity changes. All P07 regressions must pass bitwise-unchanged.
Checker-verified H0 commit becomes the P08 baseline.
```
