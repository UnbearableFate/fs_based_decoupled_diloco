---
plan_id: "P06"
title: "Learner Contribution Intervals、Adoption 与 Warm Recovery"
status: "planned"
date: "2026-07-10"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/fs-diloco-miyabi"
planning_basis_commit: "afc50a1e179c64321645b278b2497ea3ab3fe24d"
target_branch: "codex/duraloco-p06-learner-protocol"
depends_on:
  - "P05"
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
agent_decision_gates:
  - "inner optimizer adoption policy 默认值由 agent 基于 numeric/recovery evidence 决定并经独立 Checker 复核；"
  - "v2 learner/syncer 默认训练路径在兼容性和 1/2-node gates 通过后由 agent 自动 promotion。"
human_approval_gates: []
---

# P06 — Learner Contribution Intervals、Adoption 与 Warm Recovery

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

让 learner 产生因果边界清晰、不可重叠、可幂等重发的 proposal；global fragment adoption 只能在 interval 边界发生。完成 session/sequence、base freeze、warm restart、全局 stop 和数据/RNG cursor hooks。

### 1.1 本阶段支撑的研究主张

DuraLoCo 的 selected proposal 表示一段唯一 local work，而不是可能重复包含已应用训练进展的任意参数快照；learner crash 最多损失未提交 interval，并能从 committed frontier warm restart。

### 1.2 完成后的系统增量

现有 learner 可在 protocol v2 模式发布 durable proposal、轮询 committed head、采用新 fragments，并与 v2 syncer 完成 end-to-end small run。

## 2. 前置条件

- [ ] v2 syncer transactional path 可运行；
- [ ] proposal payload kind 已冻结；
- [ ] fragment schedule 初版定义；
- [ ] warm restart 的非精确性已在 research contract 中明确。

## 3. 范围

### 3.1 必须完成

- [ ] learner_session_id 与 durable monotonic sequence；
- [ ] interval base/frontier freeze；
- [ ] local work token/step accounting；
- [ ] proposal payload/content publication；
- [ ] response-loss/idempotent retry；
- [ ] global adoption 仅在 interval boundary；
- [ ] per-fragment base vector/cursor；
- [ ] warm restart；
- [ ] global stop 优先级；
- [ ] inner optimizer adoption policies 与实验标记；
- [ ] RNG/data cursor 抽象 hooks。

### 3.2 明确不做

- 不实现 exact learner capsule；
- 不实现 lazy streaming dataset 完整重构，除非为 cursor 正确性所需；
- 不实现 SACC 动态 local interval；
- 不保证 warm restart bitwise continuation。

## 4. 预期仓库变更

```text
fs_diloco/learner_v2/
  __init__.py
  runtime.py
  session.py
  interval.py
  proposal.py
  publication.py
  adoption.py
  recovery.py
  data_cursor.py
  rng_state.py
fs_diloco/legacy/learner_v1.py
tests/learner_v2/
  test_interval_base_freeze.py
  test_sequence_idempotency.py
  test_boundary_adoption.py
  test_warm_restart.py
  test_stop_priority.py
  test_inner_optimizer_policy.py
```

不得同时保留 `fs_diloco/learner.py` 和创建同名 `fs_diloco/learner/` package。现有 `fs_diloco.learner:main` entrypoint 必须保持兼容：P06 使用无冲突的 `learner_v2` package，并由现有 `learner.py` 在明确 promotion gate 后作为 dispatcher；在此之前默认仍走 legacy v1。

## 5. 需要先冻结的设计决策

- [ ] D-0601：proposal 是 pseudo-gradient 还是 local end weight；
- [ ] D-0602：同 session/base 的 superseding proposal 是否允许；
- [ ] D-0603：fragment schedule 是 committed round-robin、acceptable set 还是 learner-local cursor；
- [ ] D-0604：inner optimizer reset-all/reset-fragment/preserve 的默认策略；
- [ ] D-0605：target token 计数定义；
- [ ] D-0606：session sequence 的 durable location。

每项决策必须写入 `plans/duraloco/DECISIONS.md`，包含：上下文、候选方案、所选方案、拒绝方案、兼容性影响和可逆性。不得把未决语义隐藏在实现细节中。

## 6. Codex 执行循环

### Loop 1 — Session、sequence 与 interval

**目标。** 每段 local work 具有唯一、持久、不可重叠身份。

**先产生的失败证据或规范。**

- [ ] learner restart 后 seq 重用；interval 中途采用 global；同一 tokens 被两个 proposal 声明。

**实现任务。**

- [ ] 实现 session state；
- [ ] freeze base frontier/vector；
- [ ] 记录 start/end token cursor；
- [ ] proposal identity 绑定 interval。

**本循环验证。**

- [ ] restart 创建新 session 或安全继续 seq；
- [ ] interval boundaries 不重叠；
- [ ] base 在 interval 内不可变。

**本循环持久化输出。**

- [ ] session/interval modules；
- [ ] lineage log。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 2 — Proposal publication

**目标。** payload + manifest 在 timeout/重复提交下幂等。

**先产生的失败证据或规范。**

- [ ] payload 成功响应丢失；manifest 重发；same ID conflicting payload。

**实现任务。**

- [ ] 使用 storage API immutable puts；
- [ ] 先 payload 后 manifest；
- [ ] 保存 local publication state；
- [ ] 冲突 fail closed。

**本循环验证。**

- [ ] 任意 publication crash 重启后最多一个 canonical proposal；
- [ ] syncer 可验证/消费。

**本循环持久化输出。**

- [ ] publication pipeline；
- [ ] crash tests。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 3 — Boundary adoption 与 optimizer policy

**目标。** 采用 committed fragments 不污染正在形成的 proposal 因果边界。

**先产生的失败证据或规范。**

- [ ] inner step polling 时 head 变化；多个 fragment 版本变化；optimizer state policy 差异。

**实现任务。**

- [ ] 只在 boundary adopt；
- [ ] 记录 adopted frontier；
- [ ] 实现并标记 reset-all/reset-updated-fragment/preserve；
- [ ] scheduler/scaler hooks。

**本循环验证。**

- [ ] interval metadata 与实际 base digest 一致；
- [ ] 未更新 fragment state 策略符合配置；
- [ ] 策略进入 run manifest。

**本循环持久化输出。**

- [ ] adoption module；
- [ ] policy ablation hooks。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 4 — Warm restart 与 stop

**目标。** learner crash 后从 committed global state 恢复，不误称 exact continuation。

**先产生的失败证据或规范。**

- [ ] kill before/after proposal publish/adoption；global stop 与 local budget 冲突。

**实现任务。**

- [ ] 恢复 model/frontier/session metadata；
- [ ] 丢弃或重发未完成 interval 的明确规则；
- [ ] global stop 优先；
- [ ] 记录 lost/repeated token estimate。

**本循环验证。**

- [ ] warm restart 可继续提交；
- [ ] stop 后不继续无界训练；
- [ ] 报告恢复语义和 lost work。

**本循环持久化输出。**

- [ ] warm recovery；
- [ ] stop tests；
- [ ] 1/2-node E2E。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

## 7. 不变量与失败注入

### 7.1 本阶段必须维护的不变量

- [ ] 一个 proposal 对应一个不可变 base 和一个非重叠 interval；
- [ ] session+sequence 不重复映射到不同内容；
- [ ] adoption 不发生在 interval 内部；
- [ ] global stop 优先于本地 max step；
- [ ] warm restart 不宣称恢复 inner optimizer/RNG/data exact state；
- [ ] proposal token count 使用冻结定义。

### 7.2 必须覆盖的故障与反例

- [ ] crash before/after payload、manifest、ack；
- [ ] restart sequence reuse；
- [ ] head changes mid-interval；
- [ ] multiple fragment updates；
- [ ] global stop race；
- [ ] same ID conflicting payload；
- [ ] slow learner stale proposal。

## 8. 验收标准

以下条件是阶段 gate，不是建议。Maker 必须给出命令、退出码和 artifact 路径；Checker 必须逐项复核。

- [ ] P06-A01：interval base freeze 有自动测试；
- [ ] P06-A02：session/sequence 在 restart 下无冲突；
- [ ] P06-A03：proposal publication 对 response loss 幂等；
- [ ] P06-A04：adoption 只发生于 boundary；
- [ ] P06-A05：三种 optimizer policy 行为被测试并写入 manifest；
- [ ] P06-A06：global stop 在设置 local budget 时仍生效；
- [ ] P06-A07：warm restart 能继续训练且明确记录 lost/repeated work；
- [ ] P06-A08：fragment_count=1 与 full/reference 在 numeric contract 内一致；
- [ ] P06-A09：Miyabi 1-node real path ≤10 step finite；
- [ ] P06-A10：2-node learner+syncer v2 E2E。
- [ ] P06-A11：`fs-diloco-learner` 和 `python -m fs_diloco.learner` 的 legacy/default 行为及 v2 显式选择均通过入口兼容测试。

## 9. 验证矩阵

| 层级 | 要求 |
|---|---|
| 本地 | interval/publication/restart tests；tiny synthetic E2E。 |
| Miyabi 1-node | 必须：真实 model/data ≤10 optimizer steps，finite loss，至少一个 v2 commit/adoption。 |
| Miyabi 2-node | 必须：syncer 与 learner 分节点，proposal→commit→adopt→stop。 |
| 9-node | 尚不要求。 |

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

- [ ] inner optimizer adoption policy 默认值由 agent 按 numeric/recovery evidence 决定，记录 ADR 和 manifest，经 Checker 复核后生效；
- [ ] v2 learner/syncer 兼容性和 1/2-node gates 通过后由 agent 自动设为默认训练路径；
- [ ] P06 必需 gate 通过后，按依赖图自动启动 P07、P08、P09；无需人工审核。

## 12. 阻塞与停止规则

- 同一根因连续三次修复后仍未通过同一 gate：写入 `BLOCKERS.md` 并停止扩大改动。
- 若实现当前目标需要调整 research contract、failure model、协议线性化点或数值语义：agent 记录 ADR、numeric/recovery evidence 和兼容性影响，经 Checker 复核后继续；只有 materially 超出用户授权研究目标时才停止请求决策。
- 需要在 Miyabi 登录节点运行被禁止的 runtime 命令：停止，转为 PBS allocation。
- 单个 Miyabi 作业可由 agent 自主决定并提交（`select<=16`、`walltime<=02:00:00`，包括 9 节点）；超出该范围或需要付费公共云资源时停止并取得明确批准。
- 发现基础分支包含未合并的用户改动或基线漂移：保留改动，生成 drift report，不得覆盖。

## 13. 阶段完成报告模板

报告 sessions、interval lineage、proposal IDs、adopted frontiers、warm restart lost/repeated tokens、optimizer policy、1/2-node run IDs。

## 14. 可直接复制给 Codex 的启动指令

```text
使用 miyabi-development skill 执行 P06。

仓库：https://github.com/UnbearableFate/fs_based_decoupled_diloco
规划基线：codex/fs-diloco-miyabi @ afc50a1e179c64321645b278b2497ea3ab3fe24d
目标分支：codex/duraloco-p06-learner-protocol
阶段计划：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/07_P06_LEARNER_INTERVALS_ADOPTION_AND_RECOVERY.md
共同契约：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/00_CODEX_LOOP_OPERATING_CONTRACT.md

先执行 hostname、git status --short --branch、git rev-parse HEAD，并读取 AGENTS.md、共同契约、当前阶段文件、上一阶段报告和相关研究草稿。若基线漂移，先写 drift report；不要 reset 用户改动。

按阶段文件中的 Loop 顺序工作。每个 Loop 都要先建立失败测试或可执行规范，再做最小实现，随后运行分层验证和独立 checker。持续更新 plans/duraloco/STATE.yaml；不要自动合并 main；不要在 Miyabi 登录节点运行 pytest、torch/transformers/datasets 导入、训练、mpirun 或其他 runtime 工作。

结束时在全部必需 gate 有证据且 Checker 通过时标记 completed，并按依赖图自动启动下一个可执行 goal/phase，不等待用户审核；否则输出 BLOCKED，并给出最小复现、已尝试方案和下一项决策。
```

## 15. 参考输入

- `references/DuraLoCo_research_draft_zh.md`
- 现有实现：`https://github.com/UnbearableFate/fs_based_decoupled_diloco/tree/codex/fs-diloco-miyabi`
- Miyabi skill：`https://github.com/UnbearableFate/miyabi-development`
