# H0 Pre-P08 Hardening Report

## Final status

- Status: completed
- P07 basis: `c099adc3c3a99127569a7d9bf38a58547022173c`
- Qualified runtime commit: `f167a07c49339ba42d14f8a5873fe2c8781884d4`
- Independent checker commit/job: `04e0a8634b0e9d7c4cd55c5593081a0ca969a060`, `2369726.opbs`
- Acceptance: H0-A01 through H0-A09 pass
- Required follow-ups: none
- Next phase: P08

H0 repaired every must-complete item in the pre-P08 hardening plan while
preserving the committed transition schema and identities. The transition log
and its single head CAS remain the only optimizer authority; every new counter,
capability report, heartbeat field, and lifecycle report is observational or
derived.

## Implemented hardening

The floating committer now records `error` on crash paths, rethrows the primary
exception, and finalizes without masking it. A stop is published only after an
authoritative committed stop is observed. Prepare/commit ambiguity forces
empty-cache strict replay, tensor reload, and clean stop handling. Executor
result waits run under the long-substage renewal guard; the final D8 logs
contain nine renewal heartbeats during `executor_result_wait`. Grace-window
validation now requires the effective wait to fit inside the lease renewal
budget.

POSIX listing walks only the requested prefix subtree. Listing, `head`, and
idempotent immutable-create checks use the checksummed bounded header, while
`get`/`verified_get` still verify the full payload. Payload-corrupted unknown
objects remain discoverable, fail verified reads, and stay protected from GC.
Lifecycle reports now archive header/payload read counters with a precisely
isolated inventory window.

The storage capability contract records cross-node advisory locking and its
evidence. Shared authority roots fail closed when exclusion cannot be
established. The final two-node Lustre probe saw mount evidence
`lustre-mount-option-flock`, used distinct hosts, blocked the contender while
held, and allowed it after release.

The dormant fragment shadowing defect was removed and a functional
multi-fragment round-robin test binds sidecar metadata to the interval fragment.
Mutation resolution uses explicit commit-sequence lookup, heartbeat reads are
generation-scoped, and a first-lease bootstrap loser becomes an idempotent
return or coordination conflict. The quick hygiene gate includes ruff F/B/PLE;
loss handling and dtype quarantine are typed, and active source remains free of
SQLite and replacement embedded databases.

## Qualification and terminal experiment

The final runtime commit passed the required ladder:

1. `2369617.opbs`: ruff and forbidden-surface checks; 116 focused tests; full
   suite 468 passed and 1 skipped.
2. `2369625.opbs`: real GPT-2 D1, one transition, two exact capsules, strict
   snapshot equality, and zero inventory payload bytes.
3. `2369628.opbs`: two-node Lustre advisory-lock exclusion/takeover probe.
4. `2369629.opbs`: D2-R2 with executor, committer, and host failover; four
   transitions and four lifecycle cycles, all with zero inventory payload reads.
5. `2369634.opbs`: nine-node GPT-2/WikiText-2 D8-R2 50-local × 10-global run.

The terminal run used eight learner nodes, eight learner processes, eight LFEs,
two committer candidates, replication factor two, and zero dedicated syncer
nodes. It completed ten optimizer transitions, five lifecycle cycles, eight
exact capsules, executor-process loss, whole-learner-host loss, membership
revision, and authoritative stop in 752 seconds. Maximum recovery was 89.440
seconds. The five lifecycle times were 34.33, 39.30, 49.34, 58.40, and 68.42
seconds, compared with the P07 basis series 45.58, 69.09, 93.34, 118.57, and
141.89 seconds. Inventory payload reads were zero in all five cycles even as
logical inventory grew from 9.21 GB to 40.82 GB; full strict replay payload
verification remained intact.

The effective-live window remained `150, 196, 220, 248, 276`, with final-three
delta 56 below the preregistered limit 64. The run retained 245 explainable
candidates and performed no destructive GC on the real namespace.

## Failures and corrections

H0 did not erase unsuccessful attempts. `2369364.opbs` and `2369366.opbs`
failed solely on stale P07/P08 acceptance-count fixtures after 467 tests passed;
both fixtures were corrected before clean qualification. The first Checker
`2369715.opbs` failed because one response-loss test did not actually construct
a suffix-only replay, and its wrapper requested an unsupported manifest
purpose. The test now injects a suffix-only commit tuple and fails on the P07
basis; the wrapper uses `contract`. The rerun `2369726.opbs` passed 16/16
RED-on-base and 16/16 GREEN-on-H0 checks. Earlier passing runtime jobs were
superseded when counter evidence was added and when the inventory counter
boundary was moved before lease renewal. Full detail is preserved in
`plans/duraloco/phases/H0_RUN_LEDGER.md`.

## Persistence and handoff

The Checker verified bitwise-identical committed identities on a deterministic
P07 tape and wrote SHA-256 checksums over its report, identity outputs, final
JUnit, D1/D2 lifecycle reports, lock report, and D8 reports. H0 therefore hands
P08 runtime commit `f167a07c49339ba42d14f8a5873fe2c8781884d4` as the honest
profile-first baseline. Review items explicitly deferred by H0 remain owned by
P08 (true range I/O, scan validation reuse, single-copy publication,
materialization cadence, O(selected) lineage, directory durability, and
D-0800 error-stop semantics) or P11 (legacy/hygiene cleanup).

## 中文摘要

H0 已完成，H0-A01 至 H0-A09 全部通过。最终 runtime commit 为 `f167a07`，独立
Checker 作业 `2369726.opbs` 返回 PASS。修复覆盖 committer 终止事实、CAS 冲突 replay、
等待 executor 时续租、prefix/header-only POSIX 读取、Lustre 跨节点锁、multi-fragment、
mutation sequence、heartbeat generation 与 lease bootstrap race。最终按 1 节点、2 节点、
9 节点顺序验证；9 节点 GPT-2/WikiText-2 运行完成 50 local × 10 global，耗时 752 秒。
所有失败与被替代运行均记录在 `H0_RUN_LEDGER.md`，没有被最终成功结果覆盖。
