# P04 Milestone Report

## English

### Status

- Phase: P04 — transactional fragment log and prefix recovery
- Branch: `codex/duraloco-p04-transaction-log`
- Base: completed P03 commit `a93633d8d41bdb0e184711c4efaa132f211aa5e9`
- State: `in_progress`
- Completed targets: none
- Open targets: P04-A01 through P04-A09
- Terminal runtime gate: real 9-node GPT-2/WikiText-2, 8 learners plus 1
  syncer, 50 local steps per interval and exactly 10 global optimizer
  transitions, submitted by qsub with a hard 15-minute walltime; not run yet

### Checker failure history

No Checker attempt has run yet. Any failed milestone check will record the
observed phenomenon, expected/actual behavior, concise reason, impact,
evidence, and resolution here.

### Verification failure history

#### 1-node attempt `f6d6e93` / PBS `2358012` — fix pending rerun

- Phenomenon: the full compute-node suite passed 269 tests with one skip, but
  `test_same_logical_prepare_and_response_loss_are_idempotent` failed. After a
  lost CAS-success response, the first recovery returned `already_committed`;
  a second identical prepared retry returned `committed`.
- Expected/actual: both post-commit retries must be classified as recovered
  existing success; the second retry reported a fresh commit even though no
  new transition occurred.
- Reason: `commit_prepared` relied on backend request-id idempotency and mapped
  every non-exception return to `committed`; it did not resolve the current
  head before retrying the CAS.
- Impact: response-loss observability in P04-A03. Safety remained intact:
  replay still contained one transition and one proposal inclusion.
- Evidence: `artifacts/duraloco/P04/20260711_p04_f6d6e93_1node/pytest.log`.
- Resolution: pre-resolve an exact prepared head as `already_committed` before
  issuing CAS; rerun required.

### Next action

Implement failure-first genesis, prepare, one-CAS commit, replay, verification,
orphan inspection, and rebuildable cache tests, then pass the terminal 9-node
50×10 training and P04 feature probe.

## 中文

### 状态

- 阶段：P04 — transactional fragment log 与 prefix recovery
- 分支：`codex/duraloco-p04-transaction-log`
- 基线：已完成的 P03 提交 `a93633d8d41bdb0e184711c4efaa132f211aa5e9`
- 状态：`in_progress`
- 已完成 targets：无
- 未完成 targets：P04-A01 至 P04-A09
- 最终 runtime gate：真实 9-node GPT-2/WikiText-2，8 个 learners 加 1 个
  syncer，每个 interval 50 local steps，且恰好 10 次 global optimizer
  transition，以 qsub 提交且 walltime 固定为 15 分钟；尚未运行

### Checker 失败历史

尚未运行 Checker。任何 milestone 检查失败都将在此记录现象、预期/实际行为、
简短原因、影响、证据与解决方式。

### 验证失败历史

#### 单节点尝试 `f6d6e93` / PBS `2358012` — 已修复，待重跑

- 现象：compute-node 全套测试 269 项通过、1 项跳过，但
  `test_same_logical_prepare_and_response_loss_are_idempotent` 失败。CAS 成功响应
  丢失后，第一次恢复返回 `already_committed`，第二次相同 prepared retry 却
  返回 `committed`。
- 预期/实际：两次 post-commit retry 都应标记为恢复既有成功；实际第二次被
  报告为新提交，尽管没有产生新 transition。
- 原因：`commit_prepared` 依赖 backend request-id 幂等返回，并把所有无异常
  返回都映射为 `committed`，CAS 前没有先读取并解析当前 head。
- 影响：P04-A03 的 response-loss 可观测语义。安全性未受影响：replay 仍只有
  一个 transition 和一次 proposal inclusion。
- 证据：`artifacts/duraloco/P04/20260711_p04_f6d6e93_1node/pytest.log`。
- 解决：CAS 前先解析 exact prepared head，并返回 `already_committed`；需要重跑。

### 下一动作

以 failure-first 测试实现 genesis、prepare、单 CAS commit、replay、校验、
orphan inspection 与可重建 cache，然后通过最终 9-node 50×10 训练和 P04
feature probe。
