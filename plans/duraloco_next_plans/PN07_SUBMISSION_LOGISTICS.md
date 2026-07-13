---
plan_id: "PN-07"
title: "Submission, Rebuttal, and Camera-Ready Logistics"
status: "planned"
depends_on: ["PN-05", "PN-06"]
effort: "spread across the final 6 weeks; small but deadline-critical"
---

# PN-07 — Submission, Rebuttal, and Camera-Ready

## 1. Mission

Everything between "the paper and artifact exist" and "the paper is submitted,
defended, and published" — done early enough that none of it becomes a
deadline-week emergency.

## 2. Venue decision (do this in week 1, not at the end)

1. Pull the **actual CFPs**: MLSys (primary), EuroSys, USENIX ATC, SoCC,
   HPDC (fallbacks, roughly in order of fit for the frozen claims).
   Historically MLSys deadlines fall around September–October for the
   following year's conference — verify, and re-anchor the whole PN timeline
   to the real date immediately.
2. Record per venue: deadline (abstract + full), page budget, double-blind
   policy, arXiv/preprint policy, artifact-evaluation track dates, rebuttal
   format.
3. Freeze the primary + one fallback whose deadline is 2–4 months later, so a
   rejection or a missed date has a pre-agreed landing zone (EuroSys and ATC
   cycles usually interleave well with MLSys).

## 3. Task checklist

### Before submission

- [ ] **Approvals** (start immediately — slowest item): institutional /
      supervisor approval for publication; Miyabi facility acknowledgment and
      any usage-publication policy; check whether facility policy requires
      naming or anonymizing the machine in a double-blind submission.
- [ ] **Authorship & credit**: author list, order, contribution statement,
      acknowledgment of compute grants.
- [ ] **Double-blind pass**: anonymize the PDF (names, cluster identifiers,
      repo URLs, artifact links via anonymous hosting); verify PDF metadata
      is clean; ensure citations to the project's own prior artifacts are
      neutral ("an existing implementation").
- [ ] **Preprint decision**: arXiv before vs after notification, per venue
      policy and advisor preference (human decision gate).
- [ ] **Submission dry run**: account on the submission system a week early;
      upload a draft; check format-checker output (fonts, margins, page
      limit) — never first-upload on deadline day.
- [ ] **Freeze commit**: the paper cites one repo commit; tag it; PN-05
      pipeline re-run from that tag as the final consistency check.

### Rebuttal window

- [ ] Reuse PN-05's mock-review Q&A file as the rebuttal seed; assign one
      owner to draft within 24 h of reviews landing.
- [ ] Policy, pre-agreed: no new experiments promised in rebuttal unless they
      can actually run within the window on already-approved compute; claims
      shrink to evidence, as always.

### On acceptance

- [ ] Camera-ready: de-anonymize, facility acknowledgments, artifact links
      live, final pipeline re-run.
- [ ] Artifact evaluation submission per PN-06 (AE deadlines usually trail
      paper acceptance — get them into the calendar at venue-decision time).
- [ ] Code release: license audit finalized, public repo cut from the frozen
      tag (human approval gate), README pointing at the paper.

### On rejection

- [ ] Reviews triaged into: fixable-by-writing / needs-new-evidence /
      reviewer-error; fold the first class into the paper within 2 weeks
      while context is fresh; re-target the pre-agreed fallback venue.

## 4. Calendar (re-anchor to the real CFP in week 1)

```text
T-9w   venue frozen; approvals requested; submission accounts created
T-6w   PN-05 evaluation section complete on final data
T-4w   internal mock reviews done; revision complete
T-3w   PN-06 artifact frozen; cold-machine rehearsal passed
T-2w   double-blind + format dry run; freeze-commit tagged
T-1w   full re-generation from tag; final read; submit early
T-0    deadline (buffer already spent, not needed)
```

## 5. Risks

- **Approvals latency** dominates: institutional and facility sign-offs can
  take weeks — they are the first action of this phase, not the last.
- **Deadline drift**: if the real CFP deadline is closer than 9 weeks at
  PN-07 start, invoke the scope cuts pre-listed in `README.md` (PN-04 M-cell
  first) rather than compressing PN-05's review loop — an unreviewed paper is
  the worst cut of all.
