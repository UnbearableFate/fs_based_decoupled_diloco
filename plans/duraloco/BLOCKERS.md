# DuraLoCo Blockers

No open blocker is recorded through completed M00. P05 is authorized to start
from corrected archival tip `89ae48aae5956b09fc6685074d3ea0eaea36b816`.

Runtime checks must remain `not_run` until a PBS compute job produces evidence;
queue delay is not itself a blocker. Any later blocker entry must include a
minimal reproduction, expected/actual behavior, attempt count, evidence,
impact, candidate decisions, and next action.

## B-P07-20260712-01 — D8 lifecycle substage exceeds lease TTL

- Minimal reproduction: P07 D8-R2 50x10 on nine nodes, jobs 2366037, 2366101, 2366167, and 2366236.
- Expected: ten optimizer transitions plus five lifecycle cycles complete under one fenced committer/takeover chain.
- Actual: progressively larger replay/reachability substages eventually exceed the lease TTL; the latest qualified attempt reached nine transitions before `expired lease cannot be renewed` during the final cycle.
- Attempts: four terminal nine-node attempts, each preceded by the required failure review and clean 1-node/2-node qualification ladder.
- Evidence: `plans/duraloco/reviews/P07_D8_2366037_WORKFLOW_REVIEW.md`, `P07_D8_2366101_WORKFLOW_REVIEW.md`, `P07_D8_2366167_WORKFLOW_REVIEW.md`, and `artifacts/duraloco/P07/20260712_p07_deadline_eb2dc36_d8`.
- Impact: P07-A18/A21 and the independent checker cannot pass; P07 cannot complete and P08 must not start.
- Candidate decision: implement a fail-closed background lease-renewal guard around long read-only lifecycle substages, or move lifecycle observation to a non-owner worker with an immutable head snapshot and revalidation.
- Next action: human chooses the authority-safe design and authorizes a fresh qualification/retry cycle.
