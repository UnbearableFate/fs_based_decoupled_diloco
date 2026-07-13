---
plan_id: "RF-04"
title: "Hedging Semantics — first-valid commit vs evidence mode"
status: "planned"
basis_commit: "8b5121344294d202428187dfeafb0697ad38e02d"
findings: ["D-06"]
depends_on: ["RF-03 Loop 1 harness"]
runtime_validation: "2-node fault matrix, then ride the next scheduled D8-R2"
user_decision_gate: "semantics choice (D-RF0401) requires explicit user sign-off"
---

# RF-04 — Hedging Semantics

## Mission

Resolve the inversion found in D-06: once the hedge delay fires (or in
active_active), the committer requires *both* attempts, so redundancy adds
latency instead of cutting it, and a silently-dead primary blocks until
timeout. Choose and implement one of two semantics, with the choice made
explicitly and recorded — this is a research-contract decision, not just code.

## ORIENT

Re-read `committer.py:232-323` (`_wait_for_result`),
`duplicate_validation.py`, `hedge_policy.py`, the I-011 invariant, and the
P08R measurement (~5 s extra per hedged transition; hedged wait growth
79→126 s aggregate). Confirm with the user which option below is adopted.

## Design decisions to freeze (pick ONE — user gate)

- **Option A — D-RF0401a "first-valid commits, async divergence audit".**
  The committer commits on the first fully validated result. When the second
  attempt arrives (same immutable namespace), a mandatory pre-next-transition
  audit compares prepared-result identities; divergence raises the same
  fail-closed blocker as today and stops the run *before any further commit*.
  I-011 wording updates from "divergent duplicates block the commit" to
  "divergent duplicates halt the trajectory before the next commit"; the
  losing/late attempt remains retained evidence.
- **Option B — D-RF0401b "evidence mode, honest docs + dead-primary escape".**
  Keep both-attempts-required semantics, but (1) rename/document `hedged` as
  a duplicate-evidence mode, not a latency mode, in the research contract and
  configs; (2) add deadline-based failure evidence: if the primary exceeds a
  frozen multiple of the hedge delay with no attempt marker, the committer
  writes observational failure evidence that removes it from
  `required_attempts` (same mechanism as today's failed-member path), so a
  dead primary no longer blocks to the no-progress timeout.

Shared decision: **D-RF0402** — either way, the redundancy policy schema
gains an explicit `commit_rule: first_valid | all_required` field so the
semantics are frozen in the RunSpec, not implied by code version.

## Loops

### Loop 1 — Decision record
- Write the one-page decision memo (tradeoff table: latency, fault-window
  behavior, I-011 wording, checker impact); obtain user sign-off; freeze
  D-RF0401 choice + D-RF0402. RED for this loop: the plan cannot proceed
  with the gate unsigned.

### Loop 2 — Semantics implementation
- **RED (Option A):** hedged 2-node test with a slow-but-alive primary:
  commit must complete at backup latency (fails today); divergent-result
  test: second attempt with different identity must halt before the next
  transition commits (new assertion point). Lost-second-attempt test: a
  backup that never reports leaves the run progressing with the audit
  recorded as `single_attempt`.
- **RED (Option B):** dead-primary test: no primary marker after the frozen
  deadline → failure evidence written, commit completes with backup only
  (fails today with timeout); docs test: research contract + config
  reference name the mode correctly (check_docs stale-claim style assertion).
- **GREEN:** implement the chosen option + D-RF0402 schema field (RunSpec
  digest change → this rides a config/generation boundary, coordinate with
  RF-05 timing if close).
- **HARDEN:** full redundancy fault matrix re-run (warm/active/hedged ×
  primary-fail/backup-fail/both-slow/divergent); replay verification: commits
  carrying `commit_rule` validate against the frozen policy during strict
  replay.

### Loop 3 — Measurement
2-node targeted benchmark: hedged transition latency vs factor-one under (a)
healthy primary, (b) slow primary, (c) dead primary. Then ride the next
scheduled D8-R2 run (do not buy a dedicated allocation): frozen success
criterion — hedged steady-state transitions within a stated envelope of
factor-one (Option A) or dead-primary recovery bounded by the deadline rule
(Option B).

## CHECK

| ID | Acceptance | Evidence |
|---|---|---|
| RF04-A01 | Decision memo signed; commit_rule frozen in RunSpec schema | memo + schema test |
| RF04-A02 | Chosen-option RED matrix green (slow/dead/divergent primary) | pytest |
| RF04-A03 | Strict replay validates commit_rule; divergence still fail-closed at the documented point | pytest |
| RF04-A04 | 2-node benchmark + next-D8-R2 evidence meet the frozen criterion | benchmark + elapsed contract |

Checker: independent re-run of the redundancy fault matrix; verify I-011
documentation, invariants table, and failure-model doc all state the chosen
semantics consistently.

## PERSIST

`RF04_PHASE_REPORT.md` including the decision memo verbatim; STATE.yaml;
follow-up: revisit hedging defaults after RF-05 changes replay costs.
