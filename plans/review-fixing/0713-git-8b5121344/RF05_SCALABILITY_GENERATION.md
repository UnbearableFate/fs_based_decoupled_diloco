---
plan_id: "RF-05"
title: "Scalability Generation — bounded frontiers, chained digests, state snapshots"
status: "planned"
basis_commit: "8b5121344294d202428187dfeafb0697ad38e02d"
findings: ["D-01", "D-02", "D-03"]
depends_on: ["RF-01", "RF-02", "RF-03"]
runtime_validation: "reference model first; memory-backend long horizon; 1 → 2 → 8 node"
schema_change: "YES — protocol v3 objects behind a new run generation; no v2 authority is rewritten"
---

# RF-05 — Scalability Generation

## Mission

Remove the three unbounded-growth mechanisms (consumption sets, prefix
digests, history-embedding snapshots) in one coherent protocol revision, so
per-transition cost, replay cost, snapshot size, and lifecycle time are flat
in run length. This is the phase that makes long-horizon runs (and true log
truncation) possible. It follows the M00→P04 pattern: reference model leads,
implementation follows, mutants police the boundary.

## ORIENT

Re-read `docs/review/02_design_findings.md` D-01/D-02/D-03 and
`docs/review/04_performance_scalability.md`; code:
`production.py:599,1138`, `commit.py:488`, `replay.py:322-335,1099,1313,1356`,
`production.py:744-793` (snapshot embedding), `snapshot.py`,
`committer.py:219-229,478-500` (I-008 audits), the staleness bounds in
`RunSpec`, and `testing/model_checker.py` mutants. Confirm the safety
argument in ORIENT before any code: *a proposal whose base falls outside
`max_global_staleness`/`max_fragment_staleness` can never validate, and
lineage sequences are strictly monotonic per (learner, session, fragment) —
therefore a windowed consumed-set + per-lineage watermark decides
double-inclusion identically to the full set.* Write this as a lemma in the
phase notes; it is the correctness core of D-RF0501.

## Design decisions to freeze

- **D-RF0501 (D-01)** — frontier v3 replaces `consumed_proposal_ids` with:
  `lineage_watermarks` (max committed sequence per lineage),
  `windowed_consumed_ids` (only proposals whose base is within the staleness
  window), and `retired_consumption_digest` (rolling SHA-256 accumulator over
  IDs leaving the window, in canonical retirement order).
- **D-RF0502 (D-02)** — committed-state digest becomes chained:
  `digest_0 = H(spec_digest ‖ canonical(genesis_frontier))`;
  `digest_i = H(digest_{i-1} ‖ canonical(commit_i) ‖ canonical(frontier_i) ‖
  parent_head_token_i)`. The frontier stores `chained_state_digest` so any
  suffix verifier can resume the chain.
- **D-RF0503 (D-03)** — snapshot v3 embeds *state*, not history: fragment
  refs/versions, D-RF0501 consumption structures, control-request map,
  coordination/membership projections, chained digest, plus refs (not bodies)
  of live-suffix objects. I-008 is re-worded to state equivalence: strict
  replay and snapshot+suffix must agree on every state field and the chained
  digest. Full-history verification remains available via `inspect_cli
  replay` whenever the physical prefix exists, and stays the default for the
  independent checker.
- **D-RF0504** — v3 applies only to new run generations
  (`protocol_version: 3` in RunSpec); v2 replay/verify code is retained
  read-only for historical evidence. No migration tool rewrites v2 authority.
- **D-RF0505** — truncation stays out of scope: RF-05 makes truncation
  *possible* (snapshots no longer pin history), but physical deletion beyond
  today's dry-run GC remains a later, separately-gated phase.

## Loops

### Loop 1 — Reference model (RED first, no production code)
- Extend `fs_diloco/log/model.py` / `testing/deterministic_reference.py` with
  the v3 consumption structures and chained digest.
- **RED:** reference property tests — (a) equivalence: for randomized traces
  within staleness bounds, v3 windowed decision == v2 full-set decision on
  every candidate (accept/reject identical); (b) retirement determinism: the
  rolling accumulator is order-canonical and replay-recomputable; (c) chained
  digest changes for any single-object mutation in the prefix (tamper test).
- **Mutants:** add v3 mutants to the model checker — drop a watermark update;
  retire an ID early; skip the accumulator on one retirement; reuse
  digest_{i-1} for digest_i. Every mutant must be caught by replay
  verification. A mutant that survives fails the loop.

### Loop 2 — Protocol v3 schemas + log implementation
- **RED:** schema roundtrip/golden tests for frontier v3 and snapshot v3;
  production-log tests asserting a v3 generation commits/replays with the new
  structures and that a v2 generation is untouched by the new code paths.
- **GREEN:** implement in `protocol/schemas.py`, `production.py`, `replay.py`
  (v3 branch), `snapshot.py`.
- **HARDEN:** crash matrix re-run for v3 transitions; CAS-conflict and
  response-loss resolution unchanged; `_verify_control_transition` v3 rules;
  cross-generation contamination tests (v3 object in v2 namespace fails
  closed and vice versa).

### Loop 3 — Snapshot v3 + audit rewiring
- **RED:** lifecycle audit test asserting snapshot+suffix state-equivalence
  passes while the old full-`ReplayResult` equality is *not* required for
  v3 (and still required for v2); snapshot size test: v3 snapshot bytes
  independent of transition index (fails by construction for v2).
- **GREEN:** rewire `committer.py` audits per D-RF0503, keyed on protocol
  version.
- **HARDEN:** corrupted/missing v3 snapshot falls back to strict replay with
  the RF-02 telemetry event; two-restore-base retention logic verified on v3.

### Loop 4 — Long-horizon bounded-growth proof (memory backend, login-safe)
- **RED:** the regression the suite lacks today: 5k-transition synthetic run
  asserting per-transition frontier bytes, snapshot bytes, replay manifest
  work (counter-based), and lifecycle time are O(1) — run it on v2 first to
  record the failing growth curve as the "before" artifact, then require
  PASS on v3.

### Loop 5 — Miyabi qualification
1-node and 2-node v3 generations (fresh runs; no warm start from v2 in this
phase), then one 8-node D8 attempt with the standard gates plus: lifecycle
cycle time flat across the run, takeover recovery within the existing
envelope, checker strict replay green. Compare stage decomposition against
the RF-03 D8 numbers.

## CHECK

| ID | Acceptance | Evidence |
|---|---|---|
| RF05-A01 | Reference equivalence: windowed decisions ≡ full-set decisions on randomized traces | pytest property report |
| RF05-A02 | All new consumption/digest mutants caught | model-checker report |
| RF05-A03 | v3/v2 isolation: no cross-generation object acceptance | pytest |
| RF05-A04 | Chained digest tamper-evidence and suffix-resume tests green | pytest |
| RF05-A05 | Replay manifest work O(1)/transition by counters | long-horizon report |
| RF05-A06 | v3 snapshot size independent of history length | pytest + artifact |
| RF05-A07 | State-equivalence audit green; corrupted-snapshot fallback + telemetry | pytest |
| RF05-A08 | 5k-transition bounded-growth regression in CI (before/after artifacts) | pytest + artifacts |
| RF05-A09 | D8 v3 run: all correctness gates green; flat lifecycle times; recovery within envelope | elapsed contract + checker PASS |

Checker: independent strict replay of the D8 v3 run from a clean clone;
invariant docs (I-008 wording) and research contract updated and consistent;
explicit sign-off that v2 evidence remains valid and readable.

## PERSIST

`RF05_PHASE_REPORT.md` with the growth-curve before/after figures; update
`docs/architecture/` and the invariants table for v3; STATE.yaml; follow-ups:
physical truncation phase (out of scope here), multi-in-flight FWO revisit.
