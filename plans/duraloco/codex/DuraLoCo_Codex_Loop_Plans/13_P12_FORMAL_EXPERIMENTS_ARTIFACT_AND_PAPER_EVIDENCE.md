---
plan_id: "P12"
title: "正式实验、Artifact 与论文 Claim–Evidence"
status: "planned"
date: "2026-07-10"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/fs-diloco-miyabi"
planning_basis_commit: "afc50a1e179c64321645b278b2497ea3ab3fe24d"
target_branch: "codex/duraloco-p12-evaluation"
depends_on:
  - "P11"
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
agent_decision_gates:
  - "实验 registry、pre-registration、seed/stopping/exclusion policy 由 agent 冻结并经独立 Checker 复核；各 campaign 达标后自动推进。"
human_approval_gates:
  - "单个 Miyabi 作业超过 16 节点或 2 小时，以及公共云实验，须先批准资源预算；范围内的 9-node 和 multi-seed 作业由 agent 自主决定。"
  - "发布 artifact 或公开数据前需审批。"
---

# P12 — 正式实验、Artifact 与论文 Claim–Evidence

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

按照顶级系统/ML 系统会议标准执行因子化实验：隔离 storage transport 与 checkpoint fusion，测量 correctness、quality、goodput、recovery、I/O amplification、成本、controller 和 break-even region；生成不可变 evidence、图表和论文结果章节。

### 1.1 本阶段支撑的研究主张

本阶段不预设 DuraLoCo 优于所有 baseline。它验证或否证：在低通信、异步、有故障的特定工作区间，durable optimizer log 能以可接受 failure-free overhead 消除/减少独立 global checkpoint，并提高 failure 下 end-to-end ML goodput。

### 1.2 完成后的系统增量

新增 experiment registry、pre-registration、baseline adapters、fault tapes、analysis pipeline、claims matrix、artifact reproduction 和 paper result placeholders 的实测填充。

## 2. 前置条件

- [ ] P11 9-node acceptance 已通过；
- [ ] 所有 correctness invariants 无未关闭 P0；
- [ ] resource/cost budget 已登记；范围内 Miyabi 作业由 agent 自主决定，超限作业已批准或安全 skip，公共云默认 skip（显式选中时才要求预算批准）；
- [ ] 模型、数据集、revision、seeds、baselines 冻结；
- [ ] 分析脚本在 synthetic fixture 上通过。

## 3. 范围

### 3.1 必须完成

- [ ] 2×2 transport × checkpoint fusion baseline；
- [ ] POSIX/Lustre 必需基线；network/hybrid/MinIO/公共云均为可选扩展，缺失不阻塞 P12；
- [ ] full-vector/fragment DuraLoCo；
- [ ] normal checkpoint+restart；
- [ ] fixed/SACC、eager/selected-only；
- [ ] matched-token/matched-compute quality；
- [ ] failure-free overhead；
- [ ] fault schedules/recovery；
- [ ] scale/model-equivalent benchmarks；
- [ ] storage bytes/requests/object count/cost；
- [ ] multi-seed statistics；
- [ ] claim-evidence matrix；
- [ ] artifact package/reproduction；
- [ ] 更新论文结果章节，保留负面结果。

### 3.2 明确不做

- 不选择性删除不利 seed；
- 不把模拟 scale 当真实训练 scale；
- 不把 WikiText-2 smoke 当主要质量证据；
- 不在结果出来前写 improvement 数值；
- 不扩大 claim 超出测量 backend/scale/failure model。

## 4. 预期仓库变更

```text
experiments/duraloco/
  registry.yaml
  preregistration.md
  baselines/
  workloads/
  fault_tapes/
  storage_backends/
  manifests/
analysis/duraloco/
  validate_runs.py
  aggregate.py
  statistics.py
  plots.py
  claims.py
paper/
  results.md
  figures/
  tables/
artifact/
  README.md
  reproduce.sh
  environment/
  expected_checksums.json
```

所有 generated results 必须进入独立 artifact/results 路径；不要把大 checkpoint 或 secret 上传 Git。

## 5. 需要先冻结的设计决策

- [ ] D-1201：primary venue/claim 和主 workload；
- [ ] D-1202：模型规模、token budget、seeds 和 stopping rule；
- [ ] D-1203：network Decoupled baseline 的实现/公平性；
- [ ] D-1204：checkpoint interval 和 failure distribution；
- [ ] D-1205：统计检验/置信区间；
- [ ] D-1206：可选 public cloud provider/region/cost；未选中时记录 `not_applicable`；
- [ ] D-1207：run exclusion policy；
- [ ] D-1208：artifact 中可公开的模型/数据/log。

每项决策必须写入 `plans/duraloco/DECISIONS.md`，包含：上下文、候选方案、所选方案、拒绝方案、兼容性影响和可逆性。不得把未决语义隐藏在实现细节中。

## 6. Codex 执行循环

### Loop 1 — Experiment registry 与 pre-registration

**目标。** 在运行前固定问题、factor、metric、budget、seed 和排除规则。

**先产生的失败证据或规范。**

- [ ] validator 对缺 baseline、unmatched tokens、重复 ID、无 budget/approval 失败。

**实现任务。**

- [ ] 建立 registry schema；
- [ ] 2×2 matrix；
- [ ] claim→experiment mapping；
- [ ] 资源估算、自主范围判定和超限审批字段；
- [ ] run manifest generator。
- [ ] 将 pass/fail/inconclusive/excluded/queued-cancelled 都建模为不可变 attempt，同一 experiment cell/seed 的重试必须链接 `parent_run_id`。

**本循环验证。**

- [ ] registry validator pass；
- [ ] 每个 primary claim 有实验；
- [ ] 每个 run 都有资源估算；范围内 Miyabi 作业无需批准，超限或公共云 run 有批准。
- [ ] exclusion/retry 不能删除前任 manifest，并且 aggregate validator 能区分 queue/capacity 与 runtime/scientific failure。

**本循环持久化输出。**

- [ ] registry/preregistration；
- [ ] frozen config digests。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 2 — Correctness 与 resilience campaign

**目标。** 在正式代码/backend 上运行 crash matrix、long soak 和 recovery tests。

**先产生的失败证据或规范。**

- [ ] 任何 double apply/split/live delete 自动使 campaign fail。

**实现任务。**

- [ ] 随机 fault tapes；
- [ ] syncer/learner/catastrophic restart；
- [ ] 累计 24/72h resumable segmented soak：每个 Miyabi 作业不超过 2 小时并由 agent 自动续接；只有要求单次连续 >2h 时才走外部资源审批；
- [ ] POSIX/Lustre backend；若已显式提供并选中，可附加 MinIO/云 backend，否则安全 skip 且不影响 campaign gate。

**本循环验证。**

- [ ] invariant dashboard 全绿；
- [ ] 所有失败保留最小 trace；
- [ ] RTO/RPO/lost/repeated work 可计算。

**本循环持久化输出。**

- [ ] correctness dataset；
- [ ] resilience tables。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 3 — Failure-free performance 与 break-even

**目标。** 测量 storage pipeline 是否被 local compute 隐藏以及适用区间。

**先产生的失败证据或规范。**

- [ ] 分析拒绝 unmatched model/fragment/q/H/backend。

**实现任务。**

- [ ] 扫描 local interval、fragment size/count、q、learners、backend；
- [ ] POSIX/Lustre storage；network/hybrid 仅在已显式提供时作为可选扩展；
- [ ] fixed/SACC；
- [ ] model-equivalent I/O。

**本循环验证。**

- [ ] P50/P95/P99、goodput、idle、bytes/requests 可比较；
- [ ] 真实和模拟明确标记。

**本循环持久化输出。**

- [ ] break-even surfaces；
- [ ] overhead figures。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 4 — Checkpoint fusion 与 fault goodput

**目标。** 隔离 transport 和 fusion 的独立贡献。

**先产生的失败证据或规范。**

- [ ] 2×2 任一 cell 缺失或 checkpoint policy 不匹配时禁止结论。

**实现任务。**

- [ ] A ephemeral+periodic；B ephemeral+log-derived；C storage+periodic；D storage+fused；
- [ ] 同 fault schedule；
- [ ] 计算 useful tokens、recompute、checkpoint bytes、RTO。

**本循环验证。**

- [ ] 每个对照 matched；
- [ ] 结果可由 manifests 重算；
- [ ] confidence intervals。

**本循环持久化输出。**

- [ ] fusion attribution figures；
- [ ] fault-goodput tables。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 5 — 模型质量与算法消融

**目标。** 证明 matched tokens/FLOPs 下 quality 不被协议/恢复/controller 系统性破坏。

**先产生的失败证据或规范。**

- [ ] seed 不齐、token budget 不同、eval revision 不同即拒绝聚合。

**实现任务。**

- [ ] failure-free/failure；
- [ ] warm/exact；
- [ ] reset policies；
- [ ] fixed/SACC；
- [ ] full/fragment；
- [ ] validation + selected lm-eval。

**本循环验证。**

- [ ] 多 seed 曲线；
- [ ] 统计方法；
- [ ] 负面 seed 保留；
- [ ] quality/goodput tradeoff。

**本循环持久化输出。**

- [ ] quality figures/tables；
- [ ] raw eval manifests。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 6 — Artifact 与论文证据

**目标。** 让独立复现者从 clean checkout 重建关键结果。

**先产生的失败证据或规范。**

- [ ] 随机删一个 run/配置/checksum，pipeline 必须拒绝不完整 aggregation。

**实现任务。**

- [ ] reproduce scripts；
- [ ] environment lock/container；
- [ ] small artifact path；
- [ ] claims matrix；
- [ ] 填论文 results，不改 planned claims 为事实除非证据足。

**本循环验证。**

- [ ] clean environment smoke；
- [ ] checksum；
- [ ] 第三方 checker 复跑至少核心图/表。

**本循环持久化输出。**

- [ ] artifact bundle；
- [ ] paper results；
- [ ] claim-evidence matrix。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

## 7. 不变量与失败注入

### 7.1 本阶段必须维护的不变量

- [ ] 所有结果绑定不可变 commit/config/backend/environment/seed；
- [ ] factorized baseline 公平匹配；
- [ ] 缺失/排除 run 不静默；
- [ ] 计划/目标/观察值分离；
- [ ] simulation 与 real execution 分离；
- [ ] 每个论文 claim 有直接 evidence chain；
- [ ] 负面结果保留。

### 7.2 必须覆盖的故障与反例

- [ ] run preemption/partial logs；
- [ ] seed/config mismatch；
- [ ] analysis code change；
- [ ] missing/corrupt manifest；
- [ ] provider throttling；
- [ ] failure tape drift；
- [ ] baseline implementation divergence；
- [ ] cost budget exhaustion。

## 8. 验收标准

以下条件是阶段 gate，不是建议。Maker 必须给出命令、退出码和 artifact 路径；Checker 必须逐项复核。

- [ ] P12-A01：experiment registry 与 preregistration 冻结并通过独立 checker；
- [ ] P12-A02：2×2 transport/fusion baseline 完整；
- [ ] P12-A03：correctness campaign 无未解释 double apply/split/live delete；
- [ ] P12-A04：failure-free overhead 与 break-even 有真实数据；
- [ ] P12-A05：fault goodput/RTO/RPO/lost/repeated work 完整；
- [ ] P12-A06：matched-token/matched-compute multi-seed quality 完整或明确标记无法支持 claim；
- [ ] P12-A07：storage bytes/requests/object count/cost 完整；
- [ ] P12-A08：所有图表可从 raw manifests 重建；
- [ ] P12-A09：claim-evidence matrix 无悬空 primary claim；
- [ ] P12-A10：clean artifact reproduction 通过；
- [ ] P12-A11：论文不包含虚构或超范围结论；
- [ ] P12-A12：独立 Checker/内部审稿完成。
- [ ] P12-A13：所有失败、取消、排除和重试 run 均保留 immutable manifest、结构化原因和 experiment-cell/seed `parent_run_id` lineage；
- [ ] P12-A14：从最终干净 analysis commit 重建核心图表与 claim matrix，并证明 simulator/runtime/policy 的 digest 与预注册版本一致。

## 9. 验证矩阵

实验执行分层：

| Campaign | 环境 | 资源门 |
|---|---|---|
| Unit/reference/correctness quick | local/compute | 普通 phase gate |
| Lustre 1/2-node micro + crash | Miyabi | debug allocation |
| 9-node、≤2h | Miyabi | agent 自主决定并提交，无需用户批准 |
| >2h 或 >16-node | Miyabi | 明确批准后提交 |
| MinIO | 可选的独立允许环境 | 未实现 P09 时 skip；不阻塞 P12 |
| 公共云 | 可选 approved provider/region | 未实现 P09 时 skip；使用时凭据、预算、egress 明确批准 |
| Multi-seed model training | Miyabi/approved | registry + budget + stopping rule；单个范围内 Miyabi 作业自主提交 |

分析必须先运行 `validate_runs.py`；只有 status `COMPLETE_AND_MATCHED` 的 run 可进入 primary aggregate。

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

- [ ] 单个 Miyabi 作业超过 16 节点或 2 小时，以及公共云实验，须先批准资源预算；范围内的 9-node 和 multi-seed 作业由 agent 自主决定；
- [ ] 发布 artifact 或公开数据前需审批。
- [ ] P12 内各 campaign/goal 在 registry gate 和 Checker 通过后自动推进；全部必需 evidence gates 通过后自动标记 P12 `completed`，无需人工完成审核。未获发布批准时只保留私有 artifact，不影响研究阶段完成。P09 不自动启动，也不是 P12 或主线完成条件。

## 12. 阻塞与停止规则

- 同一根因连续三次修复后仍未通过同一 gate：写入 `BLOCKERS.md` 并停止扩大改动。
- 若实现当前目标需要调整 research contract、failure model、协议线性化点或数值语义：agent 记录 preregistration amendment、影响分析和 Checker verdict 后继续；只有 materially 超出用户授权研究目标或涉及外部风险权限时才停止请求决策。
- 需要在 Miyabi 登录节点运行被禁止的 runtime 命令：停止，转为 PBS allocation。
- 单个 Miyabi 作业可由 agent 自主决定并提交（`select<=16`、`walltime<=02:00:00`，包括 9 节点和 multi-seed）；超出该范围或需要付费公共云资源时停止并取得明确批准。
- 发现基础分支包含未合并的用户改动或基线漂移：保留改动，生成 drift report，不得覆盖。

## 13. 阶段完成报告模板

报告 registry version、资源决策与实际用量、completed/failed/excluded runs、primary metrics/CIs、negative results、claims supported/rejected、artifact checksum和 paper readiness。

## 14. 可直接复制给 Codex 的启动指令

```text
使用 miyabi-development skill 执行 P12。

仓库：https://github.com/UnbearableFate/fs_based_decoupled_diloco
规划基线：codex/fs-diloco-miyabi @ afc50a1e179c64321645b278b2497ea3ab3fe24d
目标分支：codex/duraloco-p12-evaluation
阶段计划：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/13_P12_FORMAL_EXPERIMENTS_ARTIFACT_AND_PAPER_EVIDENCE.md
共同契约：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/00_CODEX_LOOP_OPERATING_CONTRACT.md

先执行 hostname、git status --short --branch、git rev-parse HEAD，并读取 AGENTS.md、共同契约、当前阶段文件、上一阶段报告和相关研究草稿。若基线漂移，先写 drift report；不要 reset 用户改动。

按阶段文件中的 Loop 顺序工作。每个 Loop 都要先建立失败测试或可执行规范，再做最小实现，随后运行分层验证和独立 checker。持续更新 plans/duraloco/STATE.yaml；不要自动合并 main；不要在 Miyabi 登录节点运行 pytest、torch/transformers/datasets 导入、训练、mpirun 或其他 runtime 工作。

结束时在全部必需 gate 有证据且 Checker 通过时标记 completed，并按依赖图自动启动下一个可执行 goal/phase，不等待用户审核；否则输出 BLOCKED，并给出最小复现、已尝试方案和下一项决策。
```

## 15. 参考输入

- `references/DuraLoCo_research_draft_zh.md`
- 现有实现：`https://github.com/UnbearableFate/fs_based_decoupled_diloco/tree/codex/fs-diloco-miyabi`
- Miyabi skill：`https://github.com/UnbearableFate/miyabi-development`
