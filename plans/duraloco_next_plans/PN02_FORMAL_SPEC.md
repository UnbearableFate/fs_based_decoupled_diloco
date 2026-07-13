---
plan_id: "PN-02"
title: "Formal Specification and Model Checking of the Core Protocol"
status: "planned"
depends_on: ["P12"]
parallel_with: ["PN-01"]
effort: "2–4 weeks, desk work, no cluster compute"
---

# PN-02 — Formal Specification and Model Checking

## 1. Mission

Back the paper's central correctness claims (exactly-once inclusion, single
committed chain, fenced ownership, recovery equivalence) with a small formal
specification and exhaustive model checking of bounded configurations, so the
claims section can say "model-checked" instead of "tested". This converts the
project's strongest existing asset — the invariant discipline I-001…I-012 and
the Python mutant-based model checker in `fs_diloco/testing/` — into a
publication-grade argument.

## 2. Scope decision (freeze first)

Specify the **control plane only**; numerics stay outside the spec:

- state: head, immutable object store (as a set of published identities),
  lease record, fencing epochs, per-lineage sequences, consumption facts;
- actions: publish-proposal (marker-last as two steps), acquire/renew/expire
  lease, epoch-bump commit, prepare transition, head CAS (success / lost
  response / conflict), crash of any role, strict replay, snapshot+suffix
  replay;
- environment: at-least-once storage ops, lost responses, delayed/reordered
  listings, clock skew bounded by `max_clock_skew` (and one run with the
  bound violated, expecting the safety net to hold via CAS versioning).

Target invariants (mapped 1:1 to the repo's IDs):

| Spec invariant | Repo ID |
|---|---|
| Single parent-linked committed chain; CAS is the only linearization point | I-002, I-006 |
| A proposal enters at most one committed selected set | I-003 |
| Fencing epochs monotonic; stale-epoch owner cannot advance head | I-007 |
| Empty-cache replay ≡ memoized replay ≡ snapshot+suffix replay | I-008 |
| One identity ⇒ one canonical body | I-011 (modeled as assumption + conflict detection) |

## 3. Tooling

TLA+ / TLC as primary (best reviewer recognition). Keep the spec ≤ ~600 lines.
Configurations to exhaustively check: 2 learners × 2 committer candidates ×
1 fragment × ≤6 transitions; then 3×2×2×≤5. Use symmetry sets for learner IDs.

## 4. Loops

### Loop 1 — Spec skeleton and happy path
Write the state machine; TLC verifies the happy path reaches N committed
transitions with all invariants. Deliverable: `spec/duraloco.tla` + config.

### Loop 2 — Fault actions and adversarial schedules
Add crashes, lost CAS responses, lease expiry mid-prepare, duplicate
publication retries, stale-owner CAS attempts. TLC must (a) hold all safety
invariants, (b) reproduce the *known-required* behaviors as reachable states:
takeover after expiry, `already_committed` resolution after response loss,
CAS-conflict discard-and-replay.

### Loop 3 — Mutant validation of the spec itself
Port ≥6 of the deliberate safety mutants from
`fs_diloco/testing/model_checker.py` into spec mutations (e.g., skip the
parent-version check in CAS; allow lease renewal after expiry; drop the
consumed-set check). TLC must produce a counterexample trace for every
mutant — this is the evidence that the spec is *checking something*, and it
mirrors the repo's own mutant methodology (good paper narrative symmetry).

### Loop 4 — Code correspondence note
A short document mapping every spec action to the implementing function
(e.g., CAS action ↔ `PosixStorageBackend.conditional_replace` +
`TransactionalLog.commit_prepared`; expiry rule ↔ `LeaseManager.acquire`).
Reviewers reward this; it also catches spec/code drift.

## 5. Acceptance gate

- [ ] TLC exhaustive pass on both configurations, all five invariants, zero
      errors; state counts and runtimes recorded.
- [ ] All ported mutants produce counterexamples.
- [ ] Correspondence note reviewed against the current commit.
- [ ] Spec + configs + traces land in the repo (`spec/`) and in the PN-06
      artifact.

## 6. Risks

- **State explosion:** keep payloads/numerics out; model the object store as
  identity sets, not bytes. If 3-learner config blows up, ship 2-learner
  exhaustive + 3-learner bounded (report the bound honestly).
- **Spec/code divergence:** the correspondence note is the control; re-check
  after any P08R-era code change that touches commit/lease/replay paths.
