---
plan_id: "P05"
title: "生产 Syncer 集成、Lease/Fencing 与 Failover"
status: "planned"
date: "2026-07-10"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/fs-diloco-miyabi"
planning_basis_commit: "afc50a1e179c64321645b278b2497ea3ab3fe24d"
target_branch: "codex/duraloco-p05-syncer-failover"
depends_on:
  - "P04"
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
agent_decision_gates:
  - "v2 syncer 默认写路径在兼容性、迁移、1/2-node gates 和独立 Checker 通过后由 agent 自动 promotion。"
human_approval_gates:
  - "任何 destructive migration/旧 run conversion 需要批准。"
---

# P05 — 生产 Syncer 集成、Lease/Fencing 与 Failover

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

把现有 syncer 的发现、选择、merge、outer step 和发布迁移到 transactional fragment log，并加入 lease/fencing、standby takeover、启动 reconciliation 和明确 stop state。SQLite 仅保留为可重建 cache。

### 1.1 本阶段支撑的研究主张

syncer 不再是持有不可恢复本地状态的单点；在进程崩溃或 leader 切换后，新实例仅凭 durable log 恢复，并且旧 leader 无法以低 epoch 推进 head。

### 1.2 完成后的系统增量

新增 v2 syncer runtime，可通过配置与 legacy v1 并存；支持 synthetic production path、双 syncer chaos 和 failover。

## 2. 前置条件

- [ ] P04 log correctness 通过；
- [ ] P03 Miyabi CAS contract 通过；
- [ ] 明确 lease 时钟/TTL failure assumptions；
- [ ] 保留 legacy configs 用作回归。

## 3. 范围

### 3.1 必须完成

- [ ] syncer ingest 使用 P01 validator/quarantine；
- [ ] quorum selection 与 commit pipeline 解耦；
- [ ] lease acquisition/renewal、monotonic fencing epoch；
- [ ] head commit 检查 epoch；
- [ ] standby startup replay/cache rebuild；
- [ ] 取消持久 `selected` 状态；
- [ ] stop/request/terminal 状态通过 log 提交；
- [ ] 可控 failpoints；
- [ ] v1 legacy 与 v2 config namespace。

### 3.2 明确不做

- 不完成 learner v2 publication/adoption；可用 test producer；
- 不实现 compaction/GC；
- 不实现 SACC；
- 不自动迁移旧 run。

## 4. 预期仓库变更

```text
fs_diloco/syncer_v2/
  __init__.py
  runtime.py
  ingest.py
  selection.py
  commit_pipeline.py
  recovery.py
  stop_state.py
fs_diloco/coordination/
  lease.py
  fencing.py
  clock.py
fs_diloco/legacy/
  syncer_v1.py
tests/syncer_v2/
  test_ingest_quarantine.py
  test_commit_pipeline.py
  test_lease_fencing.py
  test_takeover.py
  test_stop_recovery.py
scripts/chaos/
  run_dual_syncer.py
```

不得同时保留 `fs_diloco/syncer.py` 和创建同名 `fs_diloco/syncer/` package。现有 `fs_diloco.syncer:main` entrypoint 必须保持兼容：P05 使用无冲突的 `syncer_v2` package，并由现有 `syncer.py` 在明确 promotion gate 后作为 dispatcher；在此之前默认仍走 legacy v1。

## 5. 需要先冻结的设计决策

- [ ] D-0501：lease 使用 backend conditional object，epoch 如何单调分配；
- [ ] D-0502：clock skew 假设和 lease safety/liveness 分界；
- [ ] D-0503：旧 leader 在 lease 过期后如何被 head CAS fencing；
- [ ] D-0504：stop 作为 commit event 还是 head metadata；
- [ ] D-0505：legacy/v2 runtime selection 和 run namespace 隔离。

每项决策必须写入 `plans/duraloco/DECISIONS.md`，包含：上下文、候选方案、所选方案、拒绝方案、兼容性影响和可逆性。不得把未决语义隐藏在实现细节中。

## 6. Codex 执行循环

### Loop 1 — Syncer 模块化与 v2 ingest

**目标。** 将当前 monolithic syncer 分解，并让所有候选通过 Protocol v2 validator。

**先产生的失败证据或规范。**

- [ ] 坏 proposal、future base、重复 identity 不应终止 runtime。

**实现任务。**

- [ ] 提取 ingest/selection/commit/recovery；
- [ ] 引入 typed event log；
- [ ] SQLite 改 cache；
- [ ] 保留 v1 entrypoint。

**本循环验证。**

- [ ] legacy tests 仍通过；
- [ ] v2 invalid corpus 被 quarantine；
- [ ] 删除 cache 后重启。

**本循环持久化输出。**

- [ ] syncer package；
- [ ] compatibility matrix。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 2 — Lease 与 fencing

**目标。** 在两个 syncer 存活时只有当前 epoch 可以推进 head。

**先产生的失败证据或规范。**

- [ ] 双实例同时 acquire；旧 leader pause 后恢复；lease renew response lost。

**实现任务。**

- [ ] 实现 acquire/renew/release；
- [ ] epoch 写入 lease、commit、head；
- [ ] commit 前后验证 fencing；
- [ ] 记录 owner/session。

**本循环验证。**

- [ ] 双 syncer 至多一个 active writer；
- [ ] 旧 epoch CAS 永远失败；
- [ ] standby 最终可 takeover。

**本循环持久化输出。**

- [ ] lease/fencing module；
- [ ] dual-syncer trace。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 3 — Crash-recoverable runtime

**目标。** 在每个 syncer pipeline stage kill 后自动 reconcile。

**先产生的失败证据或规范。**

- [ ] kill ingest/compute/output/record/frontier/pre/post CAS；
- [ ] 删除本地 SQLite。

**实现任务。**

- [ ] 启动 replay；
- [ ] 识别已提交 response-loss；
- [ ] 忽略/记录 orphan；
- [ ] 重建 metrics/cache；
- [ ] 去除 selected-stuck state。

**本循环验证。**

- [ ] 所有 kill points 无永久 selected；
- [ ] 恢复后 state digest 与 reference 一致；
- [ ] 下一 commit 可继续。

**本循环持久化输出。**

- [ ] recovery path；
- [ ] failpoint suite。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 4 — Stop 与操作 CLI

**目标。** 使停止、完成、故障和 operator shutdown 可区分、可恢复。

**先产生的失败证据或规范。**

- [ ] stop commit 前后 crash；本地 budget 与 global stop 冲突。

**实现任务。**

- [ ] 定义 stop event/state；
- [ ] 实现 request/observe/ack；
- [ ] 增加 inspect/takeover CLI；
- [ ] 日志中打印 epoch/head/run。

**本循环验证。**

- [ ] 重启后 stop 不丢失；
- [ ] 未授权旧 leader 不能覆盖 stop；
- [ ] 状态原因明确。

**本循环持久化输出。**

- [ ] stop state machine；
- [ ] operator commands。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

## 7. 不变量与失败注入

### 7.1 本阶段必须维护的不变量

- [ ] 任何 head advance 的 fencing_epoch 不低于当前 lease epoch；
- [ ] 过期/旧 leader 不能 commit；
- [ ] SQLite/cache 丢失不改变 authority；
- [ ] 没有 durable `selected` 中间状态；
- [ ] stop 状态可从 log 恢复；
- [ ] 所有 proposal 先验证再选择。

### 7.2 必须覆盖的故障与反例

- [ ] two syncers simultaneous start；
- [ ] leader pause beyond TTL then resume；
- [ ] renew response loss；
- [ ] leader kill every stage；
- [ ] cache deletion/corruption；
- [ ] bad/future proposal flood；
- [ ] stop before/after CAS crash。

## 8. 验收标准

以下条件是阶段 gate，不是建议。Maker 必须给出命令、退出码和 artifact 路径；Checker 必须逐项复核。

- [ ] P05-A01：v2 syncer 所有 apply 通过 P04 commit API；
- [ ] P05-A02：SQLite 仅为 cache，删除后可恢复；
- [ ] P05-A03：双 syncer 测试无 split-brain；
- [ ] P05-A04：旧 epoch commit 全部被拒；
- [ ] P05-A05：每个 failpoint 后无永久 selected 更新；
- [ ] P05-A06：stop reason 与 terminal state 可重启恢复；
- [ ] P05-A07：legacy v1 默认路径在 v2 promotion gate 通过前保持可用；
- [ ] P05-A08：Miyabi 2-node takeover 有 run artifact；
- [ ] P05-A09：Checker 审查 lease/fencing 的 clock assumptions。
- [ ] P05-A10：`fs-diloco-syncer` 和 `python -m fs_diloco.syncer` 的 legacy/default 行为及 v2 显式选择均通过入口兼容测试。

## 9. 验证矩阵

| 层级 | 要求 |
|---|---|
| 本地 | unit、dual process、kill matrix 必须。 |
| Miyabi login | branch/config/script static only。 |
| Miyabi 1-node | v2 synthetic syncer + test producers；实际 GPU outer path targeted。 |
| Miyabi 2-node | 必须：leader/standby、kill/takeover、旧 leader 恢复；≤10 分钟。 |
| 9-node | 不要求。 |

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

- [ ] v2 syncer 的兼容性、迁移、1/2-node 和 Checker gates 通过后由 agent 自动设为默认写路径，无需人工审核；
- [ ] 任何 destructive migration/旧 run conversion 需要批准。
- [ ] P05 必需 gate 通过后自动进入 P06；未获 destructive migration 批准时保留旧 run，不阻止新 namespace 的后续阶段。

## 12. 阻塞与停止规则

- 同一根因连续三次修复后仍未通过同一 gate：写入 `BLOCKERS.md` 并停止扩大改动。
- 若实现当前目标需要调整 research contract、failure model、协议线性化点或数值语义：agent 记录 ADR、migration impact 和 failover evidence，经 Checker 复核后继续；只有 materially 超出用户授权研究目标或需要 destructive migration 时才停止请求决策。
- 需要在 Miyabi 登录节点运行被禁止的 runtime 命令：停止，转为 PBS allocation。
- 单个 Miyabi 作业可由 agent 自主决定并提交（`select<=16`、`walltime<=02:00:00`，包括 9 节点）；超出该范围或需要付费公共云资源时停止并取得明确批准。
- 发现基础分支包含未合并的用户改动或基线漂移：保留改动，生成 drift report，不得覆盖。

## 13. 阶段完成报告模板

报告 epoch sequence、leader changes、head commits、kill points、takeover RTO（observed，不预设）、double/split count、cache rebuild。

## 14. 可直接复制给 Codex 的启动指令

```text
使用 miyabi-development skill 执行 P05。

仓库：https://github.com/UnbearableFate/fs_based_decoupled_diloco
规划基线：codex/fs-diloco-miyabi @ afc50a1e179c64321645b278b2497ea3ab3fe24d
目标分支：codex/duraloco-p05-syncer-failover
阶段计划：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/06_P05_SYNCER_LEASE_FENCING_AND_FAILOVER.md
共同契约：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/00_CODEX_LOOP_OPERATING_CONTRACT.md

先执行 hostname、git status --short --branch、git rev-parse HEAD，并读取 AGENTS.md、共同契约、当前阶段文件、上一阶段报告和相关研究草稿。若基线漂移，先写 drift report；不要 reset 用户改动。

按阶段文件中的 Loop 顺序工作。每个 Loop 都要先建立失败测试或可执行规范，再做最小实现，随后运行分层验证和独立 checker。持续更新 plans/duraloco/STATE.yaml；不要自动合并 main；不要在 Miyabi 登录节点运行 pytest、torch/transformers/datasets 导入、训练、mpirun 或其他 runtime 工作。

结束时在全部必需 gate 有证据且 Checker 通过时标记 completed，并按依赖图自动启动下一个可执行 goal/phase，不等待用户审核；否则输出 BLOCKED，并给出最小复现、已尝试方案和下一项决策。
```

## 15. 参考输入

- `references/DuraLoCo_research_draft_zh.md`
- 现有实现：`https://github.com/UnbearableFate/fs_based_decoupled_diloco/tree/codex/fs-diloco-miyabi`
- Miyabi skill：`https://github.com/UnbearableFate/miyabi-development`
