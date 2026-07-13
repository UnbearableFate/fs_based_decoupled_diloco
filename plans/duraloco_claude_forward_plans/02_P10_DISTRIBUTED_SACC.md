---
plan_id: "P10"
title: "Distributed SACC: Storage-Aware Coordination, Redundancy, Algorithm–System Co-Design"
status: "planned"
date: "2026-07-12"
planning_basis_commit: "resolve_from_P08_verified_report"
target_branch: "codex/duraloco-p10-distributed-sacc"
depends_on: ["P08"]
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
next_phase: "P11"
agent_decision_gates:
  - "only actions that pass shadow replay, guardrails, ablation, and Checker enter enforced mode"
human_approval_gates: []
---

# P10 — Distributed SACC

## 1. Mission

A distributed Storage-Aware Coordination Controller that first regulates
**system-only knobs** which cannot change the optimizer trajectory (prefetch
depth, materialization cadence, hedge start within the frozen mode, LFE
CPU/I/O budgets) from structured stage metrics; deterministic shadow mode
first, then bounded enforcement.

**Two tiers, strictly separated:**

- *System-only tier*: observable → suggestible → (after qualification)
  enforceable inside the current generation. Binds each action to
  head/membership revision + policy digest before activation.
- *Algorithm-affecting tier* (quorum/grace, fair selection, local interval
  length, replication factor, bundle shape — anything altering the proposal
  set, numeric order, ownership, or committed trajectory): requires a
  committed policy-decision schema, a **new run generation/identity**, quality
  guardrails, and independent checker qualification. Insufficient evidence
  ends the tier as `not_qualified` — a legitimate, complete outcome. Never
  force-enforce to satisfy a gate.

The minimum successful P10: deterministic shadow + guarded system-only
enforcement + complete `not_qualified` evidence for the algorithm tier.

## 2. Preconditions

- [ ] Pre-P10 P08R performance gate PASS: matched C9, two sequential D8
      factor-one runs, and D8-R2 complete 50×10 experiments each finish within
      440 seconds without weakening replay/lifecycle safety.
- [ ] P08 verified commit with P07 lifecycle regressions checker-PASS.
- [ ] Lifecycle + performance schemas frozen; D8/D8-R2 raw stage metrics
      complete, **including the storage-op counters landed in H0/P08** (these
      are a required observation source: the controller must distinguish
      metadata-scan-bound from payload-read-bound states, which is only
      possible with per-stage op/byte counters, not aggregate latency).
- [ ] Bundle path (if enabled in P08) passed serial equivalence.
- [ ] Controller-off behavior identical to the P08 fixed baseline.

## 3. Design decisions to freeze first

- D-1001 observation windows + causal cutoff; D-1002 per-action tier
  classification (uncertain ⇒ algorithm-affecting); D-1003 action binding to
  head/epoch and invalidation, algorithm-tier committed identity rules;
  D-1004 adaptive grace/quorum bounds + fairness objective (shadow only until
  qualified); D-1005 hedge/replication dwell/cooldown; D-1006 resource
  actions vs PBS allocation; D-1007 invalidation on head/epoch/strict
  fallback; D-1008 promotion evidence (shadow → system-enforced) and separate
  algorithm-tier qualification; D-1009 multi-objective cost/goodput/quality +
  negative-result policy; D-1010 controller version/implementation digest.

## 4. Expected repository changes

```text
fs_diloco/sacc/  observations.py, actions.py, policy.py, replay.py,
                 guardrails.py, fairness.py, cost_model.py, controller.py,
                 committed_decisions.py
fs_diloco/distributed_syncer/controller_hooks.py
fs_diloco/learner_protocol/controller_hooks.py
experiments/sacc/  fixed.yaml, shadow.yaml, enforced.yaml, ablations.yaml
tests/sacc/  test_replay_determinism.py, test_shadow_no_effect.py,
             test_guardrails.py, test_epoch_invalidation.py,
             test_fairness_starvation.py, test_action_response_loss.py
```

## 5. Explicitly not doing

No protocol self-modification or per-fragment heads. Controller can never
disable strict replay, validation, fencing, marker-last, or GC roots. No
root-cause guessing from a single aggregate latency. No wall-clock-only
decisions that cannot be replayed after restart. No algorithm-tier scope
expansion without quality evidence. Shadow observations never become
authority.

## 6. Execution loops

### Loop 1 — Observations and deterministic replay
Canonical observation windows + quality flags from persisted structured
metrics; policy kernel + action schema shared by simulator/runtime/offline
replay CLI. RED: missing/late/out-of-order events, clock skew, restart,
directory-order permutation, epoch/head cutover, corrupt metrics — bad
observations may only produce safe fallback. **Stop when:** identical
committed evidence yields identical actions and metrics are demonstrably not
authority.

### Loop 2 — Adaptive grace/quorum/fairness (shadow only)
Bounded grace, eligible quorum, fairness debt/token weighting as shadow
suggestions + offline counterfactuals over heterogeneous-learner, straggler,
rejoin, and token-imbalance tapes. Nothing touches the live FWO stream.
Starvation bounds reported. Enforcement exists only behind the
new-generation algorithm gate. **Stop when:** shadow provably leaves P06
interval/consumption semantics untouched and is replayable.

### Loop 3 — Storage backpressure, bundling, materialization
Stage-specific cost model distinguishing validation-bound, read-bound,
CAS-conflict, manifest-growth, and GPU-interference root causes (controller
fails RED if it emits one action for all causes). Bounded system-only actions
+ rollback; bundle knobs only if the P08 path exists and the mode is frozen in
the run spec. HARDEN: response loss, partial bundles, snapshot/GC overlap,
strict fallback, storage latency spikes. **Stop when:** actions never weaken
correctness and the controller discriminates bottlenecks.

### Loop 4 — Redundancy, hedge, learner-host resources
Choose hedge start timing within the frozen replication/mode ceiling; tune
thread/prefetch budgets with cooldowns. Replication factor / owner-set changes
are algorithm/topology tier via committed reconfiguration only — the
controller cannot alter ownership authority. RED tapes: no-failure,
straggler, node failure, CPU pressure, Lustre congestion; HARDEN: false
suspicion, oscillation, churn, same-FWO divergence, budget saturation.
**Stop when:** controller selects only validated modes and cannot bypass
duplicate validation.

### Loop 5 — Shadow qualification
D1/D2/D8/D8-R2 shadow runs; any FWO/transition/learner digest change with
shadow on is a hard failure. Record suggested actions + counterfactual costs;
restart/response-loss/head-epoch-change/controller-crash/metrics-gap
hardening. Independent replay, stability/oscillation analysis, promotion
decision per action. **Stop when:** only the evidence-qualified subset is
marked enforceable.

### Loop 6 — Guarded enforcement + ablation
Pre-registered action subset, bounds, rollback, success criteria. Small D2,
then D8/D8-R2 50×10 with at least fixed/shadow/system-enforced arms; decision
binding survives restart. Algorithm-enforced arm only if qualified; otherwise
archive `not_qualified` rationale, counterexamples, checker conclusion.
**Stop when:** enforcement violates no invariants; insufficient benefit is an
acceptable, fully-evidenced negative conclusion.

## 7. Invariants

Shadow has zero behavioral effect. Decisions replayable. Authority remains
the committed history/head. Algorithm-affecting actions never act in the old
generation. Head/epoch changes invalidate or deterministically restore
actions. Hysteresis/cooldowns bound oscillation. Factor-1/fixed modes remain
as baseline and fallback. Lifecycle roots cover committed decisions.

## 8. Acceptance

- [ ] P10-A01: P08 verified + P07 regressions + independent checker PASS.
- [ ] P10-A02: observation/action schemas strictly validated.
- [ ] P10-A03: simulator/runtime/replay action digests identical.
- [ ] P10-A04: controller replay invariant to local-state deletion.
- [ ] P10-A05: shadow mode zero-impact on FWO/transition/model digests.
- [ ] P10-A06/A07: adaptive grace/quorum and fairness shadowed with bounds +
      starvation reporting; enforced only behind the new-generation gate,
      else `not_qualified`.
- [ ] P10-A08: controller distinguishes validation/read/publication/CAS/
      replay/export/interference bottlenecks (storage-op counter evidence).
- [ ] P10-A09: in-flight/bundle/prefetch/materialization actions guardrailed.
- [ ] P10-A10: hedge/replication/resource actions cannot bypass ownership or
      duplicate validation.
- [ ] P10-A11: no algorithm-affecting action effective in the old generation;
      qualified ones enter new-generation committed lineage.
- [ ] P10-A12: decision response-loss/restart recoverable from ancestry.
- [ ] P10-A13: owner/epoch/head jumps invalidate or deterministically restore
      actions.
- [ ] P10-A14: fixed/shadow D1/D2 suites pass.
- [ ] P10-A15: promotion is per-action, per-tier, evidence-gated.
- [ ] P10-A16/A17: D8 and D8-R2 fixed/shadow/system-enforced arms complete;
      algorithm-enforced only if qualified.
- [ ] P10-A18: zero double inclusion / mixed state / live deletion.
- [ ] P10-A19: GPU interference, Lustre, latency, duplicate cost, fault
      goodput complete.
- [ ] P10-A20: quality smoke shows no unexplained regression.
- [ ] P10-A21: negative/neutral results retained; claims shrink to evidence.
- [ ] P10-A22: no SQLite / per-fragment heads / second authority.
- [ ] P10-A23: report/checksums/clean commit/checker consistent.
- [ ] P10-A24: `STATE.yaml.next_action = P11`.

## 9. Startup instruction (copyable)

```text
Execute P10 on the P08 verified commit. Build canonical observations (including
storage-op counters), deterministic replay, and fixed/shadow modes; enforce
only trajectory-neutral prefetch/materialization/hedge-start/LFE-resource
actions after per-action qualification. Grace/quorum/fairness/interval/
replication/bundle semantics are algorithm-affecting: new generation, committed
identity, quality gates — or an honest not_qualified. Shadow must have zero
behavioral impact. Complete D8/D8-R2 fixed-shadow-system-enforced ablations,
then proceed to P11.
```
