# P00–P02 Work Report

Updated: 2026-07-10

## Result

**Overall goal: NOT PASS.** P00 and P01 are complete. P02 passes the maker's
clean compute suite, but has not passed the independent checker.

| Target | Status | Evidence |
|---|---|---|
| P00 baseline/research contract | DONE — PASS | commit `993accda722d5792fe687da2158365fbd353776d`; PBS `2357424.opbs` |
| P01 Protocol v2 | DONE — PASS | commit `cfa74423978fa5ff62ff112fbde980e223d00e92`; PBS `2357589.opbs` and checker `2357596.opbs` |
| P02 reference model | NOT DONE — CHECKER FAIL | maker commit `78bc733b01f7ffac68f93ffc2986c3e2dc81d207`; PBS `2357711.opbs`: 212 passed, 1 skipped |

## Work completed

- Added the P00 contracts, evidence/state validators, baseline artifacts, and
  Miyabi validation harness.
- Added strict immutable Protocol v2 schemas, canonical identities, payload
  validation, quarantine behavior, v1 inspection adapter, and negative tests.
- Added the P02 in-memory backend, deterministic transition/optimizer model,
  crash recovery, replay/minimization, randomized traces, five safety mutants,
  reference goldens, and compute-node tests.

## Why the goal does not pass

Independent checker PBS `2357714.opbs` found that `replay_trace` selects the
lexically first eligible proposal instead of using the frozen oldest-first
`select_quorum` policy. A newer same-lineage proposal can therefore commit
first and make the older proposal ineligible without an explicit supersession
decision. This violates D-0203 and makes the P02 randomized model-check evidence
incomplete.

Required next step: route trace commits through `select_quorum`, add the
adversarial regression, regenerate goldens, then rerun maker and checker jobs.
