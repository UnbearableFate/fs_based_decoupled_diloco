---
plan_id: "P09"
title: "Optional Object-Store Backend and Hybrid Baseline"
status: "optional_deferred"
date: "2026-07-12"
planning_basis_commit: "resolve_only_after_explicit_user_opt_in (from P12 completed commit)"
target_branch: "codex/duraloco-p09-distributed-object-store"
depends_on: ["P12", "explicit_user_opt_in"]
execution_mode: "single-writer maker + independent checker"
automatic_progression: false
human_approval_gates:
  - "starting this phase at all"
  - "real public-cloud credentials/cost"
---

# P09 — Optional Object-Store Backend (opt-in only)

## 1. Mission

After explicit user opt-in, port the P06B–P12 mainline (FWO/PFT,
membership/ownership, floating commit, lifecycle, D8) to S3-compatible
storage and compare consistency/performance against POSIX/Lustre and hybrid
placements. Not on the required route; never a fallback to the centralized
1S+8L architecture.

## 2. Contracts that must survive the port

D8/D8-R2 still have no dedicated syncer. LFE remains prepare-only; the
floating committer performs fenced conditional commits. Listings are
discovery only (S3 listing lag makes this contract load-bearing, not just
prudent). Immutable objects + conditional head/manifest remain the sole
authority. Same-FWO duplicate determinism and at-most-once logical commit.
Committed membership/ownership. Snapshot/reachability/GC/capsule adapted.
Empty-local-state recovery. CRS stays a reference baseline.

Two P08 deliverables are prerequisites this plan explicitly builds on: true
`range_get` (multipart/ranged reads are the S3-native access mode) and
header-only `head` (S3 `HEAD` maps to it directly). If P08 closed either as
not-implemented, they are in P09 Loop 1 scope.

## 3. Scope (only once started)

Must complete: S3 semantic backend + capability probe (conditional-write
support varies by provider — probe, don't assume); conditional head/manifest
update; multipart, marker-last publication; request identity /
response-loss / multipart recovery; FWO/PFT/final transition on D1/D2/D8;
R2 duplicate/reconfiguration; snapshot/reachability/GC semantics; MinIO
local E2E; POSIX vs object-store state/digest equivalence; hybrid
payload/control placements; provider cost/request/latency telemetry;
optional public-cloud probe only after approval.

Explicitly not doing: ETag as content SHA; reliance on listing correctness;
metadata databases; credentials or paid resources without approval; a second
authority born from object-store convenience features; automatic start.

## 4. Execution loops

1. **Backend contract** — immutable put/get/range/list-discovery,
   conditional head, marker-last, typed errors; validated against the common
   storage contract shared with POSIX.
2. **Multipart + response loss** — payload complete before marker,
   abort/cleanup, SDK setup/publish failures, same-ID conflicts, idempotent
   retries.
3. **Distributed protocol on MinIO** — D1/D2: FWO/PFT/floating committer/
   R2/fencing/listing omission/empty-local recovery; state digests match
   POSIX bitwise.
4. **D8 object/hybrid baseline** — 8 learner nodes, 0 dedicated syncers,
   50×10; preregistered placements: all-POSIX, object-control+object-payload,
   POSIX-control+object-payload.
5. **Lifecycle + optional public cloud** — snapshot/GC/capsule + cost
   metrics; public cloud only via approval, minimal probe, secrets redacted.

## 5. Acceptance

- [ ] P09-A01: S3 backend passes the common storage contract.
- [ ] P09-A02: competing conditional-head writers yield exactly one winner.
- [ ] P09-A03: listing omission never affects correctness.
- [ ] P09-A04: multipart/marker crash + response loss recoverable.
- [ ] P09-A05: mutation request identity distinguishes retry vs independent
      request.
- [ ] P09-A06: ETag never treated as SHA.
- [ ] P09-A07/A08: MinIO D1/D2 distributed path passes; POSIX/object state
      and core digests identical.
- [ ] P09-A09/A10: R2 duplicate/reconfiguration and
      snapshot/reachability/GC/capsule pass.
- [ ] P09-A11: D8, 8 learner nodes, 0 dedicated syncers, 50×10 terminal.
- [ ] P09-A12/A13: hybrid placements measured independently;
      bytes/requests/cost/latency/GPU interference complete.
- [ ] P09-A14: no SQLite/metadata DB on the active surface.
- [ ] P09-A15: empty-local-directory replay/takeover strict.
- [ ] P09-A16/A17: cloud dependency an optional pinned extra; safe skip
      without approval/credentials.
- [ ] P09-A18: non-transient D8 failures obey the retry discipline.
- [ ] P09-A19: checker audits secrets/cost/listing assumptions.
- [ ] P09-A20: report/checksums/clean commit consistent.

## 6. Start rule

A branch is created only after the user explicitly selects P09. Until then
every acceptance item is not-applicable and P12's required-route completion
stands on its own.
