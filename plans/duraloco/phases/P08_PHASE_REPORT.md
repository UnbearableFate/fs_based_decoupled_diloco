# P08 Distributed Performance Core Report

## Current status

- Status: in progress, Loops 2–3 implementation
- Branch: `codex/duraloco-p08-distributed-performance`
- H0 runtime basis: `f167a07c49339ba42d14f8a5873fe2c8781884d4`
- H0 Checker basis: `04e0a8634b0e9d7c4cd55c5593081a0ca969a060`
- Actual branch base including the documentation rewrite: `8c12839a7b985e590378ac593c846f07b0637517`
- Instrumentation commit: `fcbbfa17e91fc1eb9cdd90b3d3ea40aea3c79705`
- Login-node static checks: PASS (`bash -n`, ruff, phase-state contract, diff check)
- Runtime checks: not run; current shell is Miyabi login/control plane

## Orientation and frozen decisions

The active contract is
`plans/duraloco_claude_forward_plans/01_P08_DISTRIBUTED_PERFORMANCE_CORE.md`,
including its additional D-0800 and P08-A25 requirements. D-0800 through
D-0810 are now recorded in `plans/duraloco/DECISIONS.md` before runtime work.
The phase retains one global head, strict ownership-bound replay, typed P07
lifecycle edges, factor-one/R2 exact same-backend semantics, and telemetry that
cannot participate in authority.

The bundle gate is preregistered but unresolved: it requires at least 8/10
transitions with serialization wait at least 25% of the critical path and a
measured two-FWO projection of at least 15% end-to-end improvement. Until real
matched D8 evidence crosses both thresholds, no bundle schema will be added.

D-0800 preserves H0 truthful error-stop behavior and chooses a fenced `resume`
control transition in a fresh v2 coordination-protocol generation. The resume
path is limited to a parent whose authoritative stop reason is exactly
`error`; normal terminal stops remain irreversible.

## Acceptance tracking

P08-A01 through P08-A25 are all `not_run`. No implementation or performance
claim is considered passed during orientation. Evidence will be added only
after RED/GREEN tests and PBS compute-node runs complete.

## Failures and experiments

The first targeted submission, PBS `2369958.opbs`, failed before project
runtime because `EXPECTED_COMMIT` was manually transcribed with the wrong full
hash. It ran for one second, changed no authority, and produced no test/profile
result. The PBS output, host/module context and scheduler trace are preserved
as P08-E001. The wrapper now installs its immutable-manifest EXIT trap before
the identity check, and the retry derives the exact hash from `git rev-parse`
instead of retyping it.

The corrected-wrapper attempt `2369961.opbs` entered the compute runtime. One
recorder-failure isolation test passed and three RED event/summary tests failed
before the benchmark: `StageEventV1.create` hashed optional fields encoded as
`null`, while the canonical round trip omitted absent fields. P08-E002 retains
the manifest/stdout/qstat evidence. The implementation now applies the frozen
canonical-omission rule before computing observational event identity; no
authority object or training run was created.

PBS `2370055.opbs` then passed all four telemetry contract tests but failed
before profiling because the benchmark was invoked by file path and therefore
could not import the repository package. P08-E003 preserves the passing test
output and failed manifest. The harness is now a module entry point
(`python -m benchmarks.bench_lfe_pipeline`) from the project root.

All later failed, inconclusive, cancelled, superseded, and passing runs will be
preserved in `plans/duraloco/errors/P08_ERROR_LEDGER.yaml` and the phase report
rather than replaced by the final result.

PBS `2370057.opbs` passed the corrected one-node telemetry contract (4/4) and
persisted the H0-style materialized-LFE baseline. For 16 MiB fragments and
quorum 1/2/4/8, materialized proposal residency was 16/32/64/128 MiB, peak RSS
was 585,105,408 / 603,979,776 / 660,602,880 / 1,203,240,960 bytes, and minimum
reduction times were 1.95/2.89/4.90/9.01 ms. This is baseline evidence, not an
optimized-path acceptance pass. Its immutable manifest and raw JSON are under
`artifacts/duraloco/P08/20260713_p08_profile_d97d914_1node_r3/`.

The login-node phase-state validation was initially invoked with a nonexistent
`--phase` option and then exposed that the first P08 phase-state draft used the
documentation-oriented schema instead of the executable checker schema. No
runtime or authority was touched. The state file was rewritten to the canonical
25-acceptance contract and is now validated with its positional path.

Loops 2–3 now have a login-statically-clean candidate implementation: canonical
direct fragment gather/scatter and learner single-copy authority publication;
one-proposal-at-a-time float32 reduction; head/epoch/owner-scoped digest-only
validation tokens; cheap causal rejection; reconstructible discovery cursors;
POSIX envelope-v2 chunk digests with seek-based range reads and v1 fallback;
replay-maintained lineage maps; cadence-gated full materialization and unchanged
fragment reuse; and parent-directory fsync for derived sidecars. Loop 4 has an
explicit one-in-flight/thread/RSS/prefetch budget plus actual affinity, NUMA and
Torch-thread evidence bound into each attempt. D-0800 is implemented as the
fresh-generation `distributed-head-fenced-error-resume-v2` control path.

These implementation claims are not acceptance results yet. They have passed
only login-safe ruff, shell syntax, diff, and phase-state checks; all Torch,
storage runtime, replay, lifecycle, numeric, memory, and resume tests await the
next one-node PBS compute qualification.

The first optimized qualification, PBS `2370192.opbs` at commit `360f2ac`,
failed with 102 tests passing and one RED counterexample: scattering into a
non-contiguous parameter used `reshape(-1)`, which produced a temporary copy,
so the parameter itself stayed unchanged. The EXIT trap also failed to create
its automatic manifest because the script used unsupported purpose
`qualification`; a complete failure manifest was reconstructed immediately
with the supported `contract` purpose and the compute-node/job facts. The
repair explicitly copies the logically flattened update back into the shaped
non-contiguous parameter and fixes the manifest purpose before the retry.

PBS `2370205.opbs` confirmed that repair: all 103 focused tests passed. It then
failed before producing the optimized profile because importing the benchmark
as the first package consumer exposed a circular runtime type import between
`optimizer.reference_adapter` and `log.commit`. The package test order had
masked it. P08-E007 preserves the automatic manifest and raw traceback. The
type-only `ReferenceProposal` dependency is now guarded by `TYPE_CHECKING`, and
the optimizer package exports are consolidated before the exact same targeted
retry.

PBS `2370206.opbs` passed the corrected optimized one-node gate: 103 focused
tests, zero forbidden active database findings, and the streaming profile all
passed at clean commit `86b77d4`. For a 16 MiB fragment the hard peak working
set was exactly 32 MiB for q=1/2/4/8, while process peak RSS stayed 537,919,488
bytes across all four cases. At q=8 the minimum reduction time was 8.60 ms,
versus 9.01 ms and 1,203,240,960-byte peak RSS in the earlier materialized
baseline. This closes the focused equivalence/memory/cache/range/cancellation
contracts, but is not D1/D2 or matched GPU-interference evidence.

The first full-regression submission was rejected before allocation because its
35-minute request exceeded the `debug-g` queue limit. It received no PBS job
ID, ran no command, and touched no authority. P08-E009 records the operator
submission failure; the wrapper now requests the queue-supported 30 minutes.

PBS `2370232.opbs` then passed the full one-node gate at clean commit
`c3d5666`: 489 tests passed, one was intentionally skipped, ruff and both P08
state contracts passed, and the forbidden-surface scan found zero active
database references. While preparing D1, the stage instrumentation was also
hardened so discovery/validation spans receive the derived work-order identity
once the canonical order is built; this prevents real traces from being
complete in aggregate but unjoinable per FWO.

PBS `2370248.opbs`, the first real P08 D1 run, failed before FWO publication.
The learner correctly wrote one authority payload whose sidecar carried the
backend's immutable version token. `publish_validated_proposal_reference`
compared that complete observed ObjectRef with a canonical manifest identity
whose optional version is absent, so otherwise identical key/size/SHA fields
were rejected. The v2 committer truthfully committed an `error` stop at
sequence 2; no optimizer transition occurred. The repair separates canonical
content identity from the optional observation version, while requiring any
supplied version to equal a fresh authoritative `head` observation.

The same-commit retry ladder passed. PBS `2370266.opbs` reran all 103 focused
tests plus the flat-working-set benchmark at commit `b1ff147`. PBS
`2370269.opbs` then passed real GPT-2/WikiText D1: one v2 optimizer transition,
one complete joinable work-order timeline, one global head, learner
publish/adopt lineage, no mailbox tensor copies, and zero forbidden database
findings. The LFE was actually pinned to CPUs 64–71 with 8 Torch threads,
NUMA allowance `0-1`, one in-flight proposal, and 6,339,821,568-byte peak RSS
under the 16 GiB ceiling. The learner was pinned away from those eight CPUs.

PBS `2370306.opbs` proved the authoritative half of D-0800: factor-two exact
duplicates committed transition 1, an injected committer exception committed a
truthful error stop, member 001 waited out the observational lease, and a
`resume` control transition advanced the fence from 1 to 2 without changing
optimizer count. It then committed transition 2. The job failed when the host
harness restarted learners under their old immutable session with sequence 1;
marker-last publication correctly rejected the conflicting request key. The
repair does not weaken identity. Recoverable v2 errors now use a distinct
derived `recoverable_error.json` observation rather than terminal `stop.json`,
so existing learner/LFE sessions stay alive across the fenced outage. Normal
stops remain terminal and unchanged.
