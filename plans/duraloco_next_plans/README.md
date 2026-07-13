---
title: "DuraLoCo Publication Plans — from P12-verified to MLSys submission"
version: "1.0"
date: "2026-07-13"
planning_basis_branch: "codex/duraloco-p08r-replay-440s"
depends_on:
  - "All docs/review findings fixed (P0–P3, incl. the D-01/D-02/D-03 scalability generation)"
  - "plans/duraloco_claude_forward_plans executed through P12 (formal evaluation complete)"
companion_review: "docs/review/README.md"
target_venue_class: "systems/ML-systems conference (primary: MLSys; fallbacks: EuroSys, ATC, SoCC, HPDC)"
---

# DuraLoCo Publication Plans (PN series)

## Why this bundle exists

P12 produces *evidence*: preregistered experiments, claim–evidence bindings,
immutable run manifests. A conference submission needs five more things that
no existing phase produces:

1. a defensible **novelty position** against the decentralized-training and
   fault-tolerant-systems literature (PN-01);
2. a **formal specification** backing the exactly-once and recovery-equivalence
   claims that the paper's core contribution rests on (PN-02);
3. **external baselines and ablations** — the first question every systems
   reviewer asks is "what does this cost versus checkpoint-restart?" and P12's
   internal checkpoint-baseline cell is not enough on its own (PN-03);
4. **scale/duration evidence** beyond 10 transitions of GPT-2 (PN-04);
5. the **paper, artifact, and submission machinery** themselves (PN-05/06/07).

## Route

```text
(P12 verified; review findings fixed)
   → PN-01 Positioning & related work        ┐ parallel
   → PN-02 Formal spec & model checking      ┘
   → PN-03 Baselines & ablations             ┐ parallel (compute-bound)
   → PN-04 Scale & long-horizon evidence     ┘
   → PN-05 Paper production                  (depends on PN-01..04)
   → PN-06 Artifact evaluation package       (parallel with PN-05)
   → PN-07 Submission, rebuttal, camera-ready
```

## Phase index

| Phase | File | Output |
|---|---|---|
| PN-01 | `PN01_POSITIONING_RELATED_WORK.md` | Novelty-delta table, claim set, related-work section draft |
| PN-02 | `PN02_FORMAL_SPEC.md` | TLA+ spec + model-checking results for the core invariants |
| PN-03 | `PN03_BASELINES_ABLATIONS.md` | Matched baseline + ablation matrix with analysis |
| PN-04 | `PN04_SCALE_EVIDENCE.md` | Long-horizon + larger-model runs; flat-cost and quality curves |
| PN-05 | `PN05_PAPER_PRODUCTION.md` | Submittable paper with reproducible figure pipeline |
| PN-06 | `PN06_ARTIFACT_EVALUATION.md` | AE-ready artifact (runs off-Miyabi) |
| PN-07 | `PN07_SUBMISSION_LOGISTICS.md` | Deadline plan, internal review, rebuttal/camera-ready |

## Working-backwards timeline

Check the actual MLSys CFP first; historically the deadline falls in
September–October for the following year's conference. Assuming a ~2026-10-01
deadline as the planning anchor:

```text
2026-07-15 → 08-05   PN-01 + PN-02 (desk work, parallel)
2026-07-20 → 08-25   PN-03 + PN-04 (compute; shares D8 allocations)
2026-08-15 → 09-15   PN-05 paper drafting (starts on partial results)
2026-08-25 → 09-20   PN-06 artifact freeze
2026-09-15 → 09-25   PN-07 internal mock review + revision
2026-09-25 → deadline  buffer, submission
```

If the real deadline is earlier than ~9 weeks out, cut scope in this order:
PN-04 larger-model cell first (keep long-horizon), then PN-03 third baseline,
never PN-02 or the ablation core.

## Ground rules (inherited from project discipline)

- Every number in the paper must resolve to an immutable artifact
  (run manifest, registry entry, or analysis output digest). No hand-copied
  values.
- Negative or bounded results are publishable results; claims shrink to
  evidence, never the reverse.
- Compute follows the existing Miyabi rules: strict 8-node allocation for
  distributed cells, 1→2→8-node qualification for anything new, no ninth node.
- Anything leaving the cluster (arXiv, artifact, code release) needs explicit
  human approval — same gate as the forward plans' human_approval_gates.
