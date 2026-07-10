---
plan_id: "P10"
title: "Storage-Aware Commit Controller（SACC）与算法–系统协同"
status: "planned"
date: "2026-07-10"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/fs-diloco-miyabi"
planning_basis_commit: "afc50a1e179c64321645b278b2497ea3ab3fe24d"
target_branch: "codex/duraloco-p10-sacc"
depends_on:
  - "P07"
  - "P08"
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
agent_decision_gates:
  - "controller 动态 action 必须先通过 advisory/shadow、guardrail、replay 和独立 Checker gates；通过后由 agent 自动 promotion。"
human_approval_gates: []
---

# P10 — Storage-Aware Commit Controller（SACC）与算法–系统协同

> 本文件是可直接交给 Codex 执行的阶段计划，不是背景说明。执行前必须同时读取：
>
> 1. 仓库根目录 `AGENTS.md`；
> 2. `00_CODEX_LOOP_OPERATING_CONTRACT.md`；
> 3. `miyabi-development` skill 的 `SKILL.md`；
> 4. 上一阶段的 `PHASE_REPORT.md`、`STATE.yaml` 和未关闭的决策记录；
> 5. `P00_P04_IMPLEMENTATION_LESSONS.md`；
> 6. `references/DuraLoCo_research_draft_zh.md` 中与本阶段对应的章节。
>
> 计划基于 `codex/fs-diloco-miyabi` 的 `afc50a1e179c64321645b278b2497ea3ab3fe24d` 编写。Codex 必须在执行开始时验证真实基线；若仓库已经前进，先产生 drift report，不得为了匹配本文而强制 reset 或丢弃用户改动。

## 1. 阶段使命

基于可观测 storage tail latency、queue depth、staleness、selection fairness、object/request cost 和 local compute interval，设计稳定、可重放的 SACC。先做 deterministic heuristic 与 shadow evaluation，再有限启用。

### 1.1 本阶段支撑的研究主张

DuraLoCo 不只是把已知日志协议接到持久存储；它针对 Decoupled DiLoCo 的长 local compute 与 quorum semantics 联合控制持久化尾延迟、staleness 和存储放大，从而在当前 POSIX/Lustre 基线上刻画 storage-native 的 break-even region。该主张不要求 object-store portability。

### 1.2 完成后的系统增量

新增 committed controller decisions、adaptive grace、in-flight/bundling/backpressure、eager vs selected-only policy、cost model、fairness controller 和 simulation/small-run ablations。

## 2. 前置条件

- [ ] P08 telemetry 可信；
- [ ] P03 POSIX/Lustre backend 可测；
- [ ] P07 lifecycle 可处理策略产生的对象；
- [ ] 固定-policy baseline 已保存。

## 3. 范围

### 3.1 必须完成

- [ ] SACC observation/action/state schema；
- [ ] shadow/advisory/enforced modes；
- [ ] P50/P95/P99 latency and arrival EMA；
- [ ] adaptive grace；
- [ ] bounded in-flight read/write/prefetch；
- [ ] fragment bundling/coalescing；
- [ ] eager durability vs selected-only materialization；
- [ ] fair quorum age-credit；
- [ ] storage cost/amplification model；
- [ ] hysteresis/cooldown/guardrails；
- [ ] controller decisions 进入 commit/replay；
- [ ] simulator + small model ablation。
- [ ] simulator/runtime/replay 调用同一 fairness/materialization/action policy kernel。

### 3.2 明确不做

- 不直接实现学习型 RL controller；
- 不同时修改优化算法数学和系统策略；
- 不在无 shadow evidence 时动态改变 local interval；
- 不宣称单一策略对所有 backend/scale 最优。

## 4. 预期仓库变更

```text
fs_diloco/coordination/
  controller.py
  observations.py
  actions.py
  adaptive_grace.py
  fairness.py
  materialization.py
  cost_model.py
fs_diloco/testing/
  controller_simulator.py
configs/duraloco/sacc/
analysis/
  analyze_sacc.py
tests/controller/
  test_determinism.py
  test_hysteresis.py
  test_guardrails.py
  test_fairness.py
  test_replay.py
```

## 5. 需要先冻结的设计决策

- [ ] D-1001：可由 controller 修改的 action 集；
- [ ] D-1002：shadow→enforced promotion gate；
- [ ] D-1003：grace 目标 quantile/overlap margin；
- [ ] D-1004：selected-only protocol 的 availability→payload handshake；
- [ ] D-1005：fairness objective 与 max starvation；
- [ ] D-1006：cost function 单位和 provider normalization；
- [ ] D-1007：controller state 是否成为 frontier 的一部分。
- [ ] D-1008：policy kernel 的唯一性、版本 digest 与 simulator/runtime/replay 等价性边界。

每项决策必须写入 `plans/duraloco/DECISIONS.md`，包含：上下文、候选方案、所选方案、拒绝方案、兼容性影响和可逆性。不得把未决语义隐藏在实现细节中。

## 6. Codex 执行循环

### Loop 1 — Observation 与 replay contract

**目标。** 相同 event stream 产生相同 controller decisions。

**先产生的失败证据或规范。**

- [ ] event reorder、missing telemetry、clock skew、restart。

**实现任务。**

- [ ] 定义 logical-time observations；
- [ ] 避免 wall-clock nondeterminism进入 replay；
- [ ] commit decision/action；
- [ ] 恢复 controller state。

**本循环验证。**

- [ ] fixed trace replay decisions identical；
- [ ] 缺 metric 时 fail-safe fallback。

**本循环持久化输出。**

- [ ] controller schema；
- [ ] replay tests。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 2 — Adaptive grace 与 fairness

**目标。** 根据 arrival/latency 分布调整窗口，同时避免 learner ID 偏置和饥饿。

**先产生的失败证据或规范。**

- [ ] 同步候选>qmax 的 lexical bias；慢 learner；burst arrivals；tail spike。

**实现任务。**

- [ ] age-credit selection；
- [ ] quantile/EMA grace；
- [ ] min/max guardrails；
- [ ] selection credit persistence。

**本循环验证。**

- [ ] 公平性 synthetic tests；
- [ ] 无永久 starvation；
- [ ] 决策稳定。

**本循环持久化输出。**

- [ ] grace/fairness policy；
- [ ] ablation configs。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 3 — Materialization、bundling 与 backpressure

**目标。** 控制 eager 写放大和 selected-only 额外往返。

**先产生的失败证据或规范。**

- [ ] selected learner upload 前失败；bundle partial；queue overload。

**实现任务。**

- [ ] 实现 availability manifests；
- [ ] selection request/token；
- [ ] bundle manifests；
- [ ] bounded queues；
- [ ] fallback to eager。

**本循环验证。**

- [ ] failure semantics 无 double inclusion；
- [ ] queue bounded；
- [ ] bundle 仍可验证/GC。

**本循环持久化输出。**

- [ ] materialization modes；
- [ ] I/O amplification traces。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 4 — Cost model 与 shadow controller

**目标。** 估计 bytes/requests/useful token、storage latency overlap 和 staleness。

**先产生的失败证据或规范。**

- [ ] 缺成本配置、provider switching、outlier spike。

**实现任务。**

- [ ] 实现 cost metrics；
- [ ] shadow recommendation；
- [ ] 不影响训练；
- [ ] 对 fixed policies 离线评估。

**本循环验证。**

- [ ] shadow 输出可重放；
- [ ] 决策附原因/约束；
- [ ] 无 metric 时保持 fixed baseline。

**本循环持久化输出。**

- [ ] cost model；
- [ ] shadow reports。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 5 — 有限 enforced 与 ablation

**目标。** 在小规模安全范围验证 controller 不振荡且不损害模型路径。

**先产生的失败证据或规范。**

- [ ] rapid action oscillation；guardrail breach；quality smoke divergence。

**实现任务。**

- [ ] cooldown/hysteresis；
- [ ] 仅启用 grace/inflight/bundle 起步；
- [ ] local interval/quorum 初始保持 policy lock，只有 shadow/guardrail/replay/Checker gates 通过后才由 agent 自动解锁；
- [ ] 多 backend trace/small LM。

**本循环验证。**

- [ ] 无振荡/队列失控；
- [ ] fixed vs shadow vs enforced 可比较；
- [ ] 所有 action 在 commit log。

**本循环持久化输出。**

- [ ] controller E2E；
- [ ] break-even raw grid。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

## 7. 不变量与失败注入

### 7.1 本阶段必须维护的不变量

- [ ] controller decision 可由 committed event stream replay；
- [ ] guardrail 外动作永不执行；
- [ ] controller failure 回退到明确 fixed policy；
- [ ] selection fairness 不依赖固定 learner lexical order；
- [ ] selected-only failure 不重复/丢失已提交 contribution；
- [ ] controller 不静默改变 optimizer 数学。

### 7.2 必须覆盖的故障与反例

- [ ] telemetry missing/out-of-order；
- [ ] latency tail spike；
- [ ] queue overload；
- [ ] controller restart；
- [ ] selected learner failure；
- [ ] bundle partial；
- [ ] policy oscillation；
- [ ] provider cost missing。

## 8. 验收标准

以下条件是阶段 gate，不是建议。Maker 必须给出命令、退出码和 artifact 路径；Checker 必须逐项复核。

- [ ] P10-A01：controller trace replay deterministic；
- [ ] P10-A02：shadow mode 对训练无行为影响；
- [ ] P10-A03：adaptive grace 有 min/max/hysteresis；
- [ ] P10-A04：fair selection 消除稳定 lexical bias且无长期饥饿；
- [ ] P10-A05：eager/selected-only/bundling failure tests 通过；
- [ ] P10-A06：cost/amplification 指标完整；
- [ ] P10-A07：enforced 初版只启用通过 shadow/guardrail/replay/Checker gates 的 actions；
- [ ] P10-A08：small-run fixed/shadow/enforced 对照完成；
- [ ] P10-A09：Checker 审核 replay determinism、stability 和算法语义边界。
- [ ] P10-A10：simulator/runtime/replay 共用 policy kernel 或通过 adversarial ordering 和 mutant tests 证明完全等价；
- [ ] P10-A11：enforced action 的 response-loss/restart 可从 committed decision ancestry 重建，且不依赖 wall-clock/cache；
- [ ] P10-A12：fixed/shadow/enforced 每个 run 的失败、取消与重试有 manifest lineage，最终 Checker 在最终干净 commit 重放当前套件。

## 9. 验证矩阵

| 层级 | 要求 |
|---|---|
| 本地 simulator | 必须：arrival/latency/failure grid、determinism、stability。 |
| Miyabi 1-node | fixed/shadow/enforced tiny real path。 |
| Miyabi 2-node | tail delay/failure injection、fair quorum、backpressure。 |
| POSIX/Lustre | 必须：至少一个真实 backend trace。 |
| MinIO/object store | 可选；缺失不阻塞 P10，不得写成已支持。 |
| 9-node | P11 acceptance 才启用已通过前置 gate 的稳定策略；资源申请无需用户批准。 |

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

## 11. 自动推进与 Agent 决策门

- [ ] controller 动态改变 local interval、quorum 或算法权重前必须通过 advisory/shadow、guardrail、replay 和 Checker gates；通过后由 agent 自动 promotion。
- [ ] P10 必需 gate 通过后自动进入 P11，无需人工审核。

## 12. 阻塞与停止规则

- 同一根因连续三次修复后仍未通过同一 gate：写入 `BLOCKERS.md` 并停止扩大改动。
- 若实现当前目标需要调整 research contract、failure model、协议线性化点或数值语义：agent 记录 ADR、shadow/replay evidence 和 guardrail，经 Checker 复核后继续；只有 materially 超出用户授权研究目标时才停止请求决策。
- 需要在 Miyabi 登录节点运行被禁止的 runtime 命令：停止，转为 PBS allocation。
- 单个 Miyabi 作业可由 agent 自主决定并提交（`select<=16`、`walltime<=02:00:00`，包括 9 节点）；超出该范围或需要付费公共云资源时停止并取得明确批准。
- 发现基础分支包含未合并的用户改动或基线漂移：保留改动，生成 drift report，不得覆盖。

## 13. 阶段完成报告模板

报告 controller mode/actions、decision replay digest、fairness、queue/latency/staleness、bytes/requests、oscillation guardrail和 fixed/shadow/enforced run IDs。

## 14. 可直接复制给 Codex 的启动指令

```text
使用 miyabi-development skill 执行 P10。

仓库：https://github.com/UnbearableFate/fs_based_decoupled_diloco
规划基线：codex/fs-diloco-miyabi @ afc50a1e179c64321645b278b2497ea3ab3fe24d
目标分支：codex/duraloco-p10-sacc
阶段计划：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/11_P10_SACC_AND_ALGORITHM_SYSTEM_CODESIGN.md
共同契约：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/00_CODEX_LOOP_OPERATING_CONTRACT.md

先执行 hostname、git status --short --branch、git rev-parse HEAD，并读取 AGENTS.md、共同契约、当前阶段文件、上一阶段报告和相关研究草稿。若基线漂移，先写 drift report；不要 reset 用户改动。

按阶段文件中的 Loop 顺序工作。每个 Loop 都要先建立失败测试或可执行规范，再做最小实现，随后运行分层验证和独立 checker。持续更新 plans/duraloco/STATE.yaml；不要自动合并 main；不要在 Miyabi 登录节点运行 pytest、torch/transformers/datasets 导入、训练、mpirun 或其他 runtime 工作。

结束时在全部必需 gate 有证据且 Checker 通过时标记 completed，并按依赖图自动启动下一个可执行 goal/phase，不等待用户审核；否则输出 BLOCKED，并给出最小复现、已尝试方案和下一项决策。
```

## 15. 参考输入

- `references/DuraLoCo_research_draft_zh.md`
- 现有实现：`https://github.com/UnbearableFate/fs_based_decoupled_diloco/tree/codex/fs-diloco-miyabi`
- Miyabi skill：`https://github.com/UnbearableFate/miyabi-development`
