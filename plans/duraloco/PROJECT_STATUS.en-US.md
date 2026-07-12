# DuraLoCo Project Status

Status date: 2026-07-12

Current verified phase: P07 completed

Next required phase: P08

Current feature branch: `codex/duraloco-p07-distributed-lifecycle`

P07 verified implementation/Checker commit: `c099adc3c3a99127569a7d9bf38a58547022173c`

## Executive summary

DuraLoCo now has a verified SQLite-free, event-sourced implementation from the
baseline contract through distributed lifecycle management. The active production
direction uses learner-hosted fragment executors and learner-hosted floating
committer candidates, with no dedicated syncer node. Immutable transition objects
and one global head compare-and-swap remain the only persistent optimizer authority.

The completed work proves correctness, recovery, redundancy, and lifecycle safety
at the D8-R2 shape: eight learner nodes, eight learners, eight learner-hosted
fragment executors, replication factor two, and zero dedicated syncer nodes. P07
adds ancestry-pinned snapshots, snapshot-plus-suffix replay, typed reachability,
guarded GC, exact learner capsules, bounded lifecycle retention, and lease-safe
long lifecycle operations. Its independent Checker passed all 24 acceptance IDs.

The project is not finished. P08 must now reduce prototype data movement and
lifecycle overhead, add reconstructable stage telemetry, and quantify learner/LFE
resource interference without weakening validation or authority. P10, P11, and
P12 remain required after P08. P09 remains an optional post-P12 object-store
extension and is not on the automatic route.

## Authority and architecture that are now frozen

The persistent source of truth is the committed DuraLoCo transition chain plus one
global head CAS. A commit may atomically reference parameter fragments, matching
outer-optimizer state, membership/ownership facts, fencing facts, and control
transitions. There are no per-fragment heads and no mutable database authority.

Everything else is either immutable input/evidence or derived observation:
proposals, work orders, prepared results, execution attempts, leases, heartbeats,
snapshots, capsules, acknowledgements, GC marks, `latest.json`, checkpoints,
telemetry, and reports. These objects may improve discovery, performance, audit,
or recovery, but they cannot independently choose or advance the optimizer
trajectory.

Learner-hosted fragment executors have prepare-only capability. A floating
committer may update the global head only while holding the current committed
fencing identity and an observational lease. Membership and ownership changes are
committed facts; heartbeat suspicion is evidence, not authority. Duplicate work is
allowed, but one work-order identity may have at most one logical committed result.
Equivalent duplicate results converge; divergent results fail closed and remain
auditable.

Fresh open, takeover, explicit verification, CAS ambiguity, head jump, corruption
suspicion, or ownership-boundary change starts with empty-cache strict replay.
Process-local verified-object memoization is allowed only after complete successful
replay and is never serialized or carried across ownership.

## Completed milestone lineage

| Milestone | Status | Delivered capability | Principal verified evidence |
|---|---|---|---|
| P00 | Completed | Baseline inventory, research contract, invariants, and Agent Spine | `993accd`, independent report |
| P01 | Completed | Protocol v2 schemas, identities, strict validation, quarantine, v1 adapter | `cfa7442`, one-node/Checker |
| P02 | Completed | Independent deterministic reference simulator and in-memory backend | `7e12997`, 10,000-trace/Checker evidence |
| P03 | Completed | Semantic storage API and POSIX/Lustre capability/fault contract | `952b39b`, one/two-node/Checker |
| P04 | Completed | Transactional fragment log, one-CAS commit, prefix recovery, strict replay | `a655413`, one/two/nine-node/Checker |
| M00 | Completed | Removed SQLite authority and requalified P00–P04 on the log-only runtime | `c052438`, one/two/nine-node plus Checker |
| P05 | Completed | Production syncer lease, committed fencing, failover, control transitions | `82dbec1`, final 1/2/9-node ladder; Checker `fe41f80` |
| P06 | Completed | Learner intervals, boundary adoption, response-loss publication, warm recovery | `2581a4d`, final 1/2/9-node ladder; Checker `030129e` |
| P06A | Completed | Pure syncer kernel decomposition and archived CRS equivalence | `5a71502`, C1/C2/C9; Checker `cea5a6d` |
| P06B | Completed | Learner-hosted executors, distributed prepare, factor-one D8 with no dedicated syncer | `d5e2901`, D1/D2/D8; Checker PBS `2362890` |
| P06C | Completed | Factor-two ownership, duplicate convergence, hedging, reconfiguration, failover | `cba9f48`, D1-R2/D2-R2/D8-R2; Checker PBS `2363373` |
| P07 | Completed | Snapshots, reachability, guarded GC, exact capsules, bounded lifecycle | `2295467` runtime; report PBS `2368976`; Checker `c099adc`/PBS `2369002` |

P00–P04 are historical evidence under the original staged route. M00 is the
mandatory runtime rebase: historical database-era reports remain evidence only
and do not reintroduce a compatibility database runtime. P05 and P06 established
the central reference behavior that P06A decomposed and P06B/P06C distributed.

## Current verified distributed behavior

P06B's factor-one D8 used exactly eight learner nodes, eight learners, eight LFEs,
two learner-hosted committer candidates, and no dedicated syncer. It completed
GPT-2/WikiText-2 50×10 in 470 seconds with ten optimizer transitions and complete
publish-to-prepare-to-commit-to-adopt timing. This remains the frozen factor-one
baseline.

P06C's hedged factor-two D8-R2 completed the same workload in 528 seconds. It
proved redundant prepared execution, whole-node membership reconfiguration,
committer takeover, strict replay, and authoritative stop. It also produced an
important negative result: under the tested storage and six-second hedge delay,
elapsed time rose 12.3%, logical executor input was 1.77×, and output was 1.90×
the factor-one baseline. Correctness and availability passed, but redundancy was
not a throughput win in that regime.

P07's lifecycle-enabled D8-R2 completed ten optimizer transitions in 1100 seconds.
It added five snapshot/GC cycles, five snapshot pins, one exact capsule per
learner, executor-process loss, whole learner-host loss, membership revision one,
and authoritative stop. The valid authority completed before an inherited
900-second reporting envelope rejected the wrapper; the preserved authority was
recovered into PASS reports by PBS `2368976`.

The P07 effective-live samples were 150, 196, 220, 248, and 276 objects. The
last-three-sample delta was 56, below the preregistered maximum of 64. Raw
inventory still grew because real-namespace deletion intentionally remained
dry-run; 245 terminal candidates were explainable and eligible under the guarded
policy. This is a bounded-active-window claim, not a claim that dry-run storage
capacity is physically constant.

## Safety and recovery properties established through P07

- strict, memoized, and valid snapshot-plus-suffix replay agree; snapshot failure
  affects performance only and falls back to strict replay;
- snapshots become roots only through committed ancestry pins and never become a
  second mutable head;
- reachability explains every live or candidate object through typed roots/edges,
  including FWO/PFR lineage, equivalent loser grace, divergent evidence, response
  loss, capsules, snapshots, acknowledgements, pins, and quarantine;
- listing absence never proves unreachability, and unknown schemas are protected;
- real namespaces default to GC dry-run; destructive apply is synthetic-only
  without an explicit human gate and revalidates authority before deletion;
- partial delete and response loss recover by immutable request identity, with
  marker-last deletion order;
- exact capsules require model/frontier, inner optimizer, scheduler/scaler, RNG,
  data cursor, interval state, and compatible topology; incomplete state cannot be
  mislabeled exact;
- two independently validated snapshot bases survive newest-base corruption after
  compaction/GC;
- lease renewal continues during long lifecycle substages, and renewal/ownership
  failure prevents stale results from being used;
- active source, configuration, scripts, tests, and new artifacts contain no
  SQLite or replacement embedded database.

## Failure history and engineering lessons

The project has retained failed and inconclusive evidence rather than presenting
only successful runs. Recurrent lessons are now part of the operating contract:

1. Control-plane and runtime evidence must be separated. Miyabi login nodes are
   for static work and job submission; runtime validation belongs on PBS compute
   nodes.
2. A successful process exit is insufficient. Reports must assert optimizer
   transition count, authoritative stop, committed ancestry, participant topology,
   and evidence identities.
3. Reporting failures must not erase valid authority. The P07 D8 authority was
   complete even though the fixed report envelope failed; recovery used the raw
   authority and explicit schema validation.
4. Terminal retries are evidence-driven. After non-transient nine-node failures,
   the workflow preserved manifests and stage timings, wrote reviews, proved the
   repair on the smallest targeted benchmark, then repeated one-node and two-node
   qualification before one new nine-node attempt.
5. Leases must cover substages, not just outer loops. Replay, reachability, and
   lifecycle scans can grow beyond a nominal TTL, so the fenced owner needs a
   fail-closed renewal guard throughout long operations.
6. Marker-last publication and deletion grace are protocol requirements. Earlier
   cleanup races showed that directory appearance is not durable object identity.
7. Performance claims must retain negative results. P06C redundancy overhead and
   P07 lifecycle latency are inputs to optimization, not reasons to weaken safety.

## Current gaps and risks

P08 is the immediate gap. The current implementation still performs prototype
whole-model or repeated fragment copies in places, uses Python graph/replay paths
whose lifecycle time reached 141.89 seconds per late D8 cycle, and lacks the final
structured telemetry needed to reconstruct every publish/plan/prepare/commit/adopt
stage uniformly. Scanner work, validation reuse, CPU/NUMA placement, pinned-buffer
budgets, and learner GPU interference need matched measurement.

P08 must not assume bundling is beneficial. It first profiles direct fragment I/O,
streaming reduction, validation reuse, scanner bounds, and resource isolation. A
multi-FWO/one-CAS bundle is implemented only if a preregistered bottleneck gate
triggers and a new generation/schema proves canonical serial equivalence plus P07
reachability integration. Otherwise the bundle acceptances close as independently
justified `not_applicable`.

Later gaps are P10 storage-aware coordination, P11 formal Miyabi chaos and final
dedicated-syncer-free acceptance, and P12 experiments/artifact/paper evidence.
Algorithm-affecting adaptation cannot enter before fixed and shadow modes prove
the observation/controller boundary. Formal scientific claims require matched
baselines, raw immutable run IDs, analysis scripts, and preserved negative data.

## Authorized next route

The required route is now:

```text
P07 completed → P08 performance core → P10 SACC → P11 Miyabi acceptance → P12 evaluation
```

P08 should branch sequentially from the verified P07 implementation, begin with
an orientation/profile loop, and keep the complete P07 lifecycle test and Checker
contract as regressions. No merge to `main` is authorized by phase completion.
