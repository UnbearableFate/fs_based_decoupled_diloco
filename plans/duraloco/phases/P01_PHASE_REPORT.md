# P01 Phase Report

## Identity

- Phase: P01 — Protocol v2 schemas and validation
- Feature branch: `codex/duraloco-p01-protocol-v2`
- Base branch/commit: `codex/duraloco-p00-contract` @ `71fcae1b4d230a5a98ddb019f17b9f5009cde346`
- Final verified implementation commit: `cfa74423978fa5ff62ff112fbde980e223d00e92`
- Maker: Codex `/root`
- Checker: independent read-only Codex checker `/root/p00_checker`
- Status: `PASS`

## Scope completed

| Acceptance ID | Result | Evidence |
|---|---|---|
| P01-A01 | PASS | `tests/protocol/golden/`, `protocol_goldens.json`, canonical/round-trip tests |
| P01-A02 | PASS | `tests/protocol/test_validation_matrix.py`, clean pytest/JUnit evidence |
| P01-A03 | PASS | typed quarantine tests and independent checker counterexamples |
| P01-A04 | PASS | identity and same-session sequence conflict tests |
| P01-A05 | PASS | v1 read-only adapter tests and migration documentation |
| P01-A06 | PASS | canonical object-key and filename/listing-independence tests |
| P01-A07 | PASS | 162-test clean dependency-complete suite |
| P01-A08 | PASS | independent PBS counterexample suite and checker verdict |

## Changed files and behavior

P01 adds a standard-library Protocol v2 package with strict immutable schemas,
canonical JSON/content identities, layered metadata/causal/payload validation,
dependency-free safetensors verification, typed errors/quarantine, a read-only
v1 adapter and inspect CLI. Stable parameter-index and fragment-layout digest
APIs are additive. The legacy learner/syncer commit path remains the default.

## Compatibility and migration

No v1 authority is rewritten or mixed with v2. Conversion requires an explicit
new run/generation/model/index/layout context and produces an object only; the
adapter has no authority write capability. P01 does not implement or activate
head CAS.

## Verification

| Layer | Host/node | Command or job ID | Result | Artifact |
|---|---|---|---|---|
| Login static | `miyabi-g1` | py_compile, all PBS `bash -n`, plan SHA-256, research/state checkers | PASS | repository |
| Miyabi 1-node maker | `mg0033` | `2357589.opbs` | PASS; 162/162 | `artifacts/duraloco/P01/20260710_clean_p01_cfa7442` |
| Miyabi 1-node checker | `mg0041` | `2357596.opbs` | PASS; independent negative cases | `artifacts/duraloco/P01/20260710_checker_cfa7442` |
| Multi-node | — | not required | SKIPPED | P01 plan §9 |

## Faults and counterexamples exercised

The suite covers truncated/duplicate/deep/surrogate JSON, unknown/missing
fields, unhashable enum forms, future/stale/mismatched causal state, run/model/
index/layout mismatch, path aliases/escape/control characters, missing/racing
payload reads, size/hash/offset/key/shape/dtype errors, malformed/deep/non-finite
safetensors headers and values, sequence/identity conflict, repeated quarantine,
and legacy malformed/overflowing metadata.

## Checker findings

The checker found and the maker closed fail-open deep JSON/header, canonical
weight, partial eligibility, normalized path, exact base-frontier-version,
nested mutability, ObjectRef golden, byte-snapshot, surrogate, enum, fragment
key, and legacy-overflow gaps. Final maker and independent checker jobs passed.

## Open follow-ups

None for required P01 gates. Production storage immutability, head CAS, and
commit/recovery semantics begin in later phases.

## Research implications

- Claims supported: strict canonical input boundary, content identity,
  full-integrity eligibility, typed quarantine, and v1/v2 authority isolation.
- Claims not yet supported: transactional commit, prefix recovery, fencing,
  production performance, or multi-node training quality.
- Negative findings: several common host-language parser/container edge cases
  require explicit type/depth/scalar checks; relying on dataclass freezing or
  parser defaults is insufficient.

## Merge state

- Worktree clean at runtime: yes
- Branch pushed: yes
- Phase completed: yes; independent checker authorized `checking -> completed`
- Next phase automatically started: authorized immediately after this archival commit
- Ready to merge: no; feature branch only
- External-risk approval still required: none
