---
plan_id: "P12"
title: "Formal Experiments, Artifact, Related Work, and Paper Evidence"
status: "planned"
date: "2026-07-12"
planning_basis_commit: "resolve_from_P11_verified_report"
target_branch: "codex/duraloco-p12-distributed-evaluation"
depends_on: ["P11"]
execution_mode: "preregistered experiments + independent analysis/checker"
automatic_progression: false
next_phase: "project_complete_or_optional_P09_by_explicit_user_choice"
agent_decision_gates:
  - "autonomous within preregistered resources; claims must shrink to evidence; negative/neutral results complete the phase"
human_approval_gates:
  - "resources beyond the Miyabi envelope, public cloud, public release, or new long-horizon large-scale training"
---

# P12 — Formal Evaluation and Paper Evidence

## 1. Mission

Freeze the experiment registry and complete the correctness, resource
efficiency, failure-free performance, fault-goodput, lifecycle, controller,
redundancy, and model-quality evaluation of the DuraLoCo distributed-syncer
route; bind every figure, claim, related-work differentiation, and artifact
reproduction to immutable run manifests. Valid outcomes: **Supported**,
**Bounded/conditional**, or **Rejected/negative** — success cannot be
manufactured by deleting unfavorable data.

## 2. Comparison configurations

| Code | Configuration |
|---|---|
| D8 | 8 learner nodes, factor 1, no dedicated syncer |
| D8-R2-W | D8, factor 2, warm standby |
| D8-R2-H | D8, factor 2, hedged |
| D8-SACC-SYS | D8/D8-R2 with guarded system-only enforced controller |
| D8-SACC-ALG | only if the P10 algorithm tier qualified; new generation |
| checkpoint baseline | conventional checkpoint+restart where available |

Every current comparison uses the same eight-node allocation. Historical C9
results may be cited as archival context but cannot enter a matched statistical
cell or trigger a new ninth-node run.

## 3. Candidate research claims

Storage-resident outer-optimizer authority replaces persistent syncer state;
D8 removes the dedicated-syncer allocation with correctness/quality
preserved; R2/hedging improves fault goodput at a quantifiable cost;
ownership migration requires zero private optimizer-state transfer; the
lifecycle keeps storage bounded with safe recovery; SACC improves goodput/
cost under identified conditions or its no-benefit boundary is mapped.

## 4. Preconditions

P11-A01–A26 pass; final implementation/config/semantic digests frozen;
`RESEARCH_RELATED_WORK_AND_DIFFERENTIATION.md` updated to execution date;
analysis environment pinned; registry, exclusion rules, and failure
classification pre-reviewed by the checker.

## 5. Design decisions to freeze first

D-1201 endpoints + success criteria; D-1202 matched-token / matched-compute /
matched-allocation comparison bases; D-1203 seeds/repetitions/confidence
intervals; D-1204 fault distributions/tapes/controls; D-1205 exact eight-node
allocation accounting; D-1206 quality non-inferiority or bounded-difference criteria;
D-1207 exclusion/inconclusive rules; D-1208 science-vs-engineering lineage
separation; D-1209 artifact licenses/secrets/redaction; D-1210 claim wording
and related-work priority check.

## 6. Execution loops

### Loop 1 — Registry and preregistration
Freeze cells, configs, seeds, faults, metrics, exclusions, and the analysis
commit before formal runs. RED: the registry fails if any cell lacks
topology/resource/implementation digests or success criteria could be edited
post hoc. Checker signs the preregistration. Analysis must run schema
validation with zero results present.

### Loop 2 — Correctness and resilience campaign
Systematic validation of duplicate execution, fencing, reconfiguration,
replay, GC, and capsules on D8 / D8-R2-W/H with fixed fault tapes and
no-fault controls. Metrics: double inclusion, mixed state, live deletion,
divergence blockers, committed progress, RTO/RPO, lost/repeated tokens,
availability, fault goodput. **Added cell (review H2 regression): injected
crashes at every commit stage must never yield a committed stop fact whose
reason misrepresents the outcome; the stop-fact audit is part of the safety
endpoint.** Any safety violation is explained and re-verified after fix, or
the core claim is Rejected.

### Loop 3 — Failure-free performance and resource efficiency
D8 factor-one vs R2 vs SACC: wall time, useful tokens/s, outer transitions/s,
GPU step time, CPU/RSS, Lustre bytes + metadata ops (per-stage counters, not
one aggregate), publish→adopt latency, duplicate waste, allocation
efficiency; exact eight-node accounting explicit. Raw manifests reconstruct every
figure; break-even conditions stated.

### Loop 4 — Redundancy, fault goodput, state-transfer claim
Replay/simulated sweeps over failure/straggler rates plus selected real D8
fault tapes. Verify owner changes read shared objects with **zero private
optimizer-state bytes migrated** (trace evidence). Tail latency, hedge rate,
wasted CPU/I/O, recovery time, availability. Report applicability regions or
a negative result; do not generalize.

### Loop 5 — Lifecycle and checkpoint fusion
No-GC vs dry-run vs approved-apply (synthetic), snapshot cadence, warm/exact
recovery comparisons: bytes, object counts, ops, peak/steady storage,
snapshot/replay time, capsule overhead, restore success. Evidence for
bounded growth and safe restore, or the claim shrinks.

### Loop 6 — SACC ablation
Matched D8/D8-R2 fixed/shadow/system-enforced cells with action traces,
counterfactual replay, quality smoke. Algorithm-enforced cells only if P10
qualified; otherwise the `not_qualified` evidence enters the claim matrix
explicitly (not as a missing run).

### Loop 7 — Model quality
Matched-token and matched-compute, preregistered seeds: central CRS, D8,
D8-R2, SACC; training curves + downstream metrics; seed variance, failed-run
handling, warm/exact restart, actual-token differences addressed. If the
evidence budget is not met, state plainly that quality equivalence is not
claimed.

### Loop 8 — Artifact, related work, paper evidence
Pinned environment; packaged registry/manifests/raw data/analysis/checksums;
claim–evidence matrix; related-work comparison updated to execution date
without overstating the novelty of individual primitives (the wording
distinguishes *dedicated-syncer-free* from *coordinator-free*). Independent
checker reproduces core results from a clean directory, including at least
one stale-cache/head-jump counterexample, one duplicate counterexample, and
one retry-lock counterexample. Internal review walks every claim.

## 7. Invariants

Results cannot modify preregistered criteria. All failures/cancellations/
exclusions/retries retain lineage. Every current cell uses exactly eight nodes.
Correctness and quality claims separated. Raw manifests are the analysis
input; no database dependency. Figures rebuild from the final clean analysis
commit. P09 non-selection does not affect completion.

## 8. Acceptance

- [ ] P12-A01: registry/preregistration checksum + checker PASS.
- [ ] P12-A02: required cells complete or preregistered-inconclusive.
- [ ] P12-A03: correctness campaign clean (incl. stop-fact truthfulness
      audit) or violations explained/fixed/re-verified.
- [ ] P12-A04: divergent-duplicate expected-BLOCKED formal evidence.
- [ ] P12-A05–A07: failure-free overhead, node/GPU efficiency, exact
      eight-node accounting, and CPU/GPU/Lustre/interference attribution complete.
- [ ] P12-A08/A09: redundancy break-even + negative regions; fault goodput /
      RTO / RPO / lost-repeated work complete.
- [ ] P12-A10: zero private optimizer-state transfer on ownership migration,
      with traces.
- [ ] P12-A11: lifecycle bytes/ops/object-count/steady-growth/recovery
      complete.
- [ ] P12-A12: SACC ablations complete; algorithm tier qualified or
      `not_qualified` in the claim matrix.
- [ ] P12-A13: multi-seed matched-token/matched-compute quality complete or
      the claim explicitly withheld.
- [ ] P12-A14/A15: full lineage retention; science cells separated from
      engineering runs.
- [ ] P12-A16/A17: every figure rebuilds from raw manifests; no dangling
      primary claim.
- [ ] P12-A18: related work current and free of unfounded first-claims.
- [ ] P12-A19/A20: clean reproduction without SQLite/DB dumps; replayed
      counterexamples included.
- [ ] P12-A21: final D8/D8-R2 milestone runs in the artifact.
- [ ] P12-A22: claim wording separates dedicated-syncer-free from
      coordinator-free.
- [ ] P12-A23/A24: independent checker + internal review complete; final
      verdict Supported/Bounded/Rejected with full evidence.
- [ ] P12-A25/A26: `STATE.yaml` marks the required route completed; P09
      remains opt-in only.

## 9. Completion semantics

P12 ends the required route. A negative or bounded conclusion is not an
engineering failure provided the preregistered experiments, evidence,
artifact, and honest claims are complete. No automatic merge to main, no
automatic public release.

## 10. Startup instruction (copyable)

```text
Execute P12 formal evaluation. Freeze registry/preregistration first, then run
D8/D8-R2/SACC correctness (incl. stop-fact truthfulness), resource,
fault, lifecycle, and quality cells. Retain every fail/cancel/exclusion/retry;
figures rebuild from raw manifests only. Update related-work differentiation
and the claim–evidence matrix; independent clean reproduction. Supported/
Bounded/Rejected are all valid endings. P09 never starts automatically.
```
