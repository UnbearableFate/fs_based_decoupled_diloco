---
plan_id: "P07"
title: "Compaction、Reachability GC、Ack 与 Learner Capsules"
status: "planned"
date: "2026-07-10"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/fs-diloco-miyabi"
planning_basis_commit: "afc50a1e179c64321645b278b2497ea3ab3fe24d"
target_branch: "codex/duraloco-p07-lifecycle"
depends_on:
  - "P06"
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
agent_decision_gates:
  - "exact learner capsule 的存储预算/频率默认值由 agent 在自主资源范围和有界增长证据内决定，经独立 Checker 复核。"
human_approval_gates:
  - "启用任何非 dry-run GC 前必须人工批准；"
---

# P07 — Compaction、Reachability GC、Ack 与 Learner Capsules

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

使 durable log 长期运行时空间有界，并提供安全恢复边界。实现 compaction snapshot、reachability/pinning、ack/watermark、orphan grace 和 exact learner capsule。

### 1.1 本阶段支撑的研究主张

DuraLoCo 可以将 committed update log 用作全局 checkpoint，同时通过可证明的 reachability GC 控制长期存储；exact learner recovery 通过独立低频 capsule 实现，而不是错误地把 fragment proposal 当完整 checkpoint。

### 1.2 完成后的系统增量

新增 global snapshot+suffix recovery、GC dry-run/apply、learner ack/watermark、capsule save/restore 和并发恢复测试。

## 2. 前置条件

- [ ] P04 committed log 稳定；
- [ ] P06 learner state/cursor hooks 存在；
- [ ] storage prefix 完全隔离；
- [ ] 定义 pinned experiments/replay policy。

## 3. 范围

### 3.1 必须完成

- [ ] compaction snapshot 包含 fragment+outer state+frontier/consumption digest；
- [ ] snapshot commit/pin；
- [ ] suffix replay；
- [ ] reachability graph；
- [ ] ack/watermark；
- [ ] orphan/expired/superseded proposal lifecycle；
- [ ] GC mark/report/apply；
- [ ] concurrent restore/GC safety；
- [ ] learner capsule：model local state、inner optimizer、scheduler/scaler、RNG、data cursor、interval state；
- [ ] accelerated bounded-storage soak。

### 3.2 明确不做

- 不立即运行 72h 正式 soak；
- 不删除用户历史 run；
- 不做跨 provider archival policy；
- 不把 capsule 频率自动调优。

## 4. 预期仓库变更

```text
fs_diloco/log/
  snapshot.py
  compaction.py
  reachability.py
  gc.py
  pins.py
  acknowledgements.py
fs_diloco/learner_v2/
  capsule.py
  exact_recovery.py
fs_diloco/duraloco_cli/
  gc.py
  snapshot.py
  restore.py
tests/lifecycle/
  test_snapshot_suffix_replay.py
  test_reachability.py
  test_gc_dry_run.py
  test_gc_restore_race.py
  test_capsule_roundtrip.py
  test_capsule_crash.py
  test_bounded_growth.py
```

`fs_diloco/cli.py` 保持现有 dispatcher 兼容；不得创建同名 `fs_diloco/cli/` package。新增 lifecycle 命令放入 `duraloco_cli`，再通过显式 project entrypoint 或现有 dispatcher 子命令暴露。

## 5. 需要先冻结的设计决策

- [ ] D-0701：snapshot 是 log 中的 commit event 还是 side index + pin；
- [ ] D-0702：ack 的语义是 learner observed、durably adopted 或 no-longer-needs；
- [ ] D-0703：inactive learner 是否阻止 GC；
- [ ] D-0704：orphan grace、quarantine retention 和 replay pin；
- [ ] D-0705：capsule consistency point 与未决 proposal 的处理；
- [ ] D-0706：GC 操作的二阶段 mark/apply 与审批 token。

每项决策必须写入 `plans/duraloco/DECISIONS.md`，包含：上下文、候选方案、所选方案、拒绝方案、兼容性影响和可逆性。不得把未决语义隐藏在实现细节中。

## 6. Codex 执行循环

### Loop 1 — Snapshot 与 suffix recovery

**目标。** 从最近 snapshot + committed suffix 恢复相同 global state。

**先产生的失败证据或规范。**

- [ ] snapshot 写到一半；head 前进并发；snapshot ref corrupt。

**实现任务。**

- [ ] 定义 snapshot manifest；
- [ ] 写 immutable state；
- [ ] 绑定 covered commit；
- [ ] 恢复选择最新合法 reachable snapshot；
- [ ] 回放 suffix。

**本循环验证。**

- [ ] snapshot/no snapshot state digest 相同；
- [ ] crash 后旧 snapshot 仍可用；
- [ ] corrupt snapshot fallback。

**本循环持久化输出。**

- [ ] snapshot/restore；
- [ ] compaction report。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 2 — Ack、watermark 与 reachability

**目标。** 明确哪些 proposal/objects 对 active learners、restore points 和 experiments 仍可达。

**先产生的失败证据或规范。**

- [ ] 慢/掉线 learner；pinned replay；frontier 与 capsule 引用旧 fragment。

**实现任务。**

- [ ] 定义 ack record；
- [ ] 计算 per learner/fragment watermarks；
- [ ] 构建 object graph；
- [ ] 生成解释性 reachability report。

**本循环验证。**

- [ ] 每个 live object 有引用路径；
- [ ] 每个 candidate delete 有原因和 grace。

**本循环持久化输出。**

- [ ] reachability engine；
- [ ] ack APIs。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 3 — 安全 GC

**目标。** 默认 dry-run，只有不可达且过 grace 的对象可删除。

**先产生的失败证据或规范。**

- [ ] GC 与 restore、commit、capsule upload 并发；delete response loss；list omission。

**实现任务。**

- [ ] mark generation；
- [ ] revalidate head/epoch；
- [ ] batch delete idempotency；
- [ ] tombstone/audit report；
- [ ] 审批 token。

**本循环验证。**

- [ ] 并发 tests 零 live deletion；
- [ ] 重复 GC 幂等；
- [ ] listing omission 不误删。

**本循环持久化输出。**

- [ ] GC CLI；
- [ ] dry-run/apply reports。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 4 — Learner capsule exact recovery

**目标。** 恢复 learner inner state 与 data/RNG cursor。

**先产生的失败证据或规范。**

- [ ] capsule before/after proposal/adoption crash；optimizer/model mismatch；partial upload。

**实现任务。**

- [ ] 序列化 model-local/inner optimizer/scheduler/scaler/RNG/data/interval；
- [ ] content hashes；
- [ ] capsule manifest/pin；
- [ ] restore validation；
- [ ] 与 warm restart 对照。

**本循环验证。**

- [ ] deterministic tiny continuation 在 numeric contract 内；
- [ ] 坏 capsule fail closed；
- [ ] 未决 proposal 规则一致。

**本循环持久化输出。**

- [ ] capsule pipeline；
- [ ] exact recovery report。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 5 — Accelerated soak

**目标。** 在短时间高事件率下验证对象数量和字节达到稳态。

**先产生的失败证据或规范。**

- [ ] 关闭 GC 产生线性增长作为对照。

**实现任务。**

- [ ] 构造大量 tiny commits/proposals/snapshots；
- [ ] 周期 compaction/GC；
- [ ] 记录 live/orphan/deleted counts。

**本循环验证。**

- [ ] 启用 lifecycle 后 steady-state 有界；
- [ ] 无 live deletion；
- [ ] 恢复任一 pinned point。

**本循环持久化输出。**

- [ ] soak traces；
- [ ] growth plots raw data。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

## 7. 不变量与失败注入

### 7.1 本阶段必须维护的不变量

- [ ] GC 只删除从当前 head、合法 snapshot、active capsule、pin 和 grace roots 均不可达的对象；
- [ ] snapshot 覆盖 prefix 与 suffix 连续；
- [ ] exact capsule 的 model/optimizer/RNG/data/interval 属于同一 consistency point；
- [ ] ack 不被误解释为 proposal 已提交；
- [ ] 所有 delete 可审计且幂等；
- [ ] 默认 GC dry-run。

### 7.2 必须覆盖的故障与反例

- [ ] snapshot partial/crash；
- [ ] GC mark/apply crash；
- [ ] head moves during GC；
- [ ] restore races GC；
- [ ] list omission；
- [ ] delete timeout after effect；
- [ ] capsule partial/corrupt；
- [ ] inactive/reactivated learner。

## 8. 验收标准

以下条件是阶段 gate，不是建议。Maker 必须给出命令、退出码和 artifact 路径；Checker 必须逐项复核。

- [ ] P07-A01：snapshot+suffix 与 full replay digest 一致；
- [ ] P07-A02：reachability report 可解释每个 live/candidate object；
- [ ] P07-A03：并发 GC/restore/commit tests 零 live deletion；
- [ ] P07-A04：GC 默认 dry-run，apply 需要显式 approval token；
- [ ] P07-A05：delete response loss 重试幂等；
- [ ] P07-A06：learner capsule exact tiny continuation 通过；
- [ ] P07-A07：warm/exact recovery 语义和成本分开报告；
- [ ] P07-A08：accelerated soak 显示有界 steady-state；
- [ ] P07-A09：Checker 独立审查 reachability roots。
- [ ] P07-A10：现有 `fs_diloco.cli` dispatcher 未被 package shadow，新增 lifecycle CLI 的 entrypoint/import 兼容测试通过。

## 9. 验证矩阵

| 层级 | 要求 |
|---|---|
| 本地 | lifecycle unit、concurrent stress、accelerated soak。 |
| Miyabi 1-node | snapshot/restore/capsule real filesystem + tiny model。 |
| Miyabi 2-node | GC 与 learner/syncer/restore 并发；仅隔离 prefix，GC dry-run 默认。 |
| 长时间/9-node | 9-node 与不超过 2 小时的作业由 agent 自主决定；累计 24/72h soak 延后 P12，以可恢复的 ≤2h segments 自动续接；只有单次连续 >2h 才需外部资源批准。 |

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

## 11. 自动推进与外部风险审批门

- [ ] 启用任何非 dry-run GC 前必须人工批准；
- [ ] exact learner capsule 的存储预算/频率默认值由 agent 在自主资源范围和有界增长证据内决定，经 Checker 复核后生效；
- [ ] P07 必需 correctness gates 可用 GC dry-run 证据完成；未获 destructive apply 批准不阻止 phase `completed`。P08/P09 也完成并通过集成 Checker 后自动进入 P10。

## 12. 阻塞与停止规则

- 同一根因连续三次修复后仍未通过同一 gate：写入 `BLOCKERS.md` 并停止扩大改动。
- 若实现当前目标需要调整 research contract、failure model、协议线性化点或数值语义：agent 记录 ADR、reachability proof 和恢复影响，经 Checker 复核后继续；只有 materially 超出用户授权研究目标或需要 destructive apply 时才停止请求决策。
- 需要在 Miyabi 登录节点运行被禁止的 runtime 命令：停止，转为 PBS allocation。
- 单个 Miyabi 作业可由 agent 自主决定并提交（`select<=16`、`walltime<=02:00:00`，包括 9 节点）；超出该范围或需要付费公共云资源时停止并取得明确批准。
- 发现基础分支包含未合并的用户改动或基线漂移：保留改动，生成 drift report，不得覆盖。

## 13. 阶段完成报告模板

报告 snapshot covered seq、suffix 长度、reachability roots、候选/实际删除、capsule bytes/RTO、bounded-growth 数据和 GC 审批状态。

## 14. 可直接复制给 Codex 的启动指令

```text
使用 miyabi-development skill 执行 P07。

仓库：https://github.com/UnbearableFate/fs_based_decoupled_diloco
规划基线：codex/fs-diloco-miyabi @ afc50a1e179c64321645b278b2497ea3ab3fe24d
目标分支：codex/duraloco-p07-lifecycle
阶段计划：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/08_P07_COMPACTION_GC_ACKS_AND_LEARNER_CAPSULES.md
共同契约：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/00_CODEX_LOOP_OPERATING_CONTRACT.md

先执行 hostname、git status --short --branch、git rev-parse HEAD，并读取 AGENTS.md、共同契约、当前阶段文件、上一阶段报告和相关研究草稿。若基线漂移，先写 drift report；不要 reset 用户改动。

按阶段文件中的 Loop 顺序工作。每个 Loop 都要先建立失败测试或可执行规范，再做最小实现，随后运行分层验证和独立 checker。持续更新 plans/duraloco/STATE.yaml；不要自动合并 main；不要在 Miyabi 登录节点运行 pytest、torch/transformers/datasets 导入、训练、mpirun 或其他 runtime 工作。

结束时在全部必需 gate 有证据且 Checker 通过时标记 completed，并按依赖图自动启动下一个可执行 goal/phase，不等待用户审核；否则输出 BLOCKED，并给出最小复现、已尝试方案和下一项决策。
```

## 15. 参考输入

- `references/DuraLoCo_research_draft_zh.md`
- 现有实现：`https://github.com/UnbearableFate/fs_based_decoupled_diloco/tree/codex/fs-diloco-miyabi`
- Miyabi skill：`https://github.com/UnbearableFate/miyabi-development`
