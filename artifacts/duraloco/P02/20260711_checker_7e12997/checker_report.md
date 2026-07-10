# P02 Independent Checker Report

Verdict: PASS
required_gate_followups: none

## Review identity

- Checker: independent Codex checker agent `/root/p00_checker` (read-only maker tree)
- Reviewed implementation commit: `7e12997ca0a9fe4e48bb96cfe6391e0e8d1bf773`
- Maker runtime: `2357761.opbs` on `mg0011`, exit 0, 213 passed and 1 explicitly skipped
- Explicit model-check run: 10,000 seeded traces, 10,000 unique state digests
- Independent runtime: `2357765.opbs` on `mg0013`, exit 0
- Maker evidence: `artifacts/duraloco/P02/20260711_clean_p02_7e12997`
- Checker evidence: `artifacts/duraloco/P02/20260711_checker_7e12997`

## Gate results

- P02-A01: the executable reference/storage/model-check modules remain free of
  Torch, Hugging Face, NumPy, filesystem, and network dependencies. The Torch
  dependency is confined to the external legacy numeric oracle test.
- P02-A02: publish, decision, commit, fold, and recovery transitions check the
  invariant catalog. Exact causal-base/frontier pairing, monotonic lineage,
  deterministic numeric transitions, fragment/outer-state pairing, and the
  single parent-linked head are independently folded and verified.
- P02-A03: all enumerated commit and decision crash points recover the old or
  new legal prefix. Publication crashes and response loss after head CAS are
  also covered, and the explicit 10,000-trace suite passed.
- P02-A04: proposal IDs cannot be logically included twice; same-base overlap
  and committed sequence rollback are rejected.
- P02-A05: deliberate double-apply, wrong-parent, state-pairing,
  numeric-transition, and sequence-rollback mutants each trigger their target
  invariant class.
- P02-A06: SGD, momentum, Nesterov, AdamW, and the one-fragment path match the
  legacy Torch oracle under the frozen numeric tolerance.
- P02-A07: trace/state digests are stable across replay and process execution;
  failing traces reproduce by seed and minimize to their causal event.
- P02-A08: the checker independently exercised an adversarial proposal-ID order
  and a benign decision-versus-prepared-commit race. Both linearized according
  to the frozen oldest-first/single-head semantics.

## Independent counterexamples and closed findings

The exact counterexample from checker PBS `2357714.opbs` was rerun with a newer
same-lineage proposal whose ID sorts before the older proposal. At the reviewed
commit, both `select_quorum` and `replay_trace` commit the older proposal. The
newer overlapping proposal remains unconsumed until an explicit supersession
decision.

The checker also revalidated immutable byte snapshots, exact fragment/base
pairing, decision-log prefix recovery, stale prepared-transition rejection,
committed sequence rollback rejection, every commit/decision crash point, and
all five safety mutants. No required P02 gate remains open.

## Non-blocking scope note

Cross-session learner interval adoption/supersession policy remains assigned to
P06. P02 enforces non-overlap and monotonicity within the frozen
learner/session/fragment lineage and does not claim P06 runtime adoption
semantics.
