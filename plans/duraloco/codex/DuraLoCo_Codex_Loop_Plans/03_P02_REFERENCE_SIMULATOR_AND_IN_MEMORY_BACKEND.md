---
plan_id: "P02"
title: "确定性参考模拟器与 In-Memory Backend"
status: "planned"
date: "2026-07-10"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/fs-diloco-miyabi"
planning_basis_commit: "afc50a1e179c64321645b278b2497ea3ab3fe24d"
target_branch: "codex/duraloco-p02-reference-model"
depends_on:
  - "P01"
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
agent_decision_gates:
  - "outer optimizer 数学、quorum selection 或 staleness weighting 的参考语义调整由 agent 记录 ADR 和 oracle 证据，经独立 Checker 复核。"
human_approval_gates: []
---

# P02 — 确定性参考模拟器与 In-Memory Backend

> 本文件是可直接交给 Codex 执行的阶段计划，不是背景说明。执行前必须同时读取：
>
> 1. 仓库根目录 `AGENTS.md`；
> 2. `00_CODEX_LOOP_OPERATING_CONTRACT.md`；
> 3. `miyabi-development` skill 的 `SKILL.md`；
> 4. 上一阶段的 `PHASE_REPORT.md`、`STATE.yaml` 和未关闭的决策记录；
> 5. `references/DuraLoCo_research_draft_zh.md` 中与本阶段对应的章节。
>
> 计划基于 `codex/fs-diloco-miyabi` 的 `afc50a1e179c64321645b278b2497ea3ab3fe24d` 编写。Codex 必须在执行开始时验证真实基线；若仓库已经前进，先产生 drift report，不得为了匹配本文而强制 reset 或丢弃用户改动。

## 1. 阶段使命

在不依赖 filesystem、GPU、训练模型或生产 syncer 的情况下，建立 DuraLoCo 状态机的 executable specification。通过 deterministic simulator、in-memory backend、随机 trace 与 crash enumeration 固定安全语义。

### 1.1 本阶段支撑的研究主张

后续 POSIX、S3 和 production runtime 不是自行定义正确性，而是必须 refinement 到同一个 reference transition system。本阶段是 prefix recovery 和 exactly-once logical inclusion 的 oracle。

### 1.2 完成后的系统增量

新增纯 CPU/标准库可运行的 backend、state machine、reference outer optimizer、trace grammar、model checker 和 replay tool。

## 2. 前置条件

- [ ] P01 schema、identity 与 validator 已冻结；
- [ ] P00 numeric contract 已冻结并通过独立 Checker；
- [ ] 确定 reference compute dtype、rounding 和 proposal ordering。

## 3. 范围

### 3.1 必须完成

- [ ] InMemoryStorageBackend 的语义操作；
- [ ] proposal publication、eligibility、quorum selection、prepare、CAS commit、drop/supersede 状态；
- [ ] single global head + per-fragment frontier reference model；
- [ ] deterministic SGD/momentum/Nesterov/AdamW transition；
- [ ] 随机合法/非法 trace generator；
- [ ] 每个逻辑操作前后的 crash injection；
- [ ] replay、state digest、prefix verifier；
- [ ] reference vs legacy fragment_count=1 对照。

### 3.2 明确不做

- 不追求生产性能；
- 不实现真实 POSIX locking；
- 不接入 HF model；
- 不实现 controller；
- 不把 Python 调度偶然顺序当协议语义。

## 4. 预期仓库变更

```text
fs_diloco/storage/memory.py
fs_diloco/testing/
  reference_simulator.py
  deterministic_reference.py
  trace.py
  model_checker.py
  crash_matrix.py
  oracles.py
fs_diloco/log/model.py
tests/reference/
  test_reference_transitions.py
  test_random_traces.py
  test_crash_prefixes.py
  test_double_inclusion.py
  test_reference_outer_optim.py
  golden_traces/
```

## 5. 需要先冻结的设计决策

- [ ] D-0201：初版使用 single global head 对所有 fragment commits 全序化；
- [ ] D-0202：CAS 失败后的 proposal 是否立即重新 eligible；
- [ ] D-0203：同 learner/session/base 多 proposal 的 supersession 规则；
- [ ] D-0204：quorum tie-break 和公平性基础规则；
- [ ] D-0205：reference tensor representation 与 tolerance。

每项决策必须写入 `plans/duraloco/DECISIONS.md`，包含：上下文、候选方案、所选方案、拒绝方案、兼容性影响和可逆性。不得把未决语义隐藏在实现细节中。

## 6. Codex 执行循环

### Loop 1 — In-memory storage contract

**目标。** 提供无 I/O 干扰的 immutable put、put-if-absent、conditional replace、get/head/delete 语义。

**先产生的失败证据或规范。**

- [ ] 重复 immutable key 不同 bytes、错误 expected version、missing key、stale CAS。

**实现任务。**

- [ ] 实现版本 token；
- [ ] 实现 operation trace；
- [ ] 支持注入 timeout-before/after-effect；
- [ ] 禁止 listing 参与 commit correctness。

**本循环验证。**

- [ ] contract tests 对所有返回状态穷举；
- [ ] after-effect timeout 重试保持幂等。

**本循环持久化输出。**

- [ ] memory backend；
- [ ] operation history。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 2 — Reference transition system

**目标。** 将 proposal→commit→frontier/head 表达为纯函数状态转换。

**先产生的失败证据或规范。**

- [ ] 为非法 base、重复 inclusion、outer state mismatch、wrong parent 建立 failing traces。

**实现任务。**

- [ ] 定义 immutable SystemState；
- [ ] 实现 eligible/select/prepare/commit/recover；
- [ ] 定义 drop decisions；
- [ ] 输出 state digest。

**本循环验证。**

- [ ] 每个 transition 检查 invariants；
- [ ] 相同 trace 产生相同 digest。

**本循环持久化输出。**

- [ ] reference state machine；
- [ ] transition spec。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 3 — Deterministic optimizer oracle

**目标。** 固定 quorum merge 与 outer optimizer 数值语义。

**先产生的失败证据或规范。**

- [ ] 与 torch reference 的 SGD/momentum/Nesterov/AdamW 对照；
- [ ] fragment_count=1 与 full-vector 对照。

**实现任务。**

- [ ] 实现 float64 CPU reducer/outer step；
- [ ] 明确 weight normalization、staleness 和 token count；
- [ ] 保存 golden tensor digests。

**本循环验证。**

- [ ] 预定义 tolerance 内一致；
- [ ] 输入次序变化不改变 canonical selected order 下结果。

**本循环持久化输出。**

- [ ] optimizer oracle；
- [ ] golden results。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 4 — Trace/model checking

**目标。** 自动探索重复、乱序、crash 和 failover interleavings。

**先产生的失败证据或规范。**

- [ ] 加入一个有意 double-apply 的 mutant，确认 checker 必须失败。

**实现任务。**

- [ ] 定义 trace grammar；
- [ ] 生成 seeded randomized traces；
- [ ] 枚举 crash point 和 restart；
- [ ] 比较恢复状态与合法 committed prefix；
- [ ] 输出最小化失败 trace。

**本循环验证。**

- [ ] 快速 suite 至少覆盖 1,000 seeded traces；
- [ ] 显式/nightly suite 至少 10,000 tiny traces；
- [ ] mutant tests 能检测破坏。

**本循环持久化输出。**

- [ ] model checker CLI；
- [ ] failure minimizer；
- [ ] trace corpus。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

## 7. 不变量与失败注入

### 7.1 本阶段必须维护的不变量

- [ ] committed head 链无分叉；
- [ ] 恢复状态等于某个 committed prefix 的 fold；
- [ ] 每个 proposal 最多一次 logical inclusion；
- [ ] fragment output 与 outer state 由同一 commit 引用；
- [ ] 未成功 CAS 的 prepared objects 不可见为 committed；
- [ ] 相同 trace 与 seed 产生相同 state digest。

### 7.2 必须覆盖的故障与反例

- [ ] crash before/after each storage effect；
- [ ] response lost after successful CAS；
- [ ] duplicate publish；
- [ ] stale CAS；
- [ ] two tentative syncers；
- [ ] wrong parent commit；
- [ ] proposal reorder；
- [ ] recovery from every prefix。

## 8. 验收标准

以下条件是阶段 gate，不是建议。Maker 必须给出命令、退出码和 artifact 路径；Checker 必须逐项复核。

- [ ] P02-A01：reference simulator 不依赖 torch、HF、filesystem 或网络；
- [ ] P02-A02：每个 transition 自动检查 invariant catalog；
- [ ] P02-A03：所有 crash traces 恢复到旧或新合法 prefix；
- [ ] P02-A04：double logical inclusion 为零；
- [ ] P02-A05：故意注入的 double-apply、wrong-parent、state-pairing mutants 被测试捕获；
- [ ] P02-A06：外部 optimizer reference 与 legacy fragment_count=1 在 numeric contract 内一致；
- [ ] P02-A07：失败 trace 可稳定复现并最小化；
- [ ] P02-A08：Checker 独立构造一个 interleaving 反例。

## 9. 验证矩阵

| 层级 | 要求 |
|---|---|
| 本地 unit/reference | 必须；本阶段的主要 gate。 |
| Miyabi login | 只做静态同步检查。 |
| Miyabi 1-node | 不要求 GPU；若本地缺依赖，可在 compute node 运行完整 reference suite。 |
| 多节点 | 不要求；并发由 deterministic trace 模拟。 |

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

- [ ] 参考语义调整由 agent 记录 ADR、golden trace 和兼容性影响，经 Checker 复核后生效。
- [ ] P02 必需 gate 通过后自动进入 P03，无需人工审核。

## 12. 阻塞与停止规则

- 同一根因连续三次修复后仍未通过同一 gate：写入 `BLOCKERS.md` 并停止扩大改动。
- 若实现当前目标需要调整 research contract、failure model、协议线性化点或数值语义：agent 记录 ADR 和 oracle 证据，经 Checker 复核后继续；只有 materially 超出用户授权研究目标时才停止请求决策。
- 需要在 Miyabi 登录节点运行被禁止的 runtime 命令：停止，转为 PBS allocation。
- 单个 Miyabi 作业可由 agent 自主决定并提交（`select<=16`、`walltime<=02:00:00`，包括 9 节点）；超出该范围或需要付费公共云资源时停止并取得明确批准。
- 发现基础分支包含未合并的用户改动或基线漂移：保留改动，生成 drift report，不得覆盖。

## 13. 阶段完成报告模板

报告 trace 数、event/crash point 覆盖、mutant kill rate、reference digests、任何无法满足的 invariant。

## 14. 可直接复制给 Codex 的启动指令

```text
使用 miyabi-development skill 执行 P02。

仓库：https://github.com/UnbearableFate/fs_based_decoupled_diloco
规划基线：codex/fs-diloco-miyabi @ afc50a1e179c64321645b278b2497ea3ab3fe24d
目标分支：codex/duraloco-p02-reference-model
阶段计划：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/03_P02_REFERENCE_SIMULATOR_AND_IN_MEMORY_BACKEND.md
共同契约：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/00_CODEX_LOOP_OPERATING_CONTRACT.md

先执行 hostname、git status --short --branch、git rev-parse HEAD，并读取 AGENTS.md、共同契约、当前阶段文件、上一阶段报告和相关研究草稿。若基线漂移，先写 drift report；不要 reset 用户改动。

按阶段文件中的 Loop 顺序工作。每个 Loop 都要先建立失败测试或可执行规范，再做最小实现，随后运行分层验证和独立 checker。持续更新 plans/duraloco/STATE.yaml；不要自动合并 main；不要在 Miyabi 登录节点运行 pytest、torch/transformers/datasets 导入、训练、mpirun 或其他 runtime 工作。

结束时在全部必需 gate 有证据且 Checker 通过时标记 completed，并按依赖图自动启动下一个可执行 goal/phase，不等待用户审核；否则输出 BLOCKED，并给出最小复现、已尝试方案和下一项决策。
```

## 15. 参考输入

- `references/DuraLoCo_research_draft_zh.md`
- 现有实现：`https://github.com/UnbearableFate/fs_based_decoupled_diloco/tree/codex/fs-diloco-miyabi`
- Miyabi skill：`https://github.com/UnbearableFate/miyabi-development`
