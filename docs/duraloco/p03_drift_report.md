# P03 Baseline Drift Report

- Planning basis: `codex/fs-diloco-miyabi` at
  `afc50a1e179c64321645b278b2497ea3ab3fe24d`
- Actual base: `codex/duraloco-p02-reference-model` at
  `5f03afae833712706814a9c295970a5800a8f04e`
- Reason: P00–P02 were completed as required dependencies before P03.
- Preserved additions: Protocol v2 schemas/validation, the in-memory semantic
  backend, deterministic reference model, crash/model checker, phase-state
  validators, and bilingual milestone reporting.
- Compatibility rule: P03 extends the semantic backend additively. It does not
  switch the legacy learner/syncer runtime or rewrite Protocol v1 authority.
- Validation impact: P03 must run its conformance suite against both the P02
  memory backend and the new POSIX backend, then validate Lustre on one and two
  Miyabi compute nodes.
