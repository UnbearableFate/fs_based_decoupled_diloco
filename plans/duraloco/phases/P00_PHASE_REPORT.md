# P00 Phase Report

## Identity

- Phase: P00 — Baseline and research contract
- Feature branch: `codex/duraloco-p00-contract`
- Base commit: `afc50a1e179c64321645b278b2497ea3ab3fe24d`
- Final verified implementation commit: `993accda722d5792fe687da2158365fbd353776d`
- Maker: Codex `/root`
- Checker: independent read-only Codex checker `/root/p00_checker`
- Status: `PASS`

## Scope completed

| Acceptance ID | Result | Evidence |
|---|---|---|
| P00-A01 | PASS | `docs/duraloco/baseline_inventory.md`, `docs/duraloco/migration_map.md` |
| P00-A02 | PASS | `docs/duraloco/research_contract.md`, `docs/duraloco/failure_model.md`, `docs/duraloco/numeric_contract.md` |
| P00-A03 | PASS | `docs/duraloco/invariants.md`, `plans/duraloco/TRACEABILITY.md` |
| P00-A04 | PASS | `scripts/agent/check_phase_state.py`, `tests/test_agent_state_contract.py` |
| P00-A05 | PASS | clean compute artifact root and `docs/duraloco/baseline_limitations.md` |
| P00-A06 | PASS | compatibility tests plus baseline manifest at planning commit; no legacy runtime default was switched |
| P00-A07 | PASS | `checker_report.md` in the clean compute artifact root |
| P00-A08 | PASS | independent checker verdict `PASS`; automatic P01 progression is authorized |

## Changed files and behavior

P00 adds research/failure/numeric contracts, the invariant and traceability
catalogs, baseline/drift/migration inventories, persisted phase state, evidence
and manifest validators, counterexample tests, and a one-node PBS baseline
harness. Legacy learner, syncer, selection, merge, resume, and retention
defaults are unchanged.

## Compatibility and migration

The observed planning-basis worktree is preserved before the contract changes.
Protocol v1 evidence remains observational and is not upgraded to v2 authority.
P01/P02 are additive feature-branch work and do not activate a production
commit path.

## Verification

| Layer | Host/node | Command or job ID | Result | Artifact |
|---|---|---|---|---|
| Login static | `miyabi-g1` | `py_compile`, `bash -n scripts/miyabi/*.pbs`, plan/config `sha256sum -c`, contract/state checkers | PASS | repository files |
| Miyabi 1-node | `mg0026` | `2357424.opbs` | PASS; 56 tests, two tiny smokes, representative legacy sample | `artifacts/duraloco/P00/20260710_clean_p00_993accd` |
| Miyabi 2-node | — | not required by P00 | SKIPPED | phase plan §9 |
| Miyabi 9-node | — | prohibited/not required by P00 | SKIPPED | phase plan §9 |

## Faults and counterexamples exercised

Dirty planning basis, branch drift, missing config/script, null or mutated run
manifest binding, missing evidence, non-finite/malformed logs, missing required
events, non-success stop reasons, and illegal phase completion/transitions are
covered. The independent checker also caught stale evidence references,
template/checksum drift, and missing retry lineage before the final clean run.

## Checker findings

All findings were closed and rechecked. Structured verdict: `PASS` with no
required gate follow-ups.

## Open follow-ups

BASE-001 remains a documented legacy tiny full-vector liveness/configuration
limitation outside P00–P02. It does not block fragment baseline completion or
the additive Protocol v2 work.

## Research implications

- Claims supported: frozen terminology, authority/commit point, failure model,
  recovery levels, exactly-once definition, numeric contract, and reproducible
  legacy baseline evidence.
- Claims not yet supported: Protocol v2 crash consistency, production recovery,
  multi-node scalability, and training-quality conclusions.
- Negative finding: the legacy full-vector tiny configuration can exhaust all
  local steps and stop at version 1 through `no_progress_timeout`.

## Merge state

- Worktree clean at runtime: yes
- Branch pushed: yes
- Phase completed: yes; independent checker authorized `checking -> completed`
- Next phase automatically started: authorized immediately after this archival commit
- Ready to merge: no; feature branch only
- External-risk approval still required: none
