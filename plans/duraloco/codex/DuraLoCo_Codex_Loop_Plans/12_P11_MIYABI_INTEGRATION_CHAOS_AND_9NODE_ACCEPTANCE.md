---
plan_id: "P11"
title: "Miyabi 集成、Chaos Runner 与 9 节点 Acceptance"
status: "planned"
date: "2026-07-10"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/fs-diloco-miyabi"
planning_basis_commit: "afc50a1e179c64321645b278b2497ea3ab3fe24d"
target_branch: "codex/duraloco-p11-miyabi-acceptance"
depends_on:
  - "P10"
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
agent_decision_gates:
  - "必需主线 P00–P08 与 P10 completed branches 按依赖图由 agent 集成并经独立 Checker 复核；可选 P09 不参与本 gate。"
human_approval_gates:
  - "单个 Miyabi 作业超过 16 节点或 2 小时时必须批准；16 节点、2 小时以内（含 9 节点）由 agent 自主决定。"
  - "destructive GC 或作用于共享资源的真实故障操作必须批准。"
---

# P11 — Miyabi 集成、Chaos Runner 与 9 节点 Acceptance

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

把已通过 reference/local/POSIX-Lustre 的系统固化为 Miyabi 可操作 artifact：1 节点、2 节点和 9 节点 PBS 路径；可重放 fault tape；运行目录隔离；自动验收和证据打包。Object-store/MinIO/hybrid 不是本阶段的支持或验收条件。

### 1.1 本阶段支撑的研究主张

DuraLoCo 在目标 Lustre/PBS/GPU 环境中不仅通过模拟，还能在 8 learners + 1 syncer 的真实进程布局下完成训练、commit、adoption、failover 与恢复，并生成可审计 artifact。

### 1.2 完成后的系统增量

更新 Miyabi runbook、PBS scripts/configs、chaos scenario runner、acceptance checker 和 artifact packager；由 agent 自主申请资源并完成 9-node acceptance。

## 2. 前置条件

- [ ] 必需主线 P00–P08 与 P10 的所有 correctness gates 通过；可选 P09 不要求；
- [ ] completed feature branches 已按依赖图自动集成到 acceptance branch，并通过集成 Checker；
- [ ] Miyabi skill 已安装/可读；
- [ ] 确认 group/project、shared root、cache paths、model/dataset availability；
- [ ] 9-node 资源配置已确认不超过 `select=16`、`walltime=02:00:00` 的自主范围。

## 3. 范围

### 3.1 必须完成

- [ ] 统一 1/2/9-node PBS scripts；
- [ ] branch/commit/config/run root preflight；
- [ ] `/usr/bin/env` MPI env propagation；
- [ ] host/rank/role mapping；
- [ ] fault tape：learner kill/restart、syncer kill/takeover、I/O delay/error；
- [ ] 自动 acceptance assertions；
- [ ] logs/metrics/state digests packager；
- [ ] 1-node 10-step real model/data；
- [ ] 2-node failover；
- [ ] 9-node 8L+1S acceptance；
- [ ] 运行后安全 cleanup/retention report。

### 3.2 明确不做

- 不在此阶段开展完整 multi-seed science runs；
- 不在登录节点运行 runtime；
- 不把单次 9-node acceptance 当性能论文结论；
- 不故障注入共享系统服务或其他作业。

## 4. 预期仓库变更

```text
scripts/miyabi/
  duraloco_common.sh
  run_duraloco_1node_debug.pbs
  run_duraloco_2node_failover.pbs
  run_duraloco_9node_acceptance.pbs
  inspect_duraloco_run.sh
  package_duraloco_artifact.sh
scripts/chaos/
  scenario_runner.py
  fault_tape.py
  safe_process_control.py
configs/duraloco/miyabi/
  1node_real_10step.yaml
  2node_failover.yaml
  9node_8l1s_acceptance.yaml
fs_diloco/acceptance.py
docs/duraloco/miyabi_runbook.md
tests/test_acceptance_checker.py
```

## 5. 需要先冻结的设计决策

- [ ] D-1101：9-node role/GPU mapping；
- [ ] D-1102：PBS group、queue、walltime 由实际账户/项目确认，且单个作业不超过 16 节点和 2 小时；
- [ ] D-1103：fault tape 允许的 signal/process scope；
- [ ] D-1104：Lustre run root/stripe 与 cache paths；
- [ ] D-1105：9-node acceptance 的 commit/fragment/step 上限；
- [ ] D-1106：acceptance 后保留哪些 artifacts。

每项决策必须写入 `plans/duraloco/DECISIONS.md`，包含：上下文、候选方案、所选方案、拒绝方案、兼容性影响和可逆性。不得把未决语义隐藏在实现细节中。

## 6. Codex 执行循环

### Loop 1 — PBS/preflight 标准化

**目标。** 所有作业在运行前证明 branch、commit、config、host 和路径一致。

**先产生的失败证据或规范。**

- [ ] 错误 commit、脏树、空 group、login host、重复 run root、缺失 module/interpreter 记录、混用 mpirun env。

**实现任务。**

- [ ] common preflight；
- [ ] 打印 roles/ranks/hosts；
- [ ] timestamped run root；
- [ ] shell trap；
- [ ] 禁用 module pager，在作业 shell 记录 `module list` 和项目 Python 版本；非默认 module 使用精确版本显式加载；
- [ ] static checker。
- [ ] 提交时即生成 attempt manifest，记录 queue/resources/job ID；queued-cancelled 也不丢失 lineage。

**本循环验证。**

- [ ] `bash -n`；
- [ ] dry-run command；
- [ ] 错误输入 fail fast；
- [ ] 无 `mpirun -x` 混用。
- [ ] queue 切换只能重用相同 verified commit/config/assertions，并用 `parent_run_id` 连接前一尝试。

**本循环持久化输出。**

- [ ] PBS scripts；
- [ ] runbook。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 2 — 1-node real acceptance

**目标。** 在 compute node 用真实 model/data 跑最小 v2 end-to-end。

**先产生的失败证据或规范。**

- [ ] 先定义 finite loss、commit/adoption/head/outer-state artifacts assertions。

**实现任务。**

- [ ] 申请 1-node；
- [ ] ≤10 optimizer steps；
- [ ] 运行 acceptance checker；
- [ ] 每次后 qstat。

**本循环验证。**

- [ ] 至少一个合法 commit/adoption；
- [ ] loss finite；
- [ ] state verify/replay pass；
- [ ] artifact packaged。

**本循环持久化输出。**

- [ ] 1-node run bundle。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 3 — 2-node failover/chaos

**目标。** 真实跨节点验证 Lustre、leader/standby、learner/syncer roles。

**先产生的失败证据或规范。**

- [ ] fault tape 包含 pre-CAS/post-CAS kill、old leader resume。

**实现任务。**

- [ ] 2-node ≤10m；
- [ ] role logs；
- [ ] 执行 safe process-scoped faults；
- [ ] takeover/replay；
- [ ] qstat。

**本循环验证。**

- [ ] 无 split/double；
- [ ] 继续 commit；
- [ ] state digest pass；
- [ ] fault tape 可重放。

**本循环持久化输出。**

- [ ] 2-node chaos bundle。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 4 — 9-node acceptance（agent 自主资源 gate）

**目标。** 8 learners + 1 syncer/standby 真实布局完成短 acceptance。

**先产生的失败证据或规范。**

- [ ] pre-submit checker 必须拒绝超过 16 节点/2 小时、错误 group、未通过前置 gate。

**实现任务。**

- [ ] agent 根据实验目标自主选择不超过 16 节点、2 小时的资源；
- [ ] 提交 batch；
- [ ] 监控 qstat/log；
- [ ] 运行 acceptance checker；
- [ ] 保存 storage/quality/goodput raw metrics。

**本循环验证。**

- [ ] 所有 9 roles 启动并记录 hostname；
- [ ] quorum/fragment commits/adoptions；
- [ ] finite loss；
- [ ] 无 invariant violation；
- [ ] 正常 terminal state。

**本循环持久化输出。**

- [ ] 9-node immutable evidence bundle；
- [ ] acceptance report。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 5 — 操作和 artifact 演练

**目标。** 从干净 checkout 按 runbook 定位、检查和打包结果。

**先产生的失败证据或规范。**

- [ ] 缺日志/manifest/commit/config 时 packager 拒绝。

**实现任务。**

- [ ] inspect CLI；
- [ ] artifact checksums；
- [ ] redact paths/secrets；
- [ ] retention/cleanup dry run。

**本循环验证。**

- [ ] 第三方 checker 可仅凭 bundle 验证 acceptance；
- [ ] 未删除 live objects。

**本循环持久化输出。**

- [ ] artifact tar/manifest；
- [ ] operator checklist。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

## 7. 不变量与失败注入

### 7.1 本阶段必须维护的不变量

- [ ] Miyabi 登录节点仅 control-plane；
- [ ] 每个 runtime run 绑定 branch/commit/config/PBS job/hosts；
- [ ] fault injection 只作用于 run-owned process/prefix；
- [ ] 9-node 可自主提交，但单个作业不得超过 16 节点或 2 小时；
- [ ] acceptance checker 验证 protocol state 而非只看进程退出；
- [ ] 所有角色日志可关联同 run ID。

### 7.2 必须覆盖的故障与反例

- [ ] wrong host/branch/config/group；
- [ ] role process launch failure；
- [ ] learner kill/restart；
- [ ] syncer pre/post CAS kill；
- [ ] old leader resume；
- [ ] Lustre delay/temporary I/O error（安全注入层）；
- [ ] walltime不足；
- [ ] artifact missing。

## 8. 验收标准

以下条件是阶段 gate，不是建议。Maker 必须给出命令、退出码和 artifact 路径；Checker 必须逐项复核。

- [ ] P11-A01：所有 PBS/shell scripts 通过 static review；
- [ ] P11-A02：1-node real ≤10-step v2 run 完成且 finite；
- [ ] P11-A03：2-node failover 无 split-brain/double inclusion；
- [ ] P11-A04：fault tape 与 state verify artifact 完整；
- [ ] P11-A05：agent 自主提交的 9-node 8L+1S acceptance 通过，且作业资源不超过 16 节点和 2 小时；
- [ ] P11-A06：9-node 每个角色 hostname/rank/GPU/run ID 可追踪；
- [ ] P11-A07：所有 commits 可 replay/verify；
- [ ] P11-A08：artifact packager 在缺证据时 fail closed；
- [ ] P11-A09：Checker 独立从 bundle 复核。
- [ ] P11-A10：1/2/9-node 的 pass/fail/inconclusive/queued-cancelled 尝试都有 commit/config/queue/qstat 绑定的 manifest 和每个 validation shape 的 `parent_run_id` lineage；
- [ ] P11-A11：最终 Checker 从最终干净 commit/bundle 重跑当前 persisted suite、至少一个历史反例和一个新反例，state/report/checksum 同步为绿。

## 9. 验证矩阵

| 层级 | 要求 |
|---|---|
| 本地 | acceptance checker、fault tape parser、script unit。 |
| Miyabi login | 必须：git/static/qsub/qstat/log only。 |
| Miyabi 1-node | 必须。 |
| Miyabi 2-node | 必须，最大 debug walltime 10 分钟。 |
| Miyabi 9-node | agent 可自主提交，无需用户批准；单个作业最多 16 节点、2 小时，这是本阶段最终 runtime gate。 |

1/2/9-node runtime 每次尝试后必须检查 `qstat "$PBS_JOBID"`。9-node 不再设置 `READY_FOR_9NODE_APPROVAL` 状态；前置 gate 通过后由 agent 自主提交，未实际通过则不得标记 P11 完成。

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

- [ ] 单个 Miyabi 作业超过 16 节点或 2 小时时必须获得明确批准；范围内作业（包括 9 节点）无需用户批准；
- [ ] destructive GC 或作用于共享资源的真实故障操作必须批准。
- [ ] P11 在自主资源范围和隔离 fault scope 内通过全部必需 gate 后自动进入 P12，无需人工审核；超限/破坏性动作可跳过并记录，不阻止有替代证据的安全工作继续。

## 12. 阻塞与停止规则

- 同一根因连续三次修复后仍未通过同一 gate：写入 `BLOCKERS.md` 并停止扩大改动。
- 若实现当前目标需要调整 research contract、failure model、协议线性化点或数值语义：agent 记录 ADR、acceptance impact 和回滚方案，经 Checker 复核后继续；只有 materially 超出用户授权研究目标或涉及外部风险权限时才停止请求决策。
- 需要在 Miyabi 登录节点运行被禁止的 runtime 命令：停止，转为 PBS allocation。
- 单个 Miyabi 作业可由 agent 自主决定并提交（`select<=16`、`walltime<=02:00:00`，包括 9 节点）；超出该范围或需要付费公共云资源时停止并取得明确批准。
- 发现基础分支包含未合并的用户改动或基线漂移：保留改动，生成 drift report，不得覆盖。

## 13. 阶段完成报告模板

报告 initial hostname/workflow、branch/commit sync、PBS job IDs、nodes/roles、fault tape、head/epoch/commit summary、finite loss、acceptance assertions、9-node 资源决策/结果。

## 14. 可直接复制给 Codex 的启动指令

```text
使用 miyabi-development skill 执行 P11。

仓库：https://github.com/UnbearableFate/fs_based_decoupled_diloco
规划基线：codex/fs-diloco-miyabi @ afc50a1e179c64321645b278b2497ea3ab3fe24d
目标分支：codex/duraloco-p11-miyabi-acceptance
阶段计划：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/12_P11_MIYABI_INTEGRATION_CHAOS_AND_9NODE_ACCEPTANCE.md
共同契约：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/00_CODEX_LOOP_OPERATING_CONTRACT.md

先执行 hostname、git status --short --branch、git rev-parse HEAD，并读取 AGENTS.md、共同契约、当前阶段文件、上一阶段报告和相关研究草稿。若基线漂移，先写 drift report；不要 reset 用户改动。

按阶段文件中的 Loop 顺序工作。每个 Loop 都要先建立失败测试或可执行规范，再做最小实现，随后运行分层验证和独立 checker。持续更新 plans/duraloco/STATE.yaml；不要自动合并 main；不要在 Miyabi 登录节点运行 pytest、torch/transformers/datasets 导入、训练、mpirun 或其他 runtime 工作。

结束时在全部必需 gate 有证据且 Checker 通过时标记 completed，并按依赖图自动启动下一个可执行 goal/phase，不等待用户审核；否则输出 BLOCKED，并给出最小复现、已尝试方案和下一项决策。
```

## 15. 参考输入

- `references/DuraLoCo_research_draft_zh.md`
- 现有实现：`https://github.com/UnbearableFate/fs_based_decoupled_diloco/tree/codex/fs-diloco-miyabi`
- Miyabi skill：`https://github.com/UnbearableFate/miyabi-development`
