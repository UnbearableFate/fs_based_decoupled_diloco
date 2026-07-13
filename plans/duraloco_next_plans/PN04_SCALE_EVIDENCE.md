---
plan_id: "PN-04"
title: "Long-Horizon and Larger-Model Evidence"
status: "planned"
depends_on: ["P12", "docs/review D-01/D-02/D-03 fixes (scalability generation)"]
parallel_with: ["PN-03"]
effort: "3–5 weeks; the largest compute consumer in the bundle"
---

# PN-04 — Long-Horizon and Larger-Model Evidence

## 1. Mission

Close the two evidence gaps that would dominate reviews of the current
results: **10 transitions is not a run**, and **GPT-2-small is not a model**.
Produce (a) long-horizon evidence that per-transition cost and lifecycle cost
are flat after the scalability fixes, and (b) at least one larger-model
qualification showing the protocol's I/O path scales to model sizes reviewers
consider current.

This phase is only meaningful *after* the review's scalability generation
(chained prefix digest, windowed consumption, state-based snapshots) has
landed — otherwise the measured growth curves would demonstrate the defect,
not the design.

## 2. Evidence cells

| Cell | Shape | Purpose |
|---|---|---|
| L1 | D8, GPT-2, 500–1000 optimizer transitions, lifecycle cadence on, ≥1 injected committer fault per 100 transitions | flat per-transition manifest bytes, flat lifecycle time, flat replay time; recovery envelope unchanged at transition 900 vs 10 |
| L2 | memory-backend synthetic long-run (5k transitions, no GPU) | asymptotic assertion at 10× horizon, cheap; becomes a permanent regression test (the suite currently has no bounded-growth assertion) |
| M1 | D8, largest model that fits the qualification envelope (target 1–3 B params, bf16 transport; decide exact size in Loop 1), ≥50 transitions, ≥8 fragments | payload-path scaling: per-transition wallclock decomposition vs GPT-2; validates D-05/C-13 fixes at size |
| M2 (stretch) | M1 + one takeover fault | recovery envelope at model scale (replay tensor-byte bound is what's being tested) |
| Q1 | L1's model quality vs PN-03's B1/B2 at matched tokens | the non-inferiority claim needs a long-enough run to be credible |

## 3. Loops

### Loop 1 — Feasibility and sizing
Compute the byte budget per transition for candidate model sizes (params ×
fragments × the post-fix copy count); pick the M1 size where a transition's
payload traffic stays under a frozen budget (e.g. ≤60 s/transition on measured
Lustre bandwidth). Qualify 1→2 nodes with the tiny-model smoke path first.
RED: if the byte model predicts infeasibility, that bound itself becomes a
paper result ("scales to N params on this fabric") — do not force the run.

### Loop 2 — L2 synthetic long-horizon (login-safe, memory backend)
Land as a pytest regression: assert frontier bytes, snapshot bytes, replay
manifest work, and lifecycle time are O(1) per transition across 5k
transitions. This is also the review's P2 acceptance evidence.

### Loop 3 — L1 long-horizon D8
One 8-node allocation, checkpoint the campaign into PBS-walltime-sized
segments using the system's own recovery (each segment resumes via
takeover — which is itself evidence). Record growth curves for every cost
dimension; faults injected on schedule.

### Loop 4 — M1/M2 model-scale D8
Run the sized model; produce the per-stage wallclock decomposition figure
(the PN-03 overhead story at scale). M2 only if M1's envelope leaves walltime.

### Loop 5 — Analysis
Growth-curve figures (cost vs transition index, flat lines post-fix, with the
pre-fix curves from P08R-era data as the "before" contrast — a strong figure),
and the scale table (GPT-2 vs M1 stage decomposition).

## 4. Acceptance gate

- [ ] L2 asserts bounded growth at 5k transitions and is in CI.
- [ ] L1 shows per-transition and lifecycle costs flat within noise from
      transition 50 to the end; recovery at late transitions within the
      early-run envelope.
- [ ] M1 completes with the frozen per-transition budget met; decomposition
      figure produced.
- [ ] Every figure resolves to immutable run artifacts.

## 5. Risks

- **Walltime.** L1 segmented by design; if a segment fails terminally, the
  project's one-resubmission rule applies per segment, not per campaign.
- **M1 memory (LFE is CPU float32).** The streaming reducer bounds this;
  verify in Loop 1 on one node before committing to a size (C-02 fix required
  so one RSS spike doesn't poison the run).
- **Quality claim weakness.** If Q1's horizon is still too short for a strong
  non-inferiority claim, report it as bounded ("no divergence observed within
  N tokens") — do not overclaim; the paper is a systems paper.
