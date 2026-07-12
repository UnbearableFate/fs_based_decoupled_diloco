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

PBS `2370326.opbs` validated that repair end to end: workers retained their
immutable sessions, member 001 resumed under fence 2, and four factor-two
transitions each produced two exact attempts before the normal terminal stop.
The runtime completed correctly, but the post-run report asserted three
transitions even though the frozen tiny config specifies four. P08-E015 records
this analysis-harness failure; the expected work-order/attempt cardinalities
are corrected to four without changing runtime semantics.

The first submission of that corrected commit, PBS `2370338.opbs`, omitted the
required `STORAGE_ROOT` qsub variable. Strict wrapper validation rejected the
job before artifact setup, runtime, or authority access. P08-E016 preserves the
operator error and requires the next submission to name a unique shared Lustre
root explicitly.

The corrected clean ladder then passed. PBS `2370343.opbs` reran the 104-test
focused one-node gate and flat-working-set benchmark at commit `f3986b8`. PBS
`2370347.opbs` passed D2-R2: four optimizer transitions, four complete
work-order timelines, and exactly two successful attempts per work order. The
injected committer exception produced an error stop at fence 1; member 001
resumed at fence 2 without an intervening optimizer transition, and the run
ended normally at commit sequence 8. This closes P08-A14, P08-A20, and P08-A24.

The final D8 ladder is now specified on one clean commit. A nine-node no-LFE
shadow, nine-node allocation with eight factor-one learner/LFE hosts, and the
matched D8-R2 run all bind the same GPT-2/WikiText-2 50x10 config and seed.
Learners are isolated from the eight audited LFE CPUs on each host. D8-R2 uses
the D-0813 controlled executor exception so the failed canonical attempt has a
flushed terminal stage before the process restarts and the backup activates.
The D-0814 report computes D-0807 only from same-committer causal durations and
an optimistic E2E upper bound, then charges the measured R2 learner slowdown.
No bundle schema or authority object is created by the gate evaluator.
The final one-node gate also pairs real streaming reductions with and without
the asynchronous recorder, includes recorder drain time, requires identical
numeric output and complete health, and enforces D-0806's two-percent wall-time
overhead ceiling before any matched nine-node submission.

The first final one-node allocation, PBS `2370427.opbs`, never entered the
wrapper. PBS retained mg0023 in running substate 41 for 281 seconds with unset
elapsed time and no stdout or artifact directory. It was cancelled as an
infrastructure prologue stall. P08-E017 records the zero-authority, zero-runtime
attempt; no source change is attributed to it.

The replacement targeted gate passed, including 110 focused tests and a
0.303% recorder overhead measurement with 160 fully flushed events. The first
full gate, PBS `2370446.opbs`, then passed 494 tests with one skip before a
legacy minimal committer test double exposed an unconditional `log.spec`
lookup in the new error-resume finalizer. P08-E018 records the unit-only
failure. Production logs always carry a RunSpec; the repair keeps exact
protocol matching there while treating an absent optional test-adapter spec as
the legacy non-error-resume path.

The corrected clean one-node targeted/full gates and D2 qualification passed
as PBS `2370452`, `2370455`, and `2370461`. The first matched nine-node no-LFE
shadow, PBS `2370465`, then exposed a non-transient centralized-syncer lease
failure after four optimizer transitions. Successor preparation and post-CAS
replay grew from 4.408/6.221 seconds to 19.073/21.130 seconds; the last complete
loop occupied 49.023 seconds after renewal and exceeded the 45-second TTL.
P08-E019 and `P08_9NODE_FAILURE_REVIEW_2370465.md` preserve the terminal error
head, raw stages, root cause, repair, and mandatory targeted → one-node →
two-node qualification before exactly one fresh C9 retry.

That repair and its same-commit qualification passed, and PBS `2370521`
completed all ten optimizer transitions with 45 long-substage heartbeats and a
normal terminal. Acceptance still fails closed: the terminal convenience path
spent 101.495 seconds preparing and replaying the stop with no renewal directly
before its CAS. P08-E020 and `P08_9NODE_FAILURE_REVIEW_2370521.md` therefore
classify the manifest-level pass as inconclusive. D-0816 splits terminal stop
into guarded preparation, a final renewal, caller-thread CAS, and guarded
post-CAS replay before one newly qualified C9 attempt.

The final guarded C9 run, PBS `2370616`, passed ten transitions in 836 seconds;
its 99.993-second terminal stage retained four stop-prepare and four post-CAS
replay heartbeats with a final renewal before CAS. PBS `2370677` then exposed
the same missing guard in the distributed factor-one path: publish-to-commit
grew to 52.292 seconds by transition four because only executor wait, not
winner validation, successor preparation, or replay, renewed the lease.
P08-E021 and `P08_9NODE_FAILURE_REVIEW_2370677.md` preserve the error terminal,
causal timings, repair, and mandatory requalification before one D8 retry.
PBS `2370680` also overlapped that job under the same caller-supplied namespace;
P08-E022 rejects the contaminated namespace and D-0818 adds atomic root claims.
P08-E023 separately retains the immediately terminated login-node Python/torch
diagnostic mistake. Neither incident supplies performance evidence.

After clean requalification and matched C9 pass, PBS `2370782` completed ten
guarded factor-one transitions and a normal terminal. The runtime stayed within
its 25-minute P08 allocation, but the inherited P06B reporter rejected its
17:41 wall time against an obsolete 900-second phase ceiling. P08-E024 and
`P08_9NODE_FAILURE_REVIEW_2370782.md` preserve the successful runtime and
post-run failure. The reporter now retains 900 seconds by default for P06B and
accepts an explicit 1500-second P08 envelope. This changes report admission,
not the measured 17:41 runtime or its interpretation. Duplicate PBS `2370787`
was rejected by D-0818's atomic namespace claim before runtime or authority
access and is preserved as P08-E025.

The mandatory smallest recovery proof passed on PBS `2370861` at clean commit
`c76501f`. On one compute node it replayed the preserved `2370782` authority
read-only, accepted the measured 1061 seconds only under P08's explicit
1500-second envelope, and generated both the legacy base report and the full
P08 factor-one report. The latter independently confirmed ten transitions,
all optimizer/terminal lease guards, complete raw stage timelines, and a 3.74%
optimistic two-FWO end-to-end upper bound. This is repair evidence, not a
replacement matched final run.

The final same-commit C9 and factor-one reruns then passed at runtime commit
`067d33be79d9dbe63e4a31056e35e96ee525cb1f`. PBS `2370890` completed the
no-LFE shadow in 831 seconds with 440 GPU-step samples (mean 0.0259766 s) and
five heartbeats in each terminal prepare/replay substage. PBS `2370892`
completed factor one in 952 seconds with 440 samples (mean 0.0262335 s), ten
optimizer-CAS renewals, one stop-CAS renewal, 23 successor-prepare and 25
post-CAS-replay heartbeats, and zero lease-authority-loss events. Both bind the
same config digest, model/dataset revisions, seed, nine-node allocation, and
eight learner nodes.

The first R2 submission command was rejected before allocation because its six
shell-local bindings were named rather than passed as explicit `KEY=VALUE`
pairs; P08-E026 records that zero-runtime operator error. The corrected command
created PBS `2370941`. Its runtime reached ten factor-two transitions after one
controlled pre-publication executor failure and ended normally. The post-run
report then failed: it incorrectly required factor-one's ten prepared results,
where the frozen R2 shape correctly contains twenty terminal attempts,
nineteen successful prepared results, and one terminal loser. P08-E027 and
`P08_9NODE_FAILURE_REVIEW_2370941.md` preserve the raw evidence and mandatory
recovery ladder. No fresh R2 may run until the corrected cardinality checker
passes preserved-run compute recovery, one-node qualification, and two-node
qualification on one clean commit.

The first preserved-run proof, PBS `2370998`, passed all four new attempt-
lineage tests but exposed a second report-only assumption: it required every
named guarded substage to emit at least one timeout heartbeat. R2 successor and
terminal preparation completed inside their renewal interval, so zero timeout
heartbeats is the truthful result. P08-E028 retains the failed proof. The guard
audit now requires the ten optimizer-CAS and one stop-CAS renewals, exact
one-to-one lifecycle renewal/heartbeat accounting, at least one observed long-
substage renewal elsewhere in the run, and zero authority-loss events; it does
not fabricate a heartbeat for a fast future.

PBS `2371021` then passed the five corrected reporter tests and produced the
complete R2, matched-interference, and D-0807 gate reports. Its final P07
lifecycle report rejected a 72-object effective-live tail delta against P07's
fixed 64-object default. The raw curve is linear and reclaimable, not leaking:
effective live counts are 229/265/301 while candidates grow 120/182/244. P08's
typed factor-two attempt/resource evidence adds eight live objects per cadence
relative to P07, or sixteen across the three-point/two-interval tail. D-0820
therefore preserves the P07 default and binds only P08 R2 to an explicit
80-object budget. P08-E029 preserves this read-only failed proof; deletion
remains dry-run and no authority semantics changed.
