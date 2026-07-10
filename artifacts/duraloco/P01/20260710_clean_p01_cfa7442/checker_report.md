# P01 Independent Checker Report

Verdict: PASS
required_gate_followups: none

## Review identity

- Checker: independent Codex checker agent `/root/p00_checker` (read-only maker tree)
- Reviewed implementation commit: `cfa74423978fa5ff62ff112fbde980e223d00e92`
- Maker runtime: `2357589.opbs` on `mg0033`, exit 0, 162/162 tests
- Independent counterexample runtime: `2357596.opbs` on `mg0041`, exit 0
- Evidence: `artifacts/duraloco/P01/20260710_clean_p01_cfa7442` and
  `artifacts/duraloco/P01/20260710_checker_cfa7442`

## Gate results

- Proposal, ObjectRef, Commit, Frontier, Head, and DropDecision have strict
  schemas, canonical encoding, and cross-process golden digests.
- Future/stale and inconsistent causal bases, path aliases/escapes, wrong
  size/hash/key/shape/dtype, non-finite tensors, malformed JSON/safetensors,
  identity conflicts, and incomplete validation levels fail closed.
- Only full payload verification with a full finite scan produces
  `eligible=true`; metadata-only and finite-disabled reports are explicit,
  non-eligible diagnostic results.
- Nested authority and audit mappings are copied and deeply/read-only frozen.
  Payload size/hash/tensor parsing uses one immutable byte snapshot.
- The v1 adapter is read-only and cannot write Protocol v2 authority.
- The full dependency-complete suite passed without legacy regressions.

## Independent negative cases

The independent checker exercised unhashable manifest types, NFC-normalized key
collisions, invalid UTF-8, noncanonical weights, impossible
commit/frontier/fragment-version pairings, non-finite tensors, normalized-path
aliases, deep safetensors metadata, legacy numeric overflow, and
identity/content conflict. All produced the required typed outcome without
escaping the scanner boundary.

No required P01 gate remains open.
