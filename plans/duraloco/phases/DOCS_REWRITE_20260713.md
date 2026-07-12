# Documentation Rewrite Record — 2026-07-13

## Status

- State: completed
- Scope: rewrite current `README.md` and `docs/` against the H0-qualified codebase
- Runtime behavior changed: no
- PBS experiment submitted: no; documentation/static-tool-only change on Miyabi login node
- Runtime evidence reused: H0 runtime `f167a07c49339ba42d14f8a5873fe2c8781884d4`, checker
  `04e0a8634b0e9d7c4cd55c5593081a0ca969a060`

## Changes

- Replaced the central-syncer-era README and duplicate bilingual guides with a single current Chinese
  documentation tree.
- Added current status, architecture, lifecycle, user quickstart/configuration/operations, and a documentation
  validity policy.
- Rewrote Protocol v2, research, storage, transaction, failure, numeric, invariant, reference, migration, and
  review documents to distinguish implemented guarantees from P08/P11 roadmap work.
- Retained P00 baseline inventory/limitations only as explicitly historical evidence.
- Retired obsolete design, experiment, Miyabi runbook, numbered user guide, and temporary drift files.
- Added `scripts/agent/check_docs.py` and moved the forbidden embedded-database audit to the new active docs.
- Corrected the stale top-level blocker summary to reflect completed P07/H0 and the qualified P08 handoff.

## Experiment and failure record

No runtime experiment was authorized or needed for a documentation-only change. No training, torch import,
pytest runtime, MPI, model loading, or CUDA check was run on the login node. Static validation results and any
failure/correction will be appended below before completion.

## Static validation

All login-node-safe checks passed after the rewrite:

- `bash -n scripts/miyabi/*.pbs scripts/miyabi/*.sh scripts/local/*.sh`
- `.venv/bin/ruff check fs_diloco tests scripts/agent`
- `scripts/agent/check_docs.py --root "$PWD"`
- `scripts/agent/check_research_contract.py --root "$PWD"`
- `scripts/agent/check_no_embedded_database.py --root "$PWD"` (349 active files, zero findings)
- `scripts/agent/check_phase_state.py plans/duraloco/STATE.yaml`
- `git diff --check`

The first static pass had no failure. `check_docs.py` was then hardened to audit local links in every retained
Markdown document while applying stale-current-claim rules only to active documents; the hardened rerun also
passed. Runtime checks remain deliberately not run because this change does not alter runtime behavior and the
current shell is a Miyabi login node.
