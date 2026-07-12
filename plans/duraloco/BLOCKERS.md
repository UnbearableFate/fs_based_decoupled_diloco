# DuraLoCo Blockers

No open blocker is recorded through completed P07 and H0. P08 is authorized to
start from the H0-qualified runtime commit
`f167a07c49339ba42d14f8a5873fe2c8781884d4`; its independent checker basis is
`04e0a8634b0e9d7c4cd55c5593081a0ca969a060`.

Runtime checks must remain `not_run` until a PBS compute job produces evidence;
queue delay is not itself a blocker. Any later blocker entry must include a
minimal reproduction, expected/actual behavior, attempt count, evidence,
impact, candidate decisions, and next action.

## Resolved: B-P07-20260712-01 — D8 lifecycle substage exceeded lease TTL

- Status: resolved on 2026-07-12.

- Minimal reproduction: P07 D8-R2 50x10 on nine nodes, jobs 2366037, 2366101, 2366167, and 2366236.
- Expected: ten optimizer transitions plus five lifecycle cycles complete under one fenced committer/takeover chain.
- Actual: progressively larger replay/reachability substages eventually exceed the lease TTL; the latest qualified attempt reached nine transitions before `expired lease cannot be renewed` during the final cycle.
- Attempts: four terminal nine-node attempts, each preceded by the required failure review and clean 1-node/2-node qualification ladder.
- Evidence: `plans/duraloco/reviews/P07_D8_2366037_WORKFLOW_REVIEW.md`, `P07_D8_2366101_WORKFLOW_REVIEW.md`, `P07_D8_2366167_WORKFLOW_REVIEW.md`, and `artifacts/duraloco/P07/20260712_p07_deadline_eb2dc36_d8`.
- Resolution: commit `2295467fd25ae7969eb2b993ef4b193141239286`
  executes each long lifecycle substage in a worker while the fenced committer's
  control thread renews the lease at the configured renewal cadence. A substage
  exception, renewal failure, ownership change, or expired lease fails closed;
  no lifecycle result can be committed after the guard loses ownership.
- Qualification: targeted one-node PBS `2368753.opbs`, full one-node PBS
  `2368758.opbs` (75 tests), and D2-R2 PBS `2368760.opbs` all passed on the same
  clean implementation commit before the new D8-R2 attempt.
- Terminal evidence: PBS `2368771.opbs` completed all ten optimizer transitions,
  five lifecycle cycles, both fault recoveries, exact capsules, snapshot pins,
  and real-namespace GC dry-runs. Its wrapper failed only because the inherited
  report envelope was fixed at 900 seconds while the valid authority completed
  in 1100 seconds. PBS `2368976.opbs` recovered and independently validated the
  reports with an explicit lifecycle envelope. PBS `2369002.opbs` then returned
  independent Checker `PASS` over P07-A01–A24.
- Outcome: P07 is completed, no P07 blocker remains open, and P08 may start from
  verified implementation/checker commit
  `c099adc3c3a99127569a7d9bf38a58547022173c`.
