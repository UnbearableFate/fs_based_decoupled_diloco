---
plan_id: "RF-02"
title: "Corruption Observability — surface what the storage layer hides"
status: "planned"
basis_commit: "8b5121344294d202428187dfeafb0697ad38e02d"
findings: ["C-03", "C-06", "C-11", "C-08"]
depends_on: ["RF-01"]
runtime_validation: "unit + fault-injection; 1-node storage contract check"
---

# RF-02 — Corruption Observability

## Mission

Make every corruption the system already tolerates *visible*: unreadable
objects in listings, invalid pinned snapshots during replay, leaked temp
files, and payload corruption discovered at idempotent-put time. No change to
fail-closed behavior — only to what gets reported and repaired.

## ORIENT

Read `fs_diloco/storage/posix.py:539-589,591-641,815-844`,
`fs_diloco/log/replay.py:1054-1082`, `fs_diloco/log/reachability.py`,
lifecycle report construction in `committer.py:1315-1358`. Enumerate every
`list_prefix` caller and decide which need the unreadable bucket (lifecycle
inventory: yes; result-wait marker scan: log-only).

## Design decisions to freeze

- **D-RF0201** — `list_prefix` keeps its signature; add
  `list_prefix_report(prefix) -> {keys, unreadable: tuple[(key, reason)]}`.
  Lifecycle/reachability inventory switches to the report form and counts
  `unreadable_object_count` in cycle reports; a nonzero count is a corruption
  signal (warning event), never an automatic delete.
- **D-RF0202** — replay's pinned-snapshot validation failure keeps its
  fallback but records a structured event (key, commit_seq, error type) into
  replay telemetry; exception scope narrowed from bare `Exception` to
  `(VerificationError, IntegrityError, NotFound, ValueError)`.
- **D-RF0203** — lifecycle inventory counts `.duraloco-tmp` files and deletes
  those older than a frozen grace age (visible names are only created by
  `link`/`replace`, so aged temps are provably unreferenced).
- **D-RF0204** — `put_immutable` idempotent hit verifies payload bytes when
  size ≤ a frozen threshold (manifests); above threshold unchanged. On
  mismatch with caller-proven identical digest: atomic in-lock repair via the
  normal temp+publish path, recorded as `repaired` in operation counters.

## Loops

### Loop 1 — C-03 unreadable bucket
- **RED:** fault-injection test writes a valid object, truncates/garbles its
  envelope header out-of-band, asserts today's `list_prefix` hides it and the
  lifecycle report shows nothing; new assertion: report form lists it under
  `unreadable` and the cycle report counts it.
- **GREEN:** D-RF0201.
- **HARDEN:** GC-safety regression: an unreadable object must never appear in
  candidates (extend `tests/lifecycle/test_gc_concurrency.py` matrix);
  reachability explain output includes the unreadable class.

### Loop 2 — C-06 snapshot-failure telemetry
- **RED:** corrupt a pinned snapshot object in a fixture log; strict replay
  must still succeed (existing behavior) *and* the new telemetry event must
  be present — assert on the event, which does not exist today.
- **GREEN:** D-RF0202.
- **HARDEN:** snapshot-mode replay fallback path asserts the same event;
  lifecycle cycle report gains `invalid_pinned_snapshot_count`.

### Loop 3 — C-11 temp janitor
- **RED:** stage-hook crash between temp write and publish leaves a
  `.duraloco-tmp`; assert lifecycle inventory currently misses it, then
  assert the janitor counts and (past grace) removes it while an *in-flight*
  temp (age < grace) survives.
- **GREEN:** D-RF0203.
- **HARDEN:** concurrency test: janitor racing an active publish never
  deletes the temp the publisher is about to link (grace age ≫ publish
  window; assert via stage hooks).

### Loop 4 — C-08 idempotent verify/repair
- **RED:** valid header + corrupt payload on disk; `put_immutable` with the
  correct bytes currently returns `idempotent` and leaves corruption; assert
  it must detect and repair (small object) and that a subsequent
  `verified_get` succeeds.
- **GREEN:** D-RF0204.
- **HARDEN:** repair is atomic under the key lock (crash-stage tests across
  the repair publish); threshold documented in the storage contract.

## CHECK

| ID | Acceptance | Evidence |
|---|---|---|
| RF02-A01 | Unreadable objects surfaced in report form + lifecycle counts | pytest |
| RF02-A02 | Unreadable objects never GC candidates (regression) | pytest |
| RF02-A03 | Invalid pinned snapshot produces telemetry on both replay paths | pytest |
| RF02-A04 | Aged temp files counted and reclaimed; in-flight temps safe | pytest |
| RF02-A05 | Small-object idempotent puts verify and repair corrupt payloads atomically | pytest |

Checker: fault-injection suite green on clean clone; 1-node storage contract
worker run (PBS) showing report-form listing and repair behavior on Lustre;
storage-contract doc updated to describe all four behaviors (this also
retires part of C-09's doc drift — the rest lands in RF-03).

## PERSIST

`RF02_PHASE_REPORT.md`; STATE.yaml update; follow-up recorded if any
`list_prefix` caller intentionally stays on the plain form.