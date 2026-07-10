# P04 Independent Checker Report — Attempt 1

Verdict: BLOCKED
required_gate_followups: current-log-suite-green; parent-linked-clean-reruns
P04-A09: PASS
checking_to_completed: DENIED

## Review identity

- Persistence commit: `2db8a731e356f99d3c243a302674d94c8721e3c6`
- Verified implementation: `79373ecab4e051b4c9ff2ba128250d8612b9ab8b`
- Branch: `codex/duraloco-p04-transaction-log`
- Independent PBS: `2358154.opbs` on `mg0011`

## One-CAS proof result

P04-A09 passes at the verified implementation. Static audit found one
transaction mutation call, `conditional_replace(control/head.json)`, in
`TransactionalLog.commit_prepared`. Immutable proposal, params, outer-state,
commit, and frontier publication does not change authority. Replay begins at
the checksum-verified head/frontier and verifies the parent chain, content-ID
commit records, proposal identities, oracle outputs, cumulative consumption,
and paired fragment/outer-state refs.

Independent compute counterexamples all passed:

- a lost head-CAS response retried after a successor commit returned
  `already_committed` without issuing another CAS;
- two identical writers produced one logical commit, one proposal inclusion,
  and one CAS;
- a distinct losing writer remained rejected and unconsumed after successor
  progress;
- corruption of the middle commit in a three-commit POSIX prefix localized to
  `commit_seq=2`;
- a corrupt SQLite cache was rejected and rebuilt exactly from the log.

Raw result: `checker_results.json`.

## Blocking persistence findings

### Current milestone suite is red

- Phenomenon: PBS `2358154.opbs` ran the current persisted `tests/log` slice;
  24 tests passed and 2 failed.
- Expected: the persistence commit remains green after recording terminal
  evidence.
- Actual:
  1. `test_p04_state_cannot_claim_the_terminal_gate_before_runtime_evidence`
     still requires `miyabi_9node: not_run` and `status: in_progress`, while
     the evidence-backed state correctly contains `miyabi_9node_pass` and
     `checking`.
  2. `test_p04_report_is_bilingual_and_records_the_terminal_gate` requires the
     exact contract marker `50×10`, which is absent from the persisted report.
- Reason: the persistence-sensitive regression and bilingual report were not
  transitioned together with the new terminal evidence state.
- Evidence: `current_log_pytest.log`, exit code 1.

### Retry lineage is not persisted

- Phenomenon: final 1-node manifest
  `artifacts/duraloco/P04/20260711_p04_79373ec_1node/manifest.json` has
  `parent_run_id: null`, although the bilingual history identifies failed
  predecessor run `20260711_p04_f6d6e93_1node` / PBS `2358012.opbs`.
- Expected: every retry uses a new run ID and points to its previous attempt.
- Actual: the failed predecessor directory has no manifest and the successful
  retry does not bind it as parent.
- Reason: the failure/retry artifacts were persisted without manifest lineage.

## Other gate results

- P04-A01–A08: implementation/evidence audit PASS.
- Terminal 9-node gate: PASS. Tracked job `2358093.opbs` used nine distinct
  nodes with a hard `00:15:00` walltime, real GPT-2/WikiText-2, eight learners,
  `inner_steps=50`, exactly ten outer transitions, finite losses, eleven
  checkpoint hashes, and all twelve P04 terminal assertions.
- Static plan checksums, PBS syntax, current state schema, and the three final
  maker manifest self-checks pass.

P04 may not transition from `checking` to `completed` until both blocking
findings are fixed and clean parent-linked 1-node, 2-node, and terminal 9-node
evidence is persisted for the new verified commit.
