# P05 Milestone Report

## English

### Status

- Phase: P05 — production syncer lease, fencing, and failover
- Branch: `codex/duraloco-p05-syncer-failover`
- Drift-preserving base: `92acc3af0c2e80951dfcbf20c738841428a8b906`
- Current status: `checking`
- Current verified Maker implementation: `82dbec10e1a738cfaa88212698e7e8cf5a0f7ae1`
- Completed acceptance targets: P05-A01–A08, A10–A12, A14–A20
- Pending acceptance targets: P05-A09, A13
- Checker verdict: pending

P05 adds one dependency-free coordination reference model, a conditional
observational lease, head-committed owner/session/epoch fencing, ancestry-aware
mutation reconciliation, owner-bound strict replay, authoritative stop control
transitions, and an optimizer-transition count separate from control commit
sequence. The existing public syncer and production transaction path remain the
only runtime and head-CAS authority. Full and fragment learners now carry the
fragment version independently from control commit sequence.

### Current Maker evidence

- Final clean same-commit ladder: PBS `2360270.opbs` one-node, PBS
  `2360275.opbs` two-node, and PBS `2360276.opbs` nine-node, all at
  `82dbec10e1a738cfaa88212698e7e8cf5a0f7ae1` with schema-v2 parent lineage.
- The 9-node terminal run used eight learner nodes plus active and standby
  syncers on the ninth node. Active was SIGKILLed after optimizer transition 2;
  standby committed epoch 2 and completed all 10 optimizer transitions plus a
  separate stop control transition in 9m52s. All learners reached 600 local
  steps, all 96 recorded losses were finite, 80 proposals were included exactly
  once, 11 checkpoints were retained, takeover RTO was 68.722 s, and split
  brain/double inclusion were both zero.

- PBS `2360246.opbs`, run `20260711_p05_full_2a8ab75_1node`: forbidden scan
  passed; 352 tests passed with one explicit skip; 1,000 reference traces
  passed; the ten-commit POSIX crash contract passed; full and fragment process
  paths completed exactly 2 and 4 optimizer transitions. Deleting derived
  latest/stop/model/optimizer exports and reopening from authority reproduced
  the exact committed-state digest for both paths.
- PBS `2360251.opbs`, run `20260711_p05_failover_2a8ab75_2node`: two distinct
  nodes performed real lease expiry and epoch-2 takeover. The resumed epoch-1
  optimizer and stop were rejected; exactly one optimizer transition and one
  authoritative stop survived; both ranks reported identical state/view
  digests and zero split brain/double inclusion.
- Unit lineage: RED `2360088.opbs`; first GREEN exposed one test-fixture error
  in `2360089.opbs`; corrected reference GREEN `2360094.opbs`; schema
  `2360103.opbs`; lease `2360121.opbs`; production `2360167.opbs`; syncer
  `2360186.opbs`.
- Timing/safety review:
  `plans/duraloco/reviews/P05_COORDINATION_TIMING_AND_SAFETY_REVIEW.md`.

### Failure and retry history

- The first RED checkout attempt used an invalid shared checkout identity; two
  following `/tmp` worktrees were invisible on compute nodes. Those attempts
  are inconclusive infrastructure evidence. The valid shared-Lustre RED is
  `20260711_p05_red_aac21c6_1node_attempt3`.
- PBS `2360166.opbs` was rejected before tests because the submitted expected
  SHA was mistyped. Its schema-v2 manifest is inconclusive and is excluded.
- PBS `2360182.opbs` found a test-only empty `run_id`; corrected PBS `2360186`
  passed all 29 coordination/syncer contract tests.
- PBS `2360204.opbs` failed because its process root was outside the immutable
  checkout and config path containment correctly rejected it.
- PBS `2360224.opbs` reached all 331 tests and the POSIX contract, then exposed
  that analysis treated control commits as optimizer commits.
- PBS `2360235.opbs` returned success at candidate `a29adab`, but retrospective
  inspection showed the full learner proposal used control commit sequence as
  fragment version and was quarantined. The harness also failed to assert the
  intended optimizer count. This run is retained but excluded from acceptance.
  The learner metadata was separated and the harness gained explicit count and
  stop-reason assertions; PBS `2360246` is the valid successor.

### Pending Checker gate

The Maker ladder is complete. A clean-worktree Checker must still add an
unlisted counterexample and review clock assumptions plus D-M0010–D-M0012
attribution. P05 must remain checking until that artifact passes.

### Known limitations and next action

Learner interval/session boundary and warm-recovery semantics remain P06 scope.
No historical database run is migrated or resumed. Next: persist the passing
Maker ladder, run the independent Checker, and archive P05 if it authorizes the
remaining P05-A09/P05-A13 gates.

## 中文

### 状态

- 阶段：P05 — production syncer lease、fencing 与 failover
- 分支：`codex/duraloco-p05-syncer-failover`
- 保留漂移后的基线：`92acc3af0c2e80951dfcbf20c738841428a8b906`
- 当前状态：`checking`
- 当前 Maker implementation：`82dbec10e1a738cfaa88212698e7e8cf5a0f7ae1`
- 已完成验收：P05-A01–A08、A10–A12、A14–A20
- 待完成验收：P05-A09、A13
- Checker 结论：待运行

P05 增加了唯一的 dependency-free coordination 参考模型、conditional 观测性 lease、
写入 head 的 owner/session/epoch fencing、基于 ancestry 的 mutation reconciliation、
owner 边界 strict replay、权威 stop control transition，以及与 control commit sequence
分离的 optimizer-transition count。现有公共 syncer 和 production transaction path
仍是唯一 runtime 与 head-CAS 权威。full/fragment learner 现在都把 fragment version
与 control commit sequence 分开传递。

### 当前 Maker 证据

- 最终干净同 commit ladder：PBS `2360270.opbs` 单节点、PBS `2360275.opbs`
  双节点，以及 PBS `2360276.opbs` 九节点，全部绑定
  `82dbec10e1a738cfaa88212698e7e8cf5a0f7ae1`，并使用 schema-v2 parent lineage。
- 九节点 terminal 使用八个 learner node，并在第九节点同时运行 active/standby
  syncer。active 在 optimizer transition 2 后被 SIGKILL；standby 提交 epoch 2，
  在 9 分 52 秒内完成全部 10 个 optimizer transition 和独立 stop control
  transition。每个 learner 达到 600 local steps，96 个 loss 全部有限，80 个
  proposal 各自恰好包含一次，保留 11 个 checkpoint，takeover RTO 为 68.722 秒，
  split brain 和 double inclusion 均为零。

- PBS `2360246.opbs`、run `20260711_p05_full_2a8ab75_1node`：禁止项扫描
  通过；352 项测试通过、1 项显式跳过；1,000 条参考 trace 通过；十 commit POSIX
  crash contract 通过；full/fragment 进程路径分别恰好完成 2/4 个 optimizer
  transition。删除派生 latest/stop/model/optimizer export 后，仅从权威日志重开，
  两条路径都复现了完全相同的 committed-state digest。
- PBS `2360251.opbs`、run `20260711_p05_failover_2a8ab75_2node`：两个不同节点
  完成真实 lease 过期与 epoch-2 takeover。恢复的 epoch-1 optimizer/stop 被拒；
  恰好一个 optimizer transition 和一个权威 stop 存活；两 rank 的 state/view digest
  相同，split brain 与 double inclusion 均为零。
- Unit lineage：RED `2360088.opbs`；首次 GREEN 在 `2360089.opbs` 暴露一个测试
  fixture 错误；修正后的参考 GREEN `2360094.opbs`；schema `2360103.opbs`；lease
  `2360121.opbs`；production `2360167.opbs`；syncer `2360186.opbs`。
- timing/safety review：
  `plans/duraloco/reviews/P05_COORDINATION_TIMING_AND_SAFETY_REVIEW.md`。

### 失败与重试历史

- 第一次 RED checkout 使用了错误的共享 checkout 身份；随后两个 `/tmp` worktree 在
  compute node 不可见。这些尝试是 inconclusive infrastructure 证据。有效的共享
  Lustre RED 为 `20260711_p05_red_aac21c6_1node_attempt3`。
- PBS `2360166.opbs` 因提交时手误写错 expected SHA，在测试前被拒绝；其 schema-v2
  manifest 为 inconclusive，不参与验收。
- PBS `2360182.opbs` 发现测试中的空 `run_id`；修正后的 PBS `2360186` 通过全部
  29 项 coordination/syncer contract 测试。
- PBS `2360204.opbs` 的 process root 位于 immutable checkout 外，config 路径约束
  正确拒绝了它。
- PBS `2360224.opbs` 通过 331 项测试和 POSIX contract 后，暴露 analysis 把 control
  commit 当作 optimizer commit 的问题。
- PBS `2360235.opbs` 在候选 `a29adab` 上返回成功，但追溯检查发现 full learner
  proposal 把 control commit sequence 当作 fragment version，因而被 quarantine；
  harness 也没有断言目标 optimizer count。该 run 保留但排除出验收。修正 learner
  metadata 并加入 count/stop-reason 强断言后，PBS `2360246` 成为有效后继。

### 待完成 Checker gate

Maker ladder 已完成。仍需从干净 worktree 运行 Checker；Checker 必须增加 Maker 未
列出的反例，并审查时钟假设与 D-M0010–D-M0012 证据归属。该 artifact 通过前，
P05 必须保持 checking。

### 已知限制与下一步

learner interval/session boundary 与 warm recovery 语义属于 P06。不会迁移或续跑任何
历史数据库 run。下一步：持久化通过的 Maker ladder，运行独立 Checker；若其授权
剩余的 P05-A09/P05-A13，再归档 P05。
