---
plan_id: "RF-03"
title: "Critical-Path I/O — zero-copy promotion, cadence, pipelining, wait loop"
status: "planned"
basis_commit: "8b5121344294d202428187dfeafb0697ad38e02d"
findings: ["D-05", "C-13", "D-04", "C-07", "C-09"]
depends_on: ["RF-01", "RF-02"]
runtime_validation: "targeted benchmarks per fix, then 1 → 2 → 8 node; one D8 attempt"
---

# RF-03 — Critical-Path I/O

## Mission

Remove the avoidable model-sized payload movement and idle time from the
per-transition critical path, with a measured before/after for every change
(P08R rule applied proactively). Committed identities must remain
bit-identical for identical inputs — these are I/O-path changes only.

## ORIENT

Re-read the stage decomposition in
`plans/duraloco/phases/P08R_R2_527S_ANALYSIS.md`; code:
`executor.py:167-224`, `committer.py:232-323,944-1136,1359-1396`,
`production.py:1037-1055`, `syncer.py:147-250`, `config.py:164`. Freeze the
benchmark harness first: per-stage counters (post-RF-01) + elapsed contract
on a 2-node shape are the measurement baseline.

## Design decisions to freeze

- **D-RF0301 (D-05)** — prepared→authority payload promotion without byte
  copy. Preferred: the backend gains `promote_immutable(src_key, dst_key,
  expected_sha256, expected_size)`; same-device roots use `os.link` of the
  envelope after header verification (envelope is identical bytes; only the
  key differs — key is not encoded in the envelope), recording a `promoted`
  operation; cross-device falls back to copy. The committer's
  `prepare_transition` path uses promotion for `new_params`/`new_outer_state`
  when the validated PFR refs carry the same digests.
- **D-RF0302 (C-13)** — `materialize_full_every_events=None` means "only at
  authoritative stop / snapshot", and D8 configs set an explicit cadence ≥
  fragment count. Learner-facing per-fragment files are unaffected.
- **D-RF0303 (D-04b/c)** — `publish_materialized_view` runs inside the
  lease-heartbeat substage worker (off the CAS critical path); the loop-end
  `time.sleep(0.5)` becomes `config.sync.commit_loop_idle_seconds` and is
  skipped when the catalog already holds ≥ quorum_min validated candidates.
- **D-RF0304 (D-04a)** — overlap: while awaiting the PFR for fragment f, the
  committer may pre-scan and pre-validate catalog entries for the *next*
  scheduler fragment (validation tokens are head/scope-bound and already
  invalidate correctly on head change). FWO publication order is unchanged;
  no second in-flight FWO in this phase.
- **D-RF0305 (C-07)** — `_wait_for_result` memoizes loaded attempts by marker
  key (immutable objects); poll interval backs off 100 ms → 500 ms after the
  first second; hedge elapsed time computed from the committer's own
  monotonic dispatch clock, removing the cross-host `published_at`
  comparison from eligibility.
- **D-RF0306 (C-09)** — storage-contract doc updated for v2 verified chunked
  `range_get` (with the v1 full-read fallback stated).

## Loops

### Loop 1 — Benchmark harness (RED for the phase)
- **RED:** a 2-node targeted benchmark script reports per-transition bytes
  written/read by stage and wallclock per stage; run at basis commit to
  freeze the "before" numbers as immutable artifacts. Without this, no GREEN
  below may claim improvement.

### Loop 2 — D-RF0301 zero-copy promotion
- **RED:** unit: `promote_immutable` same-device creates the dst key with
  identical envelope, digest verified, no payload-bytes-read growth beyond
  header; committer integration test asserts params/outer bytes are written
  exactly once per transition (counter-based — fails today at two).
- **GREEN:** implement; wire into `prepare_transition` via a promotion-aware
  put in the production log.
- **HARDEN:** crash-stage tests around promotion (link vs fsync ordering);
  cross-device fallback test; GC/reachability regression: promoted objects
  reachable under both keys are protected; hardlinked inode delete semantics
  covered in `delete_batch` tests. 2-node benchmark: per-transition write
  bytes ≈ halved on the payload path.

### Loop 3 — D-RF0302/0303 cadence and off-path materialization
- **RED:** counter test: with cadence configured, a non-cadence transition
  writes no full-model file (fails today under default `None`); committer
  test: CAS-to-next-dispatch interval excludes materialization time (assert
  via stage telemetry ordering).
- **GREEN:** implement both; update D8 configs explicitly.
- **HARDEN:** learner adoption regression (fragment files still fresh);
  stop/snapshot still materializes; benchmark delta recorded.

### Loop 4 — D-RF0304 overlap + D-RF0305 wait loop
- **RED:** wait-loop test with stub storage counts object reads across polls
  — today re-reads every marker per poll; assert each attempt loaded once.
  Hedge test: eligibility fires on monotonic elapsed even when host clocks
  disagree (inject skewed `published_at`). Overlap test: pre-validated
  next-fragment tokens are used (validation counter does not re-pay) and are
  discarded on head jump.
- **GREEN:** implement.
- **HARDEN:** CAS-conflict during overlap discards pre-validation (no stale
  selection); hedged/active_active/warm modes re-run through
  `tests/distributed_syncer/test_hedged_execution.py` extended matrix.

### Loop 5 — Qualification
1-node → 2-node with the harness; one 8-node D8 attempt on the phase commit
with the standard elapsed contract. Success target (frozen before the run):
≥25% reduction in mean non-lifecycle `publish_to_commit_seconds` vs the
matched basis D8 numbers, with all correctness gates green.

## CHECK

| ID | Acceptance | Evidence |
|---|---|---|
| RF03-A01 | Payload bytes written once per transition (counters) | pytest + benchmark |
| RF03-A02 | Promotion crash/GC/delete matrix green | pytest |
| RF03-A03 | Cross-device fallback correct | pytest |
| RF03-A04 | No full-model write off-cadence; stop/snapshot still writes | pytest |
| RF03-A05 | Materialization off critical path (telemetry ordering) | pytest + telemetry |
| RF03-A06 | Idle sleep configurable/skipped under backlog | pytest |
| RF03-A07 | Overlapped validation reused and safely discarded on conflict | pytest |
| RF03-A08 | Wait loop loads each attempt once; backoff active | pytest |
| RF03-A09 | Hedge timing monotonic, skew-immune | pytest |
| RF03-A10 | Storage contract documents v2 range semantics | doc diff + check_docs |
| RF03-A11 | D8 run: frozen improvement target met, all gates green | elapsed contract + report |

Checker: independent verification that reference-suite committed digests are
unchanged vs basis; benchmark artifacts immutable; D8 evidence complete.

## PERSIST

`RF03_PHASE_REPORT.md` with before/after tables; STATE.yaml; explicitly
record that multi-in-flight FWO (D-04 full pipelining) remains out of scope
→ follow-up candidate after RF-05.
