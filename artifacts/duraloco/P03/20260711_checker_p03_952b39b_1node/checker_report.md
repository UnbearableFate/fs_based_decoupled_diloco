# P03 Independent Checker Report

## Verdict

**PASS**

Verdict: PASS
required_gate_followups: none

- Target: `952b39b5fef0fc06e4d28d75bbded24baa5f655f`
- Base: `5f03afae833712706814a9c295970a5800a8f04e`
- Feature branch: `codex/duraloco-p03-posix-storage`
- Review mode: independent read-only diff/spec audit plus PBS compute-node counterexamples
- Required-gate findings remaining: none

The implementation satisfies P03-A01 through P03-A08 and the frozen
D-0301 through D-0305 decisions. Earlier checker failures were reproduced,
fixed by the Maker, and independently rerun on the target commit.

## Acceptance audit

| Acceptance | Result | Independent basis and evidence |
|---|---|---|
| P03-A01 | PASS | Maker PBS `2357905.opbs` on `mg0003` ran the shared memory/POSIX suite as part of `246 passed, 1 skipped`; the only skip was the explicitly nightly 10,000-trace P02 suite. Manifest: `artifacts/duraloco/P03/20260711_clean_p03_952b39b_1node/manifest.json`. |
| P03-A02 | PASS | The clean capability operation trace records create, idempotent replay, and `immutable_conflict`; the reusable conformance suite and independent checker matrix also detected a different-bytes conflict. |
| P03-A03 | PASS | Maker PBS `2357912.opbs` on `mg0025` and `mg0026` completed 100 same-version Lustre races with zero double winners and zero visibility failures. Independent PBS `2357913.opbs` additionally raced eight clients with identical payloads and distinct request IDs: exactly one returned success. |
| P03-A04 | PASS | Independent delayed-list omission returned an empty listing while direct `head`, CAS, and version-checked `get` continued to succeed. Evidence: `artifacts/duraloco/P03/20260711_checker_p03_0a4896e_1node/checker_952b39b_results.json`. |
| P03-A05 | PASS | Clean capability report records `directory_fsync=true`, filesystem ID/block size, and the real operation trace; the run preserves Lustre mount and stripe observations. Independent audit-mode downgrade reported `directory_fsync=false`, while required mode and `require_capabilities` both failed closed. Durability documentation remains scoped to the declared failure model. |
| P03-A06 | PASS | Seed `20260711` serialized/replayed to the same schedule and digest `0310b07c79c79ed315275cdc3e265c6c4b91e0e0d3f44ad22aaebce74f505601`; after-effect retry is bound to an explicit persisted request ID. |
| P03-A07 | PASS | Diff audit found no changes to the legacy learner, syncer, config, or `atomic_io` runtime paths and no default reference to the POSIX backend. The compatibility regression passed in the clean suite. |
| P03-A08 | PASS | Independent PBS `2357913.opbs` killed CAS writers at all six publication hooks and observed a fully verified old object before publish or new object after publish; dead lock-owner exit was followed by successful takeover. Independent PBS `2357909.opbs` covered temp/lock infrastructure failure windows and typed retry classification. Raw results are under `artifacts/duraloco/P03/20260711_checker_p03_0a4896e_1node/`. |

## Frozen-decision audit

- D-0301: payload, random version, predecessor, request ID, size, hash, and
  header checksum share one envelope. Same-key mutation uses a stable
  SHA-256 lock inode, same-directory temp, file fsync, atomic link/replace,
  and parent fsync. A same-ID lost-response retry returns the original version;
  distinct or absent IDs do not turn an independent stale call into success.
- D-0302: directory fsync is probed and recorded. Required mode fails closed;
  audit-only mode exposes the downgrade without claiming durability.
- D-0303: `get`, `head`, and `range_get` all parse and verify the complete
  envelope. The independent truncation matrix raised `IntegrityError` for all
  three read forms.
- D-0304: canonical relative keys and the reserved namespace are enforced;
  the independent pre-existing symlink traversal case was rejected without an
  outside write.
- D-0305: missing/conflict/integrity errors are typed. On the final target,
  injected EIO/ESTALE are retryable `StorageIOError`; EACCES, ENOSPC, and
  EDQUOT are non-retryable `StorageIOError` across temp creation and lock
  acquisition. A real read-only parent was also translated correctly.

## Lock/CAS failure-window evidence

Independent PBS `2357913.opbs` on `mg0027` produced:

| Exit hook | Verified visible value |
|---|---|
| `after_temp_write` | old |
| `after_file_fsync` | old |
| `before_publish` | old |
| `after_publish` | new |
| `before_parent_fsync` | new |
| `after_parent_fsync` | new |

The same run passed dead-owner lock takeover, request-ID retry disambiguation,
listing independence, verified-read corruption detection, capability
downgrade, key containment, immutable conflict, and deterministic fault replay.

Independent PBS `2357909.opbs` on `mg0003` reran the exact previously failing
infrastructure-error matrix. It translated:

- temp creation: EIO, ESTALE, EACCES, ENOSPC, and EDQUOT;
- lock acquisition: EIO, ESTALE, and EACCES;
- real read-only parent: EACCES.

All classifications and retry flags matched D-0305.

## Maker evidence audit

- One node: `artifacts/duraloco/P03/20260711_clean_p03_952b39b_1node`
  - PBS `2357905.opbs`, host `mg0003`, manifest exit 0.
  - `246 passed, 1 skipped in 16.80s`.
  - Capability probe passed on Lustre with directory fsync observed.
- Two nodes: `artifacts/duraloco/P03/20260711_clean_p03_952b39b_2node`
  - PBS `2357912.opbs`, hosts `mg0025` and `mg0026`, manifest exit 0.
  - 100 races, zero double winners, zero visibility failures, stale-lock
    takeover passed; winner counts were 93 and 7.
  - Per-rank semantic traces contain 1,907 and 1,007 records.
- Static: final worktree was clean/detached at the target and all
  `scripts/miyabi/*.pbs` passed `bash -n`.

## Resolved checker findings

1. At `bfe2fb5`/`6dc7392`, independent identical-input clients could all be
   classified as after-effect retries. Commit `0a4896e` added a persisted
   explicit request ID. Independent PBS `2357892.opbs` and final rerun
   `2357913.opbs` proved exactly one distinct-request winner.
2. At `0a4896e`, temp creation and flock setup leaked raw OS errors. Commit
   `952b39b` translated setup/publication/lock failures. The exact failing
   matrix from PBS `2357895.opbs` passed on final PBS `2357909.opbs`.

## Scope and follow-ups

No required-gate follow-up remains. The PASS does not extend the documented
durability claim to permanent provider loss, controller failure, or every
parallel-filesystem failure mode, and it does not activate the new backend as
the legacy runtime default.
