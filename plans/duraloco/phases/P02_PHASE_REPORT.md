# P02 Milestone Report

## English

### Status

- Phase: P02 — deterministic reference simulator and in-memory backend
- Branch: `codex/duraloco-p02-reference-model`
- Verified implementation commit: `7e12997ca0a9fe4e48bb96cfe6391e0e8d1bf773`
- State: `checking`; implementation gates passed and persistence is under final review
- Maker evidence: PBS `2357761.opbs` on `mg0011`, 213 passed and 1 skipped;
  explicit 10,000 traces produced 10,000 unique state digests
- Checker evidence: PBS `2357765.opbs` on `mg0013`
- Checker verdict: `PASS`; `required_gate_followups: none`

The reference storage, immutable transition system, optimizer oracle, crash
matrix, deterministic replay/minimizer, seeded traces, and five safety mutants
are implemented. P02-A01 through P02-A08 passed. The final remaining action is
to persist this checked state and archive the milestone commit.

### Acceptance summary

| Target | Result | Primary evidence |
|---|---|---|
| P02-A01–A02 | PASS | independence and transition invariant tests |
| P02-A03–A04 | PASS | crash-prefix and logical-inclusion tests |
| P02-A05 | PASS | five deliberate mutants killed |
| P02-A06 | PASS | legacy Torch optimizer/one-fragment oracle comparison |
| P02-A07 | PASS | deterministic replay/minimizer and 10,000 traces |
| P02-A08 | PASS | independent ID-order and decision/prepare interleavings |

### Checker failure history

#### Attempt at `585f057` — resolved

- Phenomenon: PBS `2357700.opbs` committed learner/session/fragment sequence 2,
  then accepted sequence 1 from the successor base.
- Expected/actual: committed lineage must increase monotonically; the model
  accepted a rollback.
- Reason: eligibility and invariant folding did not track the last committed
  lineage sequence.
- Impact: D-0203 and P02-A08.
- Resolution: commit `fd2468b62dc2ec288a31795a59a65881027b3684`
  added eligibility, invariant, regression, and mutant coverage. Independent
  PBS `2357710.opbs` passed this counterexample.

#### Attempt at `78bc733` — resolved

- Phenomenon: PBS `2357714.opbs` constructed two same-lineage/same-base
  proposals whose newer proposal ID sorted first. `select_quorum` selected the
  older proposal, but `replay_trace` committed the lexically first newer one,
  leaving the older proposal ineligible without a supersession decision.
- Expected/actual: trace commits must use oldest-first `select_quorum`; replay
  instead used `sorted(eligible)[0]`.
- Reason: confirmed implementation-policy divergence in the trace commit path.
- Impact: D-0203, D-0204, P02-A08, and the validity of the 1,000/10,000-trace
  model-check evidence.
- Evidence: `artifacts/duraloco/P02/20260710_checker_fd2468b/checker_selection_counterexample.log`.
- Resolution: `ba8e594fca0ba2c01365391c114a463bd3579a53` routed trace commits
  through `select_quorum` and added the exact regression;
  `7e12997ca0a9fe4e48bb96cfe6391e0e8d1bf773` committed compute-generated
  goldens. Parent-linked maker PBS `2357761.opbs` and independent Checker PBS
  `2357765.opbs` passed.

### Next action

Complete the persistence audit, mark P02 `completed`, create the required
milestone archival commit, and only then start P03.

## 中文

### 状态

- 阶段：P02 — 确定性参考模拟器与内存后端
- 分支：`codex/duraloco-p02-reference-model`
- 已验证实现提交：`7e12997ca0a9fe4e48bb96cfe6391e0e8d1bf773`
- 状态：`checking`；实现 gate 已通过，正在进行最终持久化复核
- Maker 证据：PBS `2357761.opbs`，运行于 `mg0011`，213 项通过、1 项跳过；
  显式 10,000 traces 产生 10,000 个唯一 state digest
- Checker 证据：PBS `2357765.opbs`，运行于 `mg0013`
- Checker 结论：`PASS`；`required_gate_followups: none`

参考存储、不可变状态转换、优化器 oracle、故障矩阵、确定性
replay/minimizer、seeded traces 和五个安全 mutant 已实现。只有 trace
runner 已使用冻结的 quorum 策略，P02-A01 至 P02-A08 全部通过。当前只需
持久化 checked state 并创建 milestone archival commit。

### 验收摘要

| Target | 结果 | 主要证据 |
|---|---|---|
| P02-A01–A02 | PASS | independence 与 transition invariant 测试 |
| P02-A03–A04 | PASS | crash-prefix 与 logical-inclusion 测试 |
| P02-A05 | PASS | 五个故意注入的 mutant 全部被捕获 |
| P02-A06 | PASS | legacy Torch optimizer/单 fragment oracle 对照 |
| P02-A07 | PASS | 确定性 replay/minimizer 与 10,000 traces |
| P02-A08 | PASS | 独立 ID 顺序和 decision/prepare 交错反例 |

### Checker 失败历史

#### `585f057` 尝试 — 已解决

- 现象：PBS `2357700.opbs` 先提交 learner/session/fragment 序号 2，随后又从
  后继 base 接受序号 1。
- 预期/实际：已提交 lineage 序号必须单调递增；模型实际接受了回退。
- 原因：eligibility 和 invariant fold 没有记录最后提交的 lineage 序号。
- 影响：D-0203 和 P02-A08。
- 解决：提交 `fd2468b62dc2ec288a31795a59a65881027b3684` 增加 eligibility、
  invariant、回归测试和 mutant 覆盖；独立 PBS `2357710.opbs` 已通过该反例。

#### `78bc733` 尝试 — 已解决

- 现象：PBS `2357714.opbs` 构造了两个同 lineage、同 base 的 proposal，且
  新 proposal ID 的字典序更小。`select_quorum` 选择旧 proposal，但
  `replay_trace` 提交了字典序最小的新 proposal，使旧 proposal 在没有
  supersession 决策的情况下变为不可提交。
- 预期/实际：trace commit 必须使用 oldest-first `select_quorum`；实际使用了
  `sorted(eligible)[0]`。
- 原因：已确认 trace commit 路径与冻结策略不一致。
- 影响：D-0203、D-0204、P02-A08，以及 1,000/10,000 trace model-check
  证据的有效性。
- 证据：`artifacts/duraloco/P02/20260710_checker_fd2468b/checker_selection_counterexample.log`。
- 解决：`ba8e594fca0ba2c01365391c114a463bd3579a53` 让 trace commit 调用
  `select_quorum` 并增加精确回归测试；
  `7e12997ca0a9fe4e48bb96cfe6391e0e8d1bf773` 提交 compute 生成的 goldens。
  父子关联 Maker PBS `2357761.opbs` 和独立 Checker PBS `2357765.opbs` 均通过。

### 下一动作

完成 persistence audit，把 P02 标记为 `completed`，创建要求的 milestone
archival commit，然后才能开始 P03。
