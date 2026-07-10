# P02 Milestone Report

## English

### Status

- Phase: P02 — deterministic reference simulator and in-memory backend
- Branch: `codex/duraloco-p02-reference-model`
- Current maker commit: `78bc733b01f7ffac68f93ffc2986c3e2dc81d207`
- State: `in_progress`; the phase has not passed the independent Checker
- Maker evidence: PBS `2357711.opbs`, 212 passed and 1 skipped; explicit 10,000-trace run passed
- Checker verdict: `FAIL`

The reference storage, immutable transition system, optimizer oracle, crash
matrix, deterministic replay/minimizer, seeded traces, and five safety mutants
are implemented. P02 cannot complete until the trace runner exercises the
frozen quorum policy and a clean parent-linked maker/checker retry passes.

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

#### Attempt at `78bc733` — open

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
- Required resolution: route trace commits through `select_quorum`, add the
  adversarial regression, regenerate reference goldens, and run a new maker
  artifact with `parent_run_id=20260710_clean_p02_78bc733`, followed by an
  independent Checker retry.

### Next action

Finish the open resolution, rerun P02 on one Miyabi compute node, obtain a
Checker `PASS`, then update all P02 acceptance evidence before starting P03.

## 中文

### 状态

- 阶段：P02 — 确定性参考模拟器与内存后端
- 分支：`codex/duraloco-p02-reference-model`
- 当前 Maker 提交：`78bc733b01f7ffac68f93ffc2986c3e2dc81d207`
- 状态：`in_progress`；尚未通过独立 Checker
- Maker 证据：PBS `2357711.opbs`，212 项通过、1 项跳过；显式 10,000 trace 运行通过
- Checker 结论：`FAIL`

参考存储、不可变状态转换、优化器 oracle、故障矩阵、确定性
replay/minimizer、seeded traces 和五个安全 mutant 已实现。只有 trace
runner 使用冻结的 quorum 策略，并且新的父子关联 Maker/Checker 重试通过后，
P02 才能完成。

### Checker 失败历史

#### `585f057` 尝试 — 已解决

- 现象：PBS `2357700.opbs` 先提交 learner/session/fragment 序号 2，随后又从
  后继 base 接受序号 1。
- 预期/实际：已提交 lineage 序号必须单调递增；模型实际接受了回退。
- 原因：eligibility 和 invariant fold 没有记录最后提交的 lineage 序号。
- 影响：D-0203 和 P02-A08。
- 解决：提交 `fd2468b62dc2ec288a31795a59a65881027b3684` 增加 eligibility、
  invariant、回归测试和 mutant 覆盖；独立 PBS `2357710.opbs` 已通过该反例。

#### `78bc733` 尝试 — 未解决

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
- 必需修复：让 trace commit 调用 `select_quorum`，增加该反例回归测试，
  重新生成 reference goldens，并以
  `parent_run_id=20260710_clean_p02_78bc733` 生成新的 Maker artifact，随后进行
  独立 Checker 重试。

### 下一动作

完成上述修复，在 Miyabi 单个 compute node 上重新运行 P02，取得 Checker
`PASS`，更新全部 P02 acceptance 证据后再开始 P03。
