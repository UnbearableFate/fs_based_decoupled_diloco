---
plan_id: "PN-05"
title: "Paper Production with a Reproducible Figure Pipeline"
status: "planned"
depends_on: ["PN-01", "PN-02", "PN-03 (partial ok)", "PN-04 (partial ok)"]
parallel_with: ["PN-06"]
effort: "4–6 weeks calendar (overlaps the campaigns); writing starts on partial results"
---

# PN-05 — Paper Production

## 1. Mission

Produce a submittable MLSys paper in which every number, figure, and claim is
generated from immutable artifacts by a checked-in pipeline, and the prose
survives an internal adversarial review before the real one.

## 2. Paper skeleton (freeze early, revise text not structure)

1. **Introduction** — thesis: decentralized training can get durability,
   auditability, and exactly-once semantics from a shared filesystem alone;
   the recovery point *is* the training log.
2. **Motivation / setting** — HPC batch reality (no services, node churn,
   Lustre), fault model, why checkpoint-restart's lost-work economics differ
   from a transactional trajectory.
3. **Design** — the head-CAS transaction log, marker-last publication,
   fencing, strict replay & snapshot+suffix; source: `docs/architecture/`
   (already written; condense).
4. **Correctness** — invariants, the TLA+ spec + mutant methodology (PN-02),
   crash-matrix testing; one figure: spec/code correspondence.
5. **Implementation** — Lustre capability probing, envelope storage, streaming
   reduction; honest paragraph on what a filesystem cannot give you.
6. **Evaluation** — PN-03 baselines/ablations + PN-04 scale evidence + the
   P12 fault/recovery campaign. Key figures: overhead-vs-interval curve;
   recovery decomposition (lease policy vs replay work); flat growth curves
   (with pre-fix "before" contrast); stage decomposition at model scale.
7. **Related work** — PN-01 delta table, prose form.
8. **Non-claims & limitations** — explicit; this project's honesty discipline
   is a reviewer asset, spend it.

Target: MLSys page budget per the CFP (check; historically ~10 pages +
references). Double-blind: strip Miyabi-identifying strings per PN-07.

## 3. Reproducible figure pipeline (non-negotiable)

- `paper/pipeline/`: one script per figure/table, reading only from
  `artifacts/` run manifests and P12 registry outputs, writing
  `paper/generated/`. No number enters the LaTeX except via a generated
  `\input` macro file.
- CI check (login-node-safe): regenerate all figures from artifacts and diff
  digests; a paper build with stale generated files fails.
- Every figure caption carries the registry cell IDs it renders.

## 4. Loops

1. **Skeleton + claims wiring.** Draft sections 1–5 from `docs/architecture/`
   and `claims_frozen.md` while campaigns run; each claim sentence gets a
   `\cite`-like marker to its evidence cell (resolved later by the pipeline).
2. **Evaluation drafting.** As PN-03/04 cells complete, land figure scripts
   and write the evaluation around *actual* numbers; forbid placeholder
   numbers in prose.
3. **Internal adversarial review.** Two mock reviews using the MLSys review
   form: one reviewer briefed as "distributed-training expert", one as
   "storage/consistency expert". Every raised weakness gets a written
   response: fix, bound the claim, or add to limitations.
4. **Polish loop.** Abstract last; intro rewritten after evaluation is final;
   related-work freshness re-check (PN-01 scoping stamp).

## 5. Acceptance gate

- [ ] Paper builds from a clean checkout: artifacts → pipeline → figures →
      PDF, no manual steps.
- [ ] Zero numbers in prose without a generated-macro source.
- [ ] Both mock reviews answered in writing; no unresolved "reject-level"
      issue remains.
- [ ] Non-claims section reviewed against `docs/architecture/01` and the
      failure-model contract for drift.

## 6. Risks

- **Campaign slippage.** Sections 1–5 and PN-02 content are compute-
  independent — front-load them; the evaluation section is the only part
  gated on PN-03/04.
- **Overclaiming under deadline pressure.** The claims file is frozen in
  PN-01; any strengthening of a claim after PN-03/04 results requires the
  same checker sign-off as weakening would.
