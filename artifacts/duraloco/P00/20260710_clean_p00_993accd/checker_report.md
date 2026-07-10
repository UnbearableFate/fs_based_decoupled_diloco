# P00 Independent Checker Report

Verdict: PASS
required_gate_followups: none

## Review identity

- Checker: independent Codex checker agent `/root/p00_checker` (read-only)
- Reviewed implementation commit: `993accda722d5792fe687da2158365fbd353776d`
- Runtime job: `2357424.opbs`, `mg0026`, exit status 0, walltime 00:00:54
- Evidence root: `artifacts/duraloco/P00/20260710_clean_p00_993accd`

## Gate results

- The research contract defines global exact-prefix recovery, warm learner
  restart, capsule-dependent exact learner restart, logical exactly-once,
  the head-CAS commit point, and explicit non-claims.
- The inventory, drift report, migration map, numeric contract, failure model,
  invariant catalog, phase-state checker, evidence checker, and immutable run
  manifest are mutually consistent.
- All PBS scripts pass `bash -n`; the bundled plan and baseline configurations
  pass their SHA-256 checks; Python static compilation and contract/state
  checkers pass.
- The clean compute run passed 56 tests. The full smoke recorded 24 finite and
  zero non-finite loss events and preserved BASE-001 at committed version 1.
  The fragment smoke recorded 24 finite and zero non-finite loss events and
  completed at version 4. The representative legacy sample recorded 1,200
  finite and zero non-finite loss events.
- The final manifest is clean-tree, commit-bound, composite-config-bound,
  environment/nodefile-bound, and linked to the prior P00 attempt.

## Independent counterexamples and closed findings

The checker independently exercised/reviewed missing config binding, stale
bundle checksums, retry lineage, malformed/non-finite evidence, non-success
stop reasons, and illegal completed phase state. Findings about the initial
evidence parser, stale BASE-001 link/SHA, permissive null config, stale manifest
template, bundle checksum, and missing retry parent were fixed by the maker and
rechecked at the reviewed commit.

No required gate remains open. BASE-001 is a preserved legacy liveness/config
limitation and is not represented as Protocol v2 correctness evidence.
