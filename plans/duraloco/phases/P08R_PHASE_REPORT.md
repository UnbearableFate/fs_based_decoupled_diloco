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

None of these attempts mutated the completed historical source authority.
`2371888` never started runtime, `2371896` stopped in tests, and `2371905`
operated read-only on the preserved P08 prefix.

## Next qualification

On commit `9194a03d660dca97bb748105816e95bf73b5b776`, targeted replay PBS
`2371964`, full one-node PBS `2371978` (515 passed, one skipped), D1 PBS
`2371983`, and D2 PBS `2371993` passed in order. The next clean commit adds the
frozen complete-experiment elapsed report, terminal snapshot, and in-runtime
terminal strict audit; therefore the same 1-node to 2-node ladder will be
rerun before any eight-node arm. No ninth node is authorized.
