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

None of these attempts mutated the completed historical source authority.
`2371888` never started runtime, `2371896` stopped in tests, and `2371905`
operated read-only on the preserved P08 prefix.

## Next qualification

The next clean commit adds replay-call events to the committer's raw telemetry.
The required order remains targeted real-prefix benchmark, full one-node suite,
D1 real GPT-2, D2 takeover/ambiguity, then the sequential eight-node final
arms. No ninth node is authorized.
