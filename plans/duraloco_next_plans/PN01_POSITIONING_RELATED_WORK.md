---
plan_id: "PN-01"
title: "Positioning, Related Work, and Claim Definition"
status: "planned"
depends_on: ["P12"]
parallel_with: ["PN-02"]
effort: "1.5–3 weeks, desk work, no compute"
---

# PN-01 — Positioning, Related Work, and Claim Definition

## 1. Mission

Decide exactly what the paper claims, prove those claims are novel against the
literature as of submission date, and produce the related-work section plus a
novelty-delta table that survives an adversarial reviewer.

## 2. The claim set to defend (starting hypothesis)

The paper is a **systems** paper. Candidate core claims, to be confirmed or
cut during this phase:

- **C1 (framing):** an outer-optimizer step, a fragment merge, and a recovery
  point can be one durable transaction on a shared filesystem — "training as a
  transactional log" — with no coordination service, RPC, or collective
  runtime.
- **C2 (protocol):** exactly-once logical inclusion of learner contributions
  is derivable from at-least-once storage semantics via canonical identity,
  marker-last publication, request IDs, fencing epochs, and a single head CAS.
- **C3 (recovery):** recovery is a fold over the committed prefix; snapshot+
  suffix recovery is audited digest-equivalent to strict replay; worst-case
  failure-to-next-commit is measured and decomposed (lease policy vs replay).
- **C4 (practicality):** the whole protocol runs on an unmodified Lustre
  filesystem, with fail-closed capability probing (flock scope, dir-fsync,
  CAS races) instead of platform assumptions.

Explicit **non-claims** (state them in the paper): no new optimization
algorithm; no Byzantine tolerance; no cross-backend bitwise determinism;
no wide-area/geo-distributed deployment evidence.

## 3. Literature to survey systematically

| Cluster | Must-cover examples | Question to answer |
|---|---|---|
| Local-SGD / decoupled training | DiLoCo, DiPaCo, OpenDiLoCo, INTELLECT-1/PCCL, async local-SGD, FedAsync/FedBuff | Do any make durability/exactly-once claims? How do they handle faults? |
| Elastic / fault-tolerant training systems | Oobleck, Varuna, Bamboo, Gemini, TorchElastic, HPC MPI-fault-tolerance work | Recovery model, recovery time, coordination dependencies |
| Checkpointing systems | CheckFreq, just-in-time / asynchronous checkpointing, DeepFreeze | The baseline cost model reviewers will compare against |
| Transactional / lineage storage | git-like object stores, event sourcing, FoundationDB-style CAS logs, Tango/Corfu shared logs | Is "single CAS head + content-addressed log" prior art for training state? (Corfu/Tango are the closest — differentiate on: no sequencer service, filesystem-only, optimizer-semantics validation in replay) |
| Coordination & fencing | Chubby, ZooKeeper, fencing tokens, lease theory | We reuse, not invent; cite honestly |
| Filesystem-as-coordination on HPC | shared-FS job coordination, Lustre flock semantics literature | Supports C4's practicality claim |

## 4. Loops

### Loop 1 — Survey and delta table
Read/skim the clusters above; for each system produce one row:
{fault model, coordination substrate, recovery guarantee, recovery cost,
exactly-once story, scale evidence}. Output:
`RESEARCH_RELATED_WORK_AND_DIFFERENTIATION.md` updated (the P12 precondition
file), plus `novelty_delta.md` — the table with a one-line delta per row.

### Loop 2 — Claim freeze
Adversarial pass: for each claim C1–C4, write the strongest "this was already
done by X" attack and the response. Any claim without a clean response is
narrowed or cut *now*, not during rebuttal. Output: `claims_frozen.md` with
final claim wording — this file becomes the contract for PN-03/04/05 (every
experiment must serve a frozen claim).

### Loop 3 — Venue fit check
One page mapping the frozen claims to MLSys CFP topics and to the fallback
venues; identify which claims each venue's reviewers will weight most.

## 5. Acceptance gate

- [ ] Delta table covers all six clusters with ≥1 recent (2024–2026) system each.
- [ ] Every frozen claim has an attack/response pair and ≥1 experiment or
      artifact (existing or planned in PN-02..04) that evidences it.
- [ ] A named non-author (or independent checker pass) has read
      `claims_frozen.md` and failed to produce an unanswered prior-art attack.

## 6. Risks

- **Closest-prior-art risk:** shared-log systems (Corfu/Tango) and recent
  decentralized-training stacks. Mitigation: the delta must be architectural
  (no sequencer/coordination service; replay validates *optimizer semantics*,
  not just log integrity) and empirical (measured recovery envelope on HPC).
- **Scooping:** run a fresh search in the final week before submission;
  claims_frozen.md gets a "checked as of <date>" stamp.
