# P00–P02 Work Report

Updated: 2026-07-11

## Result

**Overall P00–P02 status: CHECKING.** P00 and P01 are complete. P02 passed the
maker and independent checker and is awaiting its archival completion commit.

| Target | Status | Evidence |
|---|---|---|
| P00 baseline/research contract | DONE — PASS | commit `993accda722d5792fe687da2158365fbd353776d`; PBS `2357424.opbs` |
| P01 Protocol v2 | DONE — PASS | commit `cfa74423978fa5ff62ff112fbde980e223d00e92`; PBS `2357589.opbs` and checker `2357596.opbs` |
| P02 reference model | CHECKING — PASS | implementation `7e12997ca0a9fe4e48bb96cfe6391e0e8d1bf773`; maker `2357761.opbs`; checker `2357765.opbs` |

## Work completed

- Added the P00 contracts, evidence/state validators, baseline artifacts, and
  Miyabi validation harness.
- Added strict immutable Protocol v2 schemas, canonical identities, payload
  validation, quarantine behavior, v1 inspection adapter, and negative tests.
- Added the P02 in-memory backend, deterministic transition/optimizer model,
  crash recovery, replay/minimization, randomized traces, five safety mutants,
  reference goldens, and compute-node tests.

## Remaining action

The PBS `2357714.opbs` oldest-first failure was fixed and independently
rechecked. P02 still needs its persisted `checking -> completed` audit and the
required milestone archival Git commit before P03 starts.
