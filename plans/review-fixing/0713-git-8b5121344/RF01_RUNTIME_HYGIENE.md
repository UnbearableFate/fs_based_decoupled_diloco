---
plan_id: "RF-01"
title: "Runtime Hygiene — leaks, budgets, per-call construction, docs move"
status: "planned"
basis_commit: "8b5121344294d202428187dfeafb0697ad38e02d"
findings: ["C-01", "C-02", "C-04", "C-12", "C-10"]
depends_on: []
runtime_validation: "1-node smoke only; no schema or identity change"
---

# RF-01 — Runtime Hygiene

## Mission

Remove the two HIGH code defects (unbounded operation history, lifetime-peak
RSS check) plus three hygiene items, without changing any committed identity,
so later phases measure the design instead of these pathologies.

## ORIENT

Read `fs_diloco/storage/posix.py:153,201-235`, `fs_diloco/log/replay.py:1399`,
`fs_diloco/log/production.py:316-327`, `fs_diloco/distributed_syncer/executor.py:220`,
`fs_diloco/learner.py:535,627`, `fs_diloco/distributed_syncer/committer.py:609`,
`scripts/agent/check_docs.py`. Grep all consumers of `backend.history`
(contract worker, capability probe, fault injection, replay overlay) before
freezing decisions.

## Design decisions to freeze

- **D-RF0101** — backend gains per-operation monotonic `operation_counters`
  (same lock discipline as `read_counters`); list `history` becomes opt-in
  (`record_history=False` default; probes/contract workers opt in; wrappers
  forward both).
- **D-RF0102** — replay/production telemetry reads counters, never scans
  `history`.
- **D-RF0103** — LFE budget measures current RSS (`/proc/self/statm`; fallback
  `ru_maxrss` delta per order), checked **before** payload publication;
  breach raises typed `ExecutorBudgetExceeded`, fatal for the process
  (supervisor restarts), never for all future orders of a live process.
- **D-RF0104** — one `PosixStorageBackend` per learner process, passed into
  `write_update` / `write_fragment_update` / recovery helpers.
- **D-RF0105** — drop `atexit` in `run_committer`; the `finally` close is the
  single owner.
- **D-RF0106** — docs tree merged atomically: `docs-codex/` +
  `docs/architecture|review` into `docs/`, with `README.md` links and
  `check_docs.py` CURRENT_DOCS updated in the same commit.

## Loops

### Loop 1 — C-01 counters
- **RED:** 10k puts/gets on a default backend must leave zero history entries
  with exact counters (fails today); replay's get-count sourcing must work on
  a history-disabled backend.
- **GREEN:** D-RF0101/0102; migrate every consumer found in ORIENT.
- **HARDEN:** 8-thread concurrency test with exact counters; fault-injection
  wrapper still deterministic; ruff clean.

### Loop 2 — C-02 RSS budget
- **RED:** after a simulated transient spike (allocate/free ~2× budget), a
  second `execute_work_order` must succeed (fails today with `MemoryError`);
  breach must be detected before any marker is published (assert no orphan
  marker).
- **GREEN:** D-RF0103.
- **HARDEN:** breach publishes typed failure evidence; case added to the
  executor test matrix.

### Loop 3 — C-04 / C-12 construction hygiene
- **RED:** publishing N proposals constructs exactly one backend (count via
  construction hook); repeated `run_committer` calls do not grow
  `atexit._exithandlers`.
- **GREEN:** D-RF0104/0105.
- **HARDEN:** 1-node smoke: fixed-seed proposal identities identical to the
  basis commit.

### Loop 4 — C-10 docs move
- **RED:** capture the current failing `check_docs.py` output (broken links).
- **GREEN:** D-RF0106 in one commit.
- **HARDEN:** `check_docs.py` extended to cover `docs/architecture/` and
  `docs/review/`; passes clean.

## CHECK

| ID | Acceptance | Evidence |
|---|---|---|
| RF01-A01 | Zero history entries by default; counters exact under concurrency | pytest |
| RF01-A02 | Telemetry sources counters; no history scan in production paths | pytest + grep |
| RF01-A03 | Post-spike orders succeed; breach detected pre-publication | pytest |
| RF01-A04 | Breach emits typed failure evidence; process-fatal semantics documented | pytest + docs |
| RF01-A05 | One backend per learner process; identities unchanged vs basis | pytest + smoke log |
| RF01-A06 | No atexit accumulation | pytest |
| RF01-A07 | `check_docs.py` PASS on merged tree | checker output |

Checker: independent clean-clone run of the login-safe suite +
`scripts/agent/*`; reference-suite digest stability versus basis.

## PERSIST

Write `RF01_PHASE_REPORT.md` here; update `plans/duraloco/STATE.yaml`;
record intentional follow-ups explicitly.