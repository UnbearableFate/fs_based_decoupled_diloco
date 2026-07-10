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

### 下一动作

以 failure-first 测试实现 genesis、prepare、单 CAS commit、replay、校验、
orphan inspection 与可重建 cache，然后通过最终 9-node 50×10 训练和 P04
feature probe。
