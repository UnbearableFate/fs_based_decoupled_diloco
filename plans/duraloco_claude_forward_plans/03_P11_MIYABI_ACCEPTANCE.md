---
plan_id: "P11"
title: "Miyabi Integration, Chaos, and Dedicated-Syncer-Free Acceptance"
status: "planned"
date: "2026-07-12"
planning_basis_commit: "resolve_from_P10_verified_report"
target_branch: "codex/duraloco-p11-distributed-acceptance"
depends_on: ["P10"]
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
next_phase: "P12"
agent_decision_gates:
  - "jobs with select<=16 and walltime<=02:00:00 may be submitted autonomously on the 1→2→8 node ladder; non-transient failures obey the retry lock"
human_approval_gates:
  - "resources beyond the established Miyabi envelope, 72h formal soak, or public cloud"
---

# P11 — Miyabi Integration, Chaos, D8 Acceptance

## 1. Mission

Solidify the P06B–P10 distributed-syncer mainline into a repeatable Miyabi
production workflow: preflight, chaos, artifact packaging, and operator drills
for D1, D2, D8, and D8-R2. The primary acceptance is **eight learner nodes,
zero dedicated syncer nodes**; C9 (dedicated CRS) remains a matched reference
baseline only.

Research claim: under a real HPC scheduler, Lustre, and whole-node failures,
the system keeps a single authority with no global outage (or bounded RTO),
and the migration of the 9-node 1S+8L workload to 8-node D8 has auditable
resource-saving and interference evidence.

## 2. Preconditions

- [ ] P10-A01–A24 pass; default controller/redundancy mode frozen.
- [ ] P07 lifecycle + P08 telemetry integrated; topology manifests verifiable.
- [ ] Clean commit, dependencies, checksums consistent.

## 3. Scope

Must complete: PBS scripts + preflight + static shell checks; environment/
module/cache/storage-namespace validation; role placement + capability audit
(**including the H0 cross-node lock probe as a per-job preflight step, with
the mount-option evidence recorded in the job manifest**); D1 real acceptance;
D2 failover/chaos; D8 50×10 terminal acceptance; D8-R2 controlled chaos;
matched C9 baseline; snapshot/capsule/GC dry-run integration; SACC
fixed/shadow/default validation; fault tapes, authority timelines, stage
timings, qstat lineage; fail-closed artifact packager; operator runbook +
recovery drill; terminal-retry lock discipline.

Repo/ops hygiene items deferred from the code review land in Loop 1:
- PBS stdout/stderr routed to `logs/pbs/` (not the repo root; migrate the
  existing `*.o*` clutter out of the tree).
- `merge.py` retirement or explicit legacy-reference designation (review L24)
  and the `stop_requested` duplicate removal (L25) — zero-runtime-risk
  cleanups that belong in the standardization pass, verified by the static
  gate.
- Config validation rejects unsupported `data.streaming: true` (review L28)
  unless implemented by then.

Explicitly not doing: automatic 72 h soaks; runtime on login nodes; C9 as
production path; new optimizer/protocol generations; deleting failed/
cancelled/operator-terminated runs; disguising operator termination as
infrastructure failure.

## 4. Design decisions to freeze first

D-1101 exact D8/D8-R2 PBS layout + CPU affinity; D-1102 default production
controller/redundancy mode; D-1103 fault-tape timing + expected RTO/RPO
bounds; D-1104 C9 matched alignment; D-1105 terminal criteria + inconclusive
classification; D-1106 minimum artifact evidence; D-1107 retry-lock release
conditions; D-1108 operator drill + authoritative stop; D-1109 optional soak
approval boundary.

## 5. Execution loops

### Loop 1 — PBS/preflight standardization
Fail-fast checks before submission: commit, modules, storage, namespace,
topology, forbidden surfaces (hidden syncer node, missing LFE, duplicate GPU
assignment, login-node runtime, stale plan checksums, SQLite artifacts), and
the storage capability probe (dir-fsync + cross-node lock). Reusable
preflight, PBS scripts, manifest skeleton, role/hostname/rank mapping, actual
affinity audit. HARDEN: queued/cancelled, module drift, permissions, partial
artifact dirs, resubmission lineage. **Stop when:** invalid jobs cannot reach
training and valid jobs are fully described by their manifests.

### Loop 2 — D1 real acceptance
Minimal real model/data path: learner + LFE + committer + lifecycle +
controller, ≤10 optimizer steps, at least one FWO/PFT/final-commit/adopt;
snapshot + capsule; executor and committer restart; fixed/shadow modes.
HARDEN: payload/marker kills, head jump, corrupt successor, local-state
deletion, strict replay. **Stop when:** finite loss, correct
authority/digests, complete artifact.

### Loop 3 — D2 failover/chaos
Two learner nodes prove committer, primary/backup, whole-node, and
reconfiguration semantics: P05 old-owner resume, P06C duplicate/divergence,
same-node owner+committer kill, false suspicion, capsule restore, GC dry-run.
Kill points cover before/after PFT, before/after CAS, response loss, stale
epoch return. **This loop must include the H0/P08 crash-evidence regressions
as chaos assertions: no injected crash may produce a `completed` stop fact,
and a killed committer's successor must resume (or terminate) per the frozen
D-0800 semantics.** **Stop when:** zero split brain, double inclusion, mixed
state, or live deletion.

### Loop 4 — D8 primary acceptance
8 learner nodes, 0 dedicated syncers, GPT-2/WikiText-2 50×10, 15-minute
target. Pre-registered topology/terminal/interval/adoption/lifecycle/
telemetry/controller/resource criteria. Fixed and default production modes at
least once each on the same clean commit. One LFE kill and one committer
takeover inside the run (whole-node loss belongs to D8-R2). Matched C9
comparison + node/GPU-hours + interference. **Stop when:** D8 terminal, or a
real failure is preserved under the retry discipline and fixed.

### Loop 5 — D8-R2 controlled chaos
Pre-recorded fault tape: primary LFE, backup, committer, whole learner node,
slow Lustre/CPU, snapshot/GC overlap; 50×10 or pre-registered equivalent;
failure-free control retained; RTO/RPO, fault goodput, duplicate cost,
quality smoke. At least one primary+committer co-failure and one late stale
node return; same-FWO divergence injection as a separate expected-BLOCKED
run. **Stop when:** all safety gates pass and liveness/performance data are
complete; the checker independently reconstructs authority and fault
timelines from the bundle.

### Loop 6 — Artifact and operator drill
Packager fails closed on missing summaries, raw events, qstat, commit/config/
checksums, or failure lineage. Package manifests, commands, logs, object
refs, traces, analysis, checker outputs, reproduction script. Drill:
authoritative stop, takeover, capsule restore, strict verify — executed by an
operator following only the runbook. HARDEN: clean-directory reproduction,
read-only store copy, partial bundles, historical failure inclusion.
**Stop when:** the bundle is self-describing and fail-closed.

## 6. Invariants

No dedicated syncer node in D8/D8-R2. C9 never writes into a distributed
generation. Head mutation only through the audited committer API; learners/
LFEs have no head-CAS surface. Fault injection never deletes real-failure
evidence. Retry lock prevents blind same-shape resubmission. Artifacts fail
closed on missing evidence. Login nodes are control-plane only.

## 7. Acceptance

- [ ] P11-A01: all PBS/shell/static checks pass.
- [ ] P11-A02: preflight detects hidden syncers, role mismatches, forbidden
      surfaces, and missing storage capabilities (dir-fsync, cross-node lock).
- [ ] P11-A03/A04: D1 real run finite + distributed commit/adopt; strict
      replay/snapshot/capsule/controller smoke.
- [ ] P11-A05/A06: D2 committer/owner/whole-node failover without split
      brain; duplicate/divergence/false-suspicion behave as specified;
      crash paths never fabricate `completed` stops.
- [ ] P11-A07–A10: D8 manifest is 8 learner nodes / 0 dedicated syncers;
      50×10 in the 15-minute target; per-role hostname/session/GPU/affinity/
      ownership traceable; training continues through LFE kill and committer
      takeover.
- [ ] P11-A11/A12: matched C9 reference complete, outside D8 authority;
      resources, latency, interference, quality smoke comparable.
- [ ] P11-A13–A16: D8-R2 chaos campaign passes; whole-node and co-failure
      RTO/RPO/fault-goodput recorded; same-FWO divergence expected-BLOCKED
      artifact complete; lifecycle concurrency causes zero live deletion.
- [ ] P11-A17: SACC default-mode decisions replayable; fixed fallback passes.
- [ ] P11-A18–A20: full lineage for pass/fail/inconclusive/queued/cancelled/
      retry; retry lock + D1→D2 requalification on non-transient terminal
      failures; operator terminations recorded truthfully.
- [ ] P11-A21/A22: packager fails closed; checker re-runs the suite plus
      historical and fresh counterexamples from the clean bundle.
- [ ] P11-A23/A24: no SQLite/embedded DB; authority audit shows no second
      authority or per-fragment heads.
- [ ] P11-A25/A26: report/state/checksums/clean commit consistent;
      `STATE.yaml.next_action = P12`.

## 8. Startup instruction (copyable)

```text
Execute P11 Miyabi acceptance. Standardize PBS/preflight (including the storage
capability and cross-node lock probes and logs/pbs output routing), then climb
D1→D2→D8→D8-R2. D8/D8-R2 must run on 8 learner nodes with 0 dedicated syncers;
C9 is a matched reference only. Chaos loops must assert truthful crash
evidence per D-0800. Run fault tapes, lifecycle/controller integration, and
the artifact/operator drill. Obey the non-transient retry lock and login-node
discipline. Proceed to P12 when all gates pass.
```
