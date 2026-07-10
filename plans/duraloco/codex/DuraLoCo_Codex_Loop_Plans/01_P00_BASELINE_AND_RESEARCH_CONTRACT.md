---
plan_id: "P00"
title: "冻结基线、研究契约与 Agent Spine"
status: "planned"
date: "2026-07-10"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/fs-diloco-miyabi"
planning_basis_commit: "011e180980e90c500bcd479a594ba47e507bb5d1"
target_branch: "codex/duraloco-p00-contract"
depends_on:
  []
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
human_approval_gates:
  - "批准 research contract、failure model、恢复语义和协议 P0 不变量后才能进入 P01。"
---

# P00 — 冻结基线、研究契约与 Agent Spine

> 本文件是可直接交给 Codex 执行的阶段计划，不是背景说明。执行前必须同时读取：
>
> 1. 仓库根目录 `AGENTS.md`；
> 2. `00_CODEX_LOOP_OPERATING_CONTRACT.md`；
> 3. `miyabi-development` skill 的 `SKILL.md`；
> 4. 上一阶段的 `PHASE_REPORT.md`、`STATE.yaml` 和未关闭的决策记录；
> 5. `references/DuraLoCo_research_draft_zh.md` 中与本阶段对应的章节。
>
> 计划基于 `codex/fs-diloco-miyabi` 的 `011e180980e90c500bcd479a594ba47e507bb5d1` 编写。Codex 必须在执行开始时验证真实基线；若仓库已经前进，先产生 drift report，不得为了匹配本文而强制 reset 或丢弃用户改动。

## 1. 阶段使命

把“当前 prototype 是什么”“DuraLoCo 要保证什么”“Codex 如何记录进度和证据”固定为可执行契约。在此阶段不改变 learner/syncer 的训练语义；目标是建立后续所有工作可依赖的基线、术语、状态文件和回归证据。

### 1.1 本阶段支撑的研究主张

该阶段本身不支撑性能或容错论文 claim。它确保后续任何 correctness、goodput 和 model-quality 结论都能够追溯到冻结的代码、配置、环境、failure assumptions 与数值语义。

### 1.2 完成后的系统增量

仓库获得 DuraLoCo 持久化 agent spine、research contract、baseline inventory、可重复的现有 full/fragment smoke 以及 phase-gate 工具。

## 2. 前置条件

- [ ] 确认能读取规划基线分支；
- [ ] 复制本计划目录到仓库 `plans/duraloco/codex/`；
- [ ] 确保 DuraLoCo 研究草稿位于 `plans/duraloco/references/` 或文档中记录其外部路径。

## 3. 范围

### 3.1 必须完成

- [ ] 盘点当前模块、配置、tests、PBS scripts、文件布局和所有权威状态；
- [ ] 冻结术语：proposal、commit、frontier、head、logical inclusion、global exact recovery、warm restart、exact learner restart；
- [ ] 定义 failure model、linearization assumptions 和非目标；
- [ ] 定义参数/outer optimizer 的 numeric contract；
- [ ] 建立 STATE、DECISIONS、BLOCKERS、TRACEABILITY 和 artifact manifest；
- [ ] 记录现有 full-vector、fragment、resume、retention 和 Miyabi smoke 的基线行为；
- [ ] 更新 `AGENTS.md`，让后续 Codex 会话自动发现 phase 规则。

### 3.2 明确不做

- 不实现 Protocol v2；
- 不修改现有 update 选择或 outer optimizer 数值；
- 不宣称现有系统满足 exactly-once、prefix recovery 或 syncer failover；
- 不提交 9 节点训练。

## 4. 预期仓库变更

建议新增：

```text
plans/duraloco/
  STATE.yaml
  DECISIONS.md
  BLOCKERS.md
  TRACEABILITY.md
  phases/
  references/
docs/duraloco/
  research_contract.md
  failure_model.md
  invariants.md
  numeric_contract.md
  baseline_inventory.md
  migration_map.md
scripts/agent/
  capture_baseline.py
  check_phase_state.py
  create_run_manifest.py
tests/
  test_agent_state_contract.py
  test_baseline_compatibility.py
```

允许更新：根 `AGENTS.md`、README 的开发入口、`.gitignore`。不得移动现有 `fs_diloco/*.py` 或改变 runtime default。

## 5. 需要先冻结的设计决策

- [ ] D-0001：authority model——现阶段如实记录 filesystem、`latest.json`、SQLite 的分散状态；目标模型为 commit log 单一权威；
- [ ] D-0002：failure model 是否覆盖 process kill、node loss、storage timeout、data corruption、MDS/object-store availability；
- [ ] D-0003：数值可重复性等级：bitwise、digest-stable metadata、或 tolerance-based tensor equivalence；
- [ ] D-0004：三种 recovery guarantee 的边界；
- [ ] D-0005：研究不主张替代 NCCL/RDMA 高频同步。

每项决策必须写入 `plans/duraloco/DECISIONS.md`，包含：上下文、候选方案、所选方案、拒绝方案、兼容性影响和可逆性。不得把未决语义隐藏在实现细节中。

## 6. Codex 执行循环

### Loop 1 — 基线与漂移清单

**目标。** 固定真实代码基线并识别计划与仓库现状的偏差。

**先产生的失败证据或规范。**

- [ ] 建立一个会在 branch/commit、脏工作树或关键路径缺失时失败的 baseline capture test。

**实现任务。**

- [ ] 记录目录树、依赖、配置、CLI、现有 protocol path、SQLite schema、PBS scripts；
- [ ] 把此前审查发现映射为可复现 issue IDs，不把审查文本当作已自动证明；
- [ ] 生成 `baseline_inventory.md` 与 `migration_map.md`。

**本循环验证。**

- [ ] `capture_baseline.py` 在干净树生成 manifest；
- [ ] 修改任一关键配置后 digest 检查会失败。

**本循环持久化输出。**

- [ ] baseline manifest；
- [ ] drift report（若需要）；
- [ ] 模块/测试/PBS 对照表。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 2 — 研究契约与不变量

**目标。** 把论文词汇变成工程可测试的定义。

**先产生的失败证据或规范。**

- [ ] 为缺少必填术语、不变量 ID 重复或 claim 无证据映射编写静态失败检查。

**实现任务。**

- [ ] 编写 failure model；
- [ ] 定义 I-001 至少包括 committed-prefix、one logical inclusion、causal base、fragment/outer-state pairing、fencing、safe GC；
- [ ] 定义 global exact、warm learner、exact learner；
- [ ] 定义 numeric contract 与允许误差。

**本循环验证。**

- [ ] 文档链接和 invariant IDs 由脚本检查；
- [ ] TRACEABILITY 中每个 P0 claim 都指向未来 test owner。

**本循环持久化输出。**

- [ ] research contract；
- [ ] invariant catalog；
- [ ] numeric contract；
- [ ] traceability seed。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 3 — Agent spine 与 phase gate

**目标。** 让新 Codex 会话可以从磁盘恢复工作状态。

**先产生的失败证据或规范。**

- [ ] `check_phase_state.py` 对缺字段、非法状态转换、无证据 PASS 返回非零。

**实现任务。**

- [ ] 创建 state/template/artifact 目录；
- [ ] 实现 run manifest 创建与 checksum；
- [ ] 把共同执行契约摘要加入 AGENTS；
- [ ] 定义 phase 状态转换。

**本循环验证。**

- [ ] 模板可解析；
- [ ] 无 checker report 时不能标记 ready_to_merge；
- [ ] 脏树和缺 commit 被 manifest 标记。

**本循环持久化输出。**

- [ ] STATE、DECISIONS、BLOCKERS、TRACEABILITY；
- [ ] phase gate scripts；
- [ ] AGENTS 更新。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 4 — 现有实现回归基线

**目标。** 在不改变 runtime 语义的情况下保存现有可运行证据。

**先产生的失败证据或规范。**

- [ ] 先定义期望产物、日志事件和有限 loss 检查；若当前路径不满足，记录为 baseline limitation，不在本阶段偷修。

**实现任务。**

- [ ] 运行依赖可用环境中的现有 unit tests；
- [ ] 运行 local tiny synthetic smoke；
- [ ] 在批准/可用时走 Miyabi 1-node 现有 debug 路径；
- [ ] 保存 run roots、日志和 digests。

**本循环验证。**

- [ ] 现有 tests 结果完整记录；
- [ ] smoke 的 `latest.json`、weights、DB dump、日志事件被 evidence checker 验证。

**本循环持久化输出。**

- [ ] baseline test report；
- [ ] baseline smoke manifest；
- [ ] 已知缺陷列表。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

## 7. 不变量与失败注入

### 7.1 本阶段必须维护的不变量

- [ ] P00 不改变训练、merge、selection、resume 和 retention 的默认行为；
- [ ] 所有基线结果绑定 commit/config/environment；
- [ ] 计划目标和观察结果分栏记录；
- [ ] 未运行的 Miyabi 验证不得标为 PASS。

### 7.2 必须覆盖的故障与反例

- [ ] 脏工作树；
- [ ] 规划基线与实际分支漂移；
- [ ] 缺配置或脚本；
- [ ] run manifest 缺 commit/config digest；
- [ ] STATE 非法跳转到 ready_to_merge。

## 8. 验收标准

以下条件是阶段 gate，不是建议。Maker 必须给出命令、退出码和 artifact 路径；Checker 必须逐项复核。

- [ ] P00-A01：`baseline_inventory.md` 覆盖当前 package、tests、configs、scripts、data/control state；
- [ ] P00-A02：research contract 明确定义三种 recovery、logical exactly-once、commit point 和 non-claims；
- [ ] P00-A03：每个核心不变量拥有唯一 ID 和 future test owner；
- [ ] P00-A04：phase state checker 可拒绝缺证据的完成状态；
- [ ] P00-A05：所有现有可运行 tests/smokes 结果被保存，失败项有最小复现；
- [ ] P00-A06：runtime 默认行为未改变；
- [ ] P00-A07：Checker 复核 baseline 和研究契约；
- [ ] P00-A08：人工批准研究契约。

## 9. 验证矩阵

| 层级 | 本阶段要求 | 说明 |
|---|---|---|
| 本地静态 | 必须 | Markdown/link/schema/state checks；shell syntax。 |
| 本地 runtime | 条件必须 | 依赖完整时运行现有 tests 和 tiny smoke。 |
| Miyabi login static | 需要同步时必须 | `bash -n`、配置和 branch/commit 检查；不得 pytest。 |
| Miyabi 1-node | 推荐为基线证据 | 使用现有 `run_1node_debug.pbs` 或等价 interactive real path。 |
| Miyabi 2-node | 本阶段不要求 | 不为基线契约消耗多节点。 |
| Miyabi 9-node | 禁止 | 尚无 correctness foundation。 |

## 10. Maker–Checker 交接

### Maker 必须提交

- 只包含本阶段范围的 feature branch；
- 实现、测试、文档和迁移说明；
- `plans/duraloco/STATE.yaml` 的最新状态；
- `artifacts/duraloco/<phase>/<run_id>/manifest.json`；
- 每条验收标准对应的证据路径；
- 已知限制、跳过的验证及原因；
- `git status --short --branch` 与 `git rev-parse HEAD` 输出。

### Checker 必须独立检查

- 从 diff 和规范反向推导是否有漏项，而不是只运行 Maker 提供的 happy-path 命令；
- 至少增加或执行一个 Maker 未列出的反例；
- 检查测试是否会在回退实现时真正失败；
- 检查是否存在静默兼容性破坏、权威状态双写、错误的故障假设或不可复现结果；
- 输出 `artifacts/duraloco/<phase>/<run_id>/checker_report.md`，结论只能是 `PASS`、`PASS_WITH_FOLLOWUPS` 或 `BLOCKED`。

Checker 不得直接修改 Maker 的工作树。发现问题后，由 Maker 在原阶段分支修复并重新提交验证。

## 11. 人工审批门

- [ ] 批准 research contract、failure model、恢复语义和协议 P0 不变量后才能进入 P01。

## 12. 阻塞与停止规则

- 同一根因连续三次修复后仍未通过同一 gate：写入 `BLOCKERS.md` 并停止扩大改动。
- 需要改变 research contract、failure model、协议线性化点或数值语义：停止并请求人工决策。
- 需要在 Miyabi 登录节点运行被禁止的 runtime 命令：停止，转为 PBS allocation。
- 需要提交 9 节点、长时间或付费公共云作业：停止并取得明确批准。
- 发现基础分支包含未合并的用户改动或基线漂移：保留改动，生成 drift report，不得覆盖。

## 13. 阶段完成报告模板

```text
P00 status:
actual baseline:
research-contract approval:
existing tests: pass/fail/skipped
local smoke run ID:
Miyabi 1-node run ID or reason skipped:
open P0 defects:
next phase gate: P01 allowed / blocked
```

## 14. 可直接复制给 Codex 的启动指令

```text
使用 miyabi-development skill 执行 P00。

仓库：https://github.com/UnbearableFate/fs_based_decoupled_diloco
规划基线：codex/fs-diloco-miyabi @ 011e180980e90c500bcd479a594ba47e507bb5d1
目标分支：codex/duraloco-p00-contract
阶段计划：plans/duraloco/codex/01_P00_BASELINE_AND_RESEARCH_CONTRACT.md
共同契约：plans/duraloco/codex/00_CODEX_LOOP_OPERATING_CONTRACT.md

先执行 hostname、git status --short --branch、git rev-parse HEAD，并读取 AGENTS.md、共同契约、当前阶段文件、上一阶段报告和相关研究草稿。若基线漂移，先写 drift report；不要 reset 用户改动。

按阶段文件中的 Loop 顺序工作。每个 Loop 都要先建立失败测试或可执行规范，再做最小实现，随后运行分层验证和独立 checker。持续更新 plans/duraloco/STATE.yaml；不要自动合并 main；不要在 Miyabi 登录节点运行 pytest、torch/transformers/datasets 导入、训练、mpirun 或其他 runtime 工作。

结束时只在全部 gate 有证据时标记 ready_to_merge；否则输出 BLOCKED，并给出最小复现、已尝试方案和下一项决策。
```

## 15. 参考输入

- `references/DuraLoCo_research_draft_zh.md`
- 现有实现：`https://github.com/UnbearableFate/fs_based_decoupled_diloco/tree/codex/fs-diloco-miyabi`
- Miyabi skill：`https://github.com/UnbearableFate/miyabi-development`
