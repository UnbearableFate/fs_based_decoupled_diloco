---
title: "DuraLoCo Forward Plans (Claude revision)"
version: "4.0-claude"
date: "2026-07-12"
planning_basis_branch: "codex/duraloco-p07-distributed-lifecycle"
planning_basis_commit: "c099adc3c3a99127569a7d9bf38a58547022173c"
planning_basis_state: "P07 completed and Checker-verified (PBS 2369002); P08 next"
supersedes: "plans/duraloco_distributed_syncer_plan_bundle v3.1/3.2 forward sections (P08→P12, optional P09)"
companion_review: "docs/reviews/20260712_code_review.md"
---

# DuraLoCo Forward Plans — from P07-verified to project end

This directory is an independent revision of the forward half of the v3.2 plan
bundle. Historical plans (P00–P07, M00, P06A/B/C) stay authoritative where they
are; nothing here retrofits completed phases. The route is unchanged in
substance but gains one small phase:

```text
(P07 verified, c099adc)
   → H0  Pre-profiling hardening            [NEW — 1 short loop cycle]
   → P08 Distributed performance core
   → P10 Distributed SACC (shadow-first, system-only-first)
   → P11 Miyabi integration, chaos, D8 acceptance
   → P12 Formal experiments, artifact, paper evidence   [required-route end]
   -→ P09 Object-store backend               [optional, explicit user opt-in]
```

## Why this revision exists

The 2026-07-12 code review (`docs/reviews/20260712_code_review.md`) found
defects that interact badly with the v3.2 sequencing:

1. **P08 is profile-first, but the current storage backend makes every profile
   measure a pathology, not the design.** `PosixStorageBackend.list_prefix`
   walks the whole namespace and fully reads/hashes every object just to list
   keys; `head()` also reads full payloads (review H15/H16). The P07 lifecycle
   latency growth (45 s → 141 s per cycle) is largely explained by this. If
   P08 Loop 1 freezes baselines on top of it, every later "improvement" claim
   is confounded.
2. **The committer records false terminal evidence on crash paths** (review
   H2/H3/M4/M5). P08–P12 lean on committed stop facts as acceptance evidence;
   these must be truthful before more evidence is piled on them.
3. **The single-head CAS rests on an unprobed platform assumption**
   (cross-node `flock` on Lustre, review M11). This must be demonstrated, per
   job, before any further acceptance run is treated as meaningful.

Rather than stretching P08's charter, these become a small, sharply-scoped H0
phase with its own checker gate. P08 then starts from an honest baseline.

## Differences from the v3.2 bundle, phase by phase

| Phase | v3.2 | This revision |
|---|---|---|
| H0 | absent | New. Fix evidence-integrity and measurement-poisoning defects; probe platform lock semantics; land multi-fragment regression test. |
| P08 | profile-first; direct I/O, streaming reducer, bundling gate | Same charter and acceptance IDs, re-anchored to concrete defects (M17–M21): true `range_get`, prefix-scoped header-only listing, catalog validation cache, single-copy payload publication, cadence-gated materialization. Bundle gate unchanged. |
| P10 | SACC shadow/system-only/algorithm tiers | Unchanged in structure. Adds one observation source requirement (storage-op counters from H0/P08 telemetry) and keeps `not_qualified` as an honest terminal for the algorithm tier. |
| P11 | Miyabi D1→D2→D8→D8-R2 ladder | Unchanged, plus preflight must run the H0 cross-node lock probe and the packager must include storage-capability evidence. PBS output relocated out of the repo root. |
| P12 | formal evaluation, claim–evidence | Unchanged, with one added correctness cell: committed stop-fact truthfulness under injected crash (regression of review H2). |
| P09 | optional object store | Unchanged; explicitly benefits from true `range_get`/header-only `head` landed in P08. |

## Non-negotiable boundaries (inherited verbatim)

- No SQLite or embedded databases anywhere on the active surface.
- Single authority: immutable committed transition chain + one linearizable
  global head CAS. Listings, heartbeats, JSONL/CSV, `latest.json` are
  discovery/observation only.
- LFE is prepare-only; only the fenced Floating Committer commits.
- Fragment params and outer state are referenced atomically by one committed
  transition; never separately-overwritten "latest files".
- Duplicate execution allowed; divergent result digests for one work-order
  identity are a fatal, blocking determinism violation.
- Single global committed history; no per-fragment heads on the required route.
- Empty-cache strict replay on fresh open, takeover, CAS ambiguity, head jump,
  corruption suspicion, and ownership epoch change.
- Caches, cursors, prefetch, telemetry: all deletable, never authority.

## Files

- `00_H0_PRE_P08_HARDENING.md`
- `01_P08_DISTRIBUTED_PERFORMANCE_CORE.md`
- `02_P10_DISTRIBUTED_SACC.md`
- `03_P11_MIYABI_ACCEPTANCE.md`
- `04_P12_FORMAL_EVALUATION.md`
- `05_P09_OBJECT_STORE_OPTIONAL.md`

Each phase keeps the established loop discipline (RED → GREEN → HARDEN →
CHECK/PERSIST per loop; single-writer maker + independent checker; STATE.yaml,
error ledger, phase report, artifact bundles; terminal-failure retry lock).
