# P08R 440-second replay recovery report

## Current status

P08R is in progress on `codex/duraloco-p08r-replay-440s`. P08 remains
completed. P10 is held until two D8 factor-one 50x10 runs and one D8-R2
fault/lifecycle run each finish within the frozen 440-second complete-experiment
metric on exactly eight learner nodes, followed by an independent Checker PASS.

## Loop 0 and Loop 1 evidence

PBS `2371915.opbs` passed 58 focused replay, snapshot, fencing, takeover,
ambiguity, and transactional-promotion tests on commit
`5a85f3372e26564b37ce6254a379d3d1b323d804`. It then replayed the completed
real GPT-2 ten-transition factor-one prefix twice with a fresh cache and three
times with the same process memo.

Each strict replay read 30,861,300,554 payload bytes and took 51.87 or 49.57
seconds. Steady memoized replay retained the identical state digest, read zero
proposal/params/outer-state tensor bytes, and took 0.226 and 0.217 seconds.
Required manifests and ancestry metadata remained fully replayed. The result
supports the Loop 1 decision gate: incremental RuntimeView derivation is not
needed before the full matched qualification because the eliminated repeated
strict tensor validation provides more than the plan's 30-second margin.

## Failed tries and causes

Every failed try is preserved in
`plans/duraloco/errors/P08R_ERROR_LEDGER.yaml`:

- P08R-E001 never reached PBS because the orchestration command named a
  not-yet-created worktree as its initial working directory.
- P08R-E002 / PBS `2371888.opbs` exited during wrapper setup because the new
  `artifacts/duraloco/P08R` parent did not yet exist.
- P08R-E003 / PBS `2371896.opbs` passed 57 tests and failed one telemetry count:
  the mandatory scope-preflight head read was outside the replay call counter.
  The EXIT path also exposed that manifests did not yet accept phase `P08R`.
- P08R-E004 / PBS `2371905.opbs` passed all 58 tests and ran the real prefix,
  but its assertion incorrectly treated required manifest bytes as tensor
  bytes. Logical tensor validation bytes are now recorded separately.
- P08R-E005 / PBS `2371957.opbs` passed static checks, the database scan, and
  514 repository tests, but the state-checker's unit fixture still encoded the
  superseded direct P08-to-P10 dependency instead of P08R-to-P10.
- P08R-E006 / PBS `2371980.opbs` rejected a D1 storage root outside the detached
  validation worktree before authority initialization. The same-commit retry
  `2371983.opbs` used an in-project fresh storage root and passed.
- P08R-E007 / PBS `2372056.opbs` completed the full eight-node factor-one
  runtime and elapsed gate in 340.529 seconds, then failed a report-only lease
  assertion. Memoized replay correctly needed zero periodic heartbeats, while
  the report still required at least one. The preserved root-cause review is
  `P08R_D8_FAILURE_REVIEW_2372056.md`.
- P08R-E008 / PBS `2372108.opbs` was the first smallest one-node recovery
  benchmark. It failed before opening authority because the new detached-
  worktree wrapper omitted `PYTHONPATH`, so `fs_diloco` was not importable.
- P08R-E009 / PBS `2372160.opbs` created a valid recovered report and left the
  source head unchanged, but its final jq gate used the terminal-audit field
  name `optimizer_transition_count` instead of the report field
  `optimizer_transitions`; the wrapper therefore remained failed.

None of these attempts mutated the completed historical source authority.
`2371888` never started runtime, `2371896` stopped in tests, and `2371905`
operated read-only on the preserved P08 prefix.

## Terminal failure recovery

On commit `ab605c82f2c88a377c151273cfc5f502fbfee3ef`, targeted replay PBS
`2372031`, full one-node PBS `2372042` (519 passed, one skipped), D1 PBS
`2372048`, and D2 PBS `2372054` passed in order. PBS `2372056` then proved the
optimized eight-node runtime itself: ten transitions, terminal snapshot and
strict audit, runtime 332.885 seconds, and complete experiment 340.529 seconds.
Its post-runtime report rejected the valid zero-heartbeat fast path.

The eight-node retry is now fail-closed. The report repair must first pass a
smallest one-node recovery benchmark against the frozen failed authority, then
targeted replay, full one-node, D1, and D2 on one clean repair commit. Only then
may one fresh D8 retry be authorized. No ninth node is authorized.

That recovery gate passed on clean runtime commit
`16e8c4242022c965db3c6fdf30021a5f0c8f4958`: frozen-authority report recovery
PBS `2372168`, targeted replay PBS `2372171`, full one-node PBS `2372183` (520
passed, one skipped), D1 PBS `2372186`, and D2 PBS `2372189`. The source head
digest was unchanged by report recovery. One D8 factor-one retry is explicitly
authorized on this exact commit; another immediate retry is not.

The authorized retry, PBS `2372194.opbs`, passed end to end on exactly eight
learner nodes. Runtime was 329.365 seconds, the complete experiment was 336.920
seconds, and post-runtime work was 6.514 seconds. Its report recorded ten
optimizer CAS guards, one stop CAS guard, zero unnecessary periodic lifecycle
heartbeats, zero authority loss, and terminal strict-audit equality. Together
with the runtime-complete 340.529-second `2372056` experiment and its read-only
recovered PASS report from `2372168`, this supplies the two sequential
factor-one measurements without violating the one-retry limit. The next and
only eight-node shape is the distinct required D8-R2 fault/lifecycle arm.

PBS `2372217.opbs` completed that R2 arm functionally but failed performance:
runtime 670.008 seconds and complete experiment 695.345 seconds. All R2,
interference, bundle, P07, terminal-audit, and regression reports passed. Five
synchronous lifecycle cycles consumed 251.394 seconds and reread 142.383 GB
because they still repeated empty-cache strict replay before the mandatory
terminal strict audit. The preserved root-cause review is
`P08R_D8R2_FAILURE_REVIEW_2372217.md`. No D8-R2 resubmission is authorized
until the opt-in deferral repair passes the smallest compute benchmark and a
fresh clean-commit 1-node to 2-node ladder.
