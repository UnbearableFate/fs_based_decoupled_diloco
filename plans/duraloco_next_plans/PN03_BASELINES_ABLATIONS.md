---
plan_id: "PN-03"
title: "External Baselines and Ablation Matrix"
status: "planned"
depends_on: ["P12", "PN-01 claims_frozen.md"]
parallel_with: ["PN-04"]
effort: "3–5 weeks; compute-bound; shares D8 allocations with PN-04"
---

# PN-03 — External Baselines and Ablations

## 1. Mission

Answer the two questions every MLSys reviewer will ask before reading page 3:

1. **"What does this cost?"** — durability/auditability overhead versus a
   conventional stack at matched hardware, model, and token budget.
2. **"Which parts matter?"** — component-wise ablation so the paper can
   attribute overhead and recovery behavior to mechanisms, not to the system
   as a monolith.

P12's internal checkpoint-baseline cell is the seed; this phase makes it a
first-class, matched, preregistered comparison.

## 2. Baseline configurations

| Code | Configuration | Answers |
|---|---|---|
| B1 | `torchrun` DDP (NCCL) + periodic synchronous checkpoint-restart, same 8 GPUs, same model/data/token budget | "why not just do normal training" — throughput ceiling and fault cost of the conventional stack |
| B2 | DiLoCo-style local SGD with *plain checkpointing* (reuse this repo's learners; replace the transactional committer with naive `latest.json`-style aggregation + periodic checkpoints, no log/CAS/fencing) | isolates the *cost of durability machinery itself* at identical algorithm and interval structure |
| B3 (optional) | B2 + etcd/ZooKeeper-style external coordinator for ownership (single-node etcd on one learner host) | "why a filesystem instead of a coordination service" — cut first if time-boxed |

Fault protocol for all baselines: identical injected fault tapes (kill active
aggregator/committer at renewal-phase-randomized times; kill one learner
host) replayed from P12's fault distributions.

## 3. Metrics (all cells)

- goodput: committed useful tokens / wallclock, fault-free and under faults;
- overhead %: (cell wallclock − B1 fault-free wallclock) at matched tokens;
- recovery: distribution of failure→next-useful-progress, plus *lost work*
  (tokens discarded), which is where checkpoint-restart pays;
- storage: bytes written/read per committed step; peak namespace size;
- quality: final eval loss/perplexity non-inferiority per P12's D-1206.

## 4. DuraLoCo ablation matrix

One knob per cell, D8 shape, ≥3 seeds where variance matters:

| Cell | Knob | Expected story |
|---|---|---|
| A1 | replication factor 1 vs 2 (warm / active_active / hedged) | reliability-latency tradeoff (post-D-06 fix semantics) |
| A2 | lifecycle cadence 0 / 2 / 5 | audit cost vs bounded-storage benefit |
| A3 | snapshot recovery on/off (force strict replay on takeover) | value of snapshot+suffix; recovery-time delta |
| A4 | lease TTL 45 s vs evidence-qualified lower value (per review D-09) | recovery floor decomposition: policy vs work |
| A5 | payload zero-copy promotion on/off (review D-05 fix) | I/O amplification attribution |
| A6 | validation depth: full finite-scan vs header-only (correctness mode vs perf mode) | cost of the paranoia, honestly reported |

## 5. Loops

1. **Harness parity loop.** Build B1/B2 launchers under `scripts/miyabi/` with
   the same elapsed-contract reporting as D8 runs; qualify 1→2→8 nodes.
   RED: a baseline that cannot replay the fault tape identically is not a
   baseline — fix the harness, not the tape.
2. **Preregistration loop.** Extend the P12 registry with baseline + ablation
   cells, seeds, exclusion rules; checker signs before any formal run.
3. **Campaign loop.** Run cells; one 8-node attempt per cell shape per the
   project's failure rule (root-cause before resubmission).
4. **Analysis loop.** Independent analysis from immutable artifacts; produce
   the overhead curve (overhead % vs local-interval length) — this single
   figure is the paper's economic argument: durability overhead amortizes as
   intervals grow.

## 6. Acceptance gate

- [ ] B1 and B2 complete with matched token budgets and identical fault tapes;
      B3 done or explicitly descoped in the registry.
- [ ] All six ablation cells analyzed; every claim in `claims_frozen.md` that
      cites cost/recovery now points at a cell.
- [ ] The overhead-vs-interval curve exists with confidence intervals.
- [ ] Negative results (if any) written up unfiltered — e.g., if B2 recovery
      is competitive at some checkpoint interval, the paper reports the
      crossover point instead of hiding it.

## 7. Risks

- **B1 NCCL stack availability on Miyabi** — validate in the 1-node loop
  first; if the platform forbids it, substitute a documented single-node DDP
  baseline plus a cost model, and say so in the paper.
- **Time.** B3 and A6 are the designated cuts. Never cut B2 — it is the
  ablation that isolates the thesis.
