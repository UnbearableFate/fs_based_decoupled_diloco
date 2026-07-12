# P08 Distributed Performance Core Report

## Current status

- Status: in progress, Loop 1 orientation
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

All later failed, inconclusive, cancelled, superseded, and passing runs will be
preserved in `plans/duraloco/errors/P08_ERROR_LEDGER.yaml` and the phase report
rather than replaced by the final result.

The first compute action is the one-node targeted telemetry/materialized-LFE
profile in `scripts/miyabi/run_duraloco_p08_profile_1node.pbs`; its test and
benchmark have not been executed on the login node.
