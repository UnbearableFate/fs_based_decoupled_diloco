---
title: "Review-Fixing Plan Bundle — docs/review findings, loop-engineering style"
version: "1.0"
date: "2026-07-13"
basis_commit: "8b5121344294d202428187dfeafb0697ad38e02d"
basis_branch: "codex/duraloco-p08r-replay-440s"
companion_review: "docs/review/README.md"
phase_loop: "ORIENT -> SPECIFY/RED -> IMPLEMENT/GREEN -> HARDEN -> CHECK -> PERSIST"
---

# Review-Fixing Plans (RF series)

Fixes for the 24 findings in `docs/review/` (D-01…D-11 design, C-01…C-13
code), organized into six loop-engineered phases. Every phase follows the
project loop `ORIENT → SPECIFY/RED → IMPLEMENT/GREEN → HARDEN → CHECK →
PERSIST`; a phase is completed only when every acceptance ID has evidence and
an independent checker report says PASS (or PASS_WITH_FOLLOWUPS with no
required-gate follow-up).

## Phase route

```text
(basis 8b51213, P08R in progress)
   → RF-01 Runtime hygiene                 [P0 — unit-test only, land first]
   → RF-02 Corruption observability        [storage semantics, 1-node contract]
   → RF-03 Critical-path I/O               ┐ parallel after RF-02
   → RF-04 Hedging semantics decision      ┘ (RF-04 has a user decision gate)
   → RF-05 Scalability generation          [schema change; largest phase]
   → RF-06 Trust, clocks, platform ops     [items independent; interleave]
```

RF-01/02 are prerequisites for honest measurement in RF-03 (C-01's quadratic
telemetry scan and C-07's polling would otherwise contaminate benchmarks —
the same measurement-poisoning logic that motivated H0).

## Finding → phase registry

| Finding | Sev. | Phase | Acceptance IDs |
|---|---|---|---|
| C-01 unbounded op history | HIGH | RF-01 | RF01-A01, A02 |
| C-02 `ru_maxrss` budget | HIGH | RF-01 | RF01-A03, A04 |
| C-04 per-update backend | MED | RF-01 | RF01-A05 |
| C-12 per-call `atexit` | LOW | RF-01 | RF01-A06 |
| C-10 docs/ tree broken | LOW | RF-01 | RF01-A07 |
| C-03 silent corrupt skip | MED | RF-02 | RF02-A01, A02 |
| C-06 swallowed snapshot failure | MED | RF-02 | RF02-A03 |
| C-11 tmp-file leak | LOW | RF-02 | RF02-A04 |
| C-08 header-only idempotent put | LOW | RF-02 | RF02-A05 |
| D-05 double payload publication | MED | RF-03 | RF03-A01…A03 |
| C-13 materialization default | LOW | RF-03 | RF03-A04 |
| D-04 serial committer pipeline | MED | RF-03 | RF03-A05…A07 |
| C-07 result-wait rereads + clocks | MED | RF-03 | RF03-A08, A09 |
| C-09 range_get doc drift | LOW | RF-03 | RF03-A10 |
| D-06 hedging waits for both | MED | RF-04 | RF04-A01…A04 |
| D-01 unbounded consumption set | HIGH | RF-05 | RF05-A01…A03 |
| D-02 O(n²) prefix digest | HIGH | RF-05 | RF05-A04, A05 |
| D-03 history-embedding snapshots | HIGH | RF-05 | RF05-A06…A09 |
| D-07 unverified learner adoption | MED | RF-06 | RF06-A01, A02 |
| D-08 unprobed clock skew | MED | RF-06 | RF06-A03, A04 |
| C-05 lock-inode growth | MED | RF-06 | RF06-A05 |
| D-09 lease-parameter tuning path | LOW | RF-06 | RF06-A06 |
| D-11 no DR export | LOW | RF-06 | RF06-A07 |
| D-10 member reintegration | LOW | **deferred** — future phase; cross-ref `plans/duraloco_next_plans` and the forward-plan route; requires its own charter | — |

## Ground rules (all phases)

1. **Miyabi safety.** Login nodes: editing, `bash -n`, `ruff`,
   `scripts/agent/*` checks, and pure-stdlib/memory-backend pytest **only
   where the suite is already login-safe per repo policy; otherwise tests run
   inside PBS**. Runtime validation escalates 1-node → 2-node → 8-node; one
   8-node attempt per validated shape (after a terminal failure: preserve
   evidence, root-cause review, smallest targeted benchmark, re-qualify
   1→2 node on the same commit before the next 8-node attempt).
2. **RED first.** Every fix lands behind a failing test that reproduces the
   finding at the cited file:line. A finding whose RED test cannot be written
   goes back to ORIENT — it means the finding is not yet understood.
3. **No silent authority/schema change.** RF-01…RF-04 and RF-06 must leave
   committed-object identities bit-identical for identical inputs (checked by
   the reference suite). Only RF-05 may change schema, and only behind a new
   run generation.
4. **Performance claims need benchmarks.** Any fix sold as "faster" carries
   the smallest targeted compute benchmark proving it (P08R rule, applied
   proactively). Numbers go into the phase report as immutable artifacts.
5. **Checker gate.** Each phase names its checker procedure in CHECK; PERSIST
   updates `plans/duraloco/STATE.yaml`, writes the phase report under this
   directory, and records follow-ups explicitly.

## Files

| Phase | File |
|---|---|
| RF-01 | `RF01_RUNTIME_HYGIENE.md` |
| RF-02 | `RF02_CORRUPTION_OBSERVABILITY.md` |
| RF-03 | `RF03_CRITICAL_PATH_IO.md` |
| RF-04 | `RF04_HEDGING_SEMANTICS.md` |
| RF-05 | `RF05_SCALABILITY_GENERATION.md` |
| RF-06 | `RF06_TRUST_CLOCKS_PLATFORM.md` |
