---
plan_id: "P08"
title: "Direct Fragment I/O、Streaming Reducer 与 Telemetry"
status: "planned"
date: "2026-07-10"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/fs-diloco-miyabi"
planning_basis_commit: "afc50a1e179c64321645b278b2497ea3ab3fe24d"
target_branch: "codex/duraloco-p08-performance-core"
depends_on:
  - "P06"
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
agent_decision_gates:
  - "引入 CUDA/C++ extension、改变 tensor layout 或默认 precision 由 agent 基于 profile、numeric equivalence 和回退方案决定，经独立 Checker 复核。"
human_approval_gates: []
---

# P08 — Direct Fragment I/O、Streaming Reducer 与 Telemetry

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

消除当前 fragment path 中 whole-model flatten/scatter 和 quorum 全量驻留的主要放大，使内存、CPU copy 与 I/O 更接近 fragment 大小；建立能够支撑论文性能结论的端到端 telemetry。

### 1.1 本阶段支撑的研究主张

Storage-native 协议的开销不是由低效 prototype 实现主导；fragment merge 的峰值工作内存接近 O(fragment size)，并可测量 publish-to-adopt critical path。

### 1.2 完成后的系统增量

新增 direct gather/scatter、streaming weighted accumulator、buffer/prefetch、增量 scanner 与结构化 metrics/benchmark harness；行为与 reference optimizer 等价。

## 2. 前置条件

- [ ] P06 v2 E2E 可运行；
- [ ] P02 numeric oracle 可比较；
- [ ] 明确 whole-tensor fragmentation 初版保持不变；
- [ ] 记录性能前基线。

## 3. 范围

### 3.1 必须完成

- [ ] 根据 parameter index 直接 gather/scatter 目标 fragment；
- [ ] streaming weighted reduce；
- [ ] accumulation dtype 与 deterministic mode；
- [ ] pinned CPU buffers/可选 CUDA stream；
- [ ] bounded in-flight reads/writes；
- [ ] incremental proposal discovery/cursor；
- [ ] 目录/key sharding；
- [ ] publish/read/validate/quorum/merge/commit/adopt telemetry；
- [ ] memory/I/O/request benchmark harness；
- [ ] legacy vs optimized 数值对照。
- [ ] optimized/runtime/reference 共用选择与数值语义，不重复实现 policy。

### 3.2 明确不做

- 不实现 sub-tensor fragmentation 默认路径；
- 不在无 evidence 时手写 CUDA kernel；
- 不实现 SACC policy；
- 不以 synthetic bandwidth 代替真实 E2E。

## 4. 预期仓库变更

```text
fs_diloco/optimizer/
  fragment_access.py
  streaming_reduce.py
  buffers.py
fs_diloco/storage/
  scanner.py
  prefetch.py
fs_diloco/telemetry/
  events.py
  recorder.py
  summaries.py
benchmarks/
  bench_fragment_access.py
  bench_streaming_reduce.py
  bench_storage_pipeline.py
tests/performance_core/
  test_fragment_access_equivalence.py
  test_streaming_reduce_equivalence.py
  test_memory_bound.py
  test_scanner_incremental.py
```

## 5. 需要先冻结的设计决策

- [ ] D-0801：accumulation dtype 和 deterministic reduction order；
- [ ] D-0802：pinned buffers 的生命周期和 backpressure；
- [ ] D-0803：CPU/GPU overlap 是否默认启用；
- [ ] D-0804：scanner watermark 和 listing 仅 discovery 的实现；
- [ ] D-0805：telemetry event schema 与 overhead sampling。

每项决策必须写入 `plans/duraloco/DECISIONS.md`，包含：上下文、候选方案、所选方案、拒绝方案、兼容性影响和可逆性。不得把未决语义隐藏在实现细节中。

## 6. Codex 执行循环

### Loop 1 — 性能基线与 profiler

**目标。** 先量化 whole flatten、quorum memory、metadata scan 和 I/O 放大。

**先产生的失败证据或规范。**

- [ ] 建立 benchmark assertions 只检测回归，不预设无法跨机器保证的绝对速度。

**实现任务。**

- [ ] 测量 bytes copied、peak RSS/VRAM、read/write、object ops、latency；
- [ ] 记录 model-equivalent tensor sizes；
- [ ] 生成 raw JSON。

**本循环验证。**

- [ ] 同 commit/seed 重复可聚合；
- [ ] 环境信息完整；
- [ ] 缺数据时分析拒绝。

**本循环持久化输出。**

- [ ] baseline benchmarks；
- [ ] metric schema。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 2 — Direct fragment access

**目标。** 只访问 fragment 对应参数/slices。

**先产生的失败证据或规范。**

- [ ] 与 legacy flatten/slice/scatter 在多 dtype/layout 下对照。

**实现任务。**

- [ ] 缓存 fragment layout；
- [ ] 实现 gather/scatter；
- [ ] 支持 whole-tensor fragment；
- [ ] 避免不相关 parameter clone。

**本循环验证。**

- [ ] 数值等价；
- [ ] copy bytes 随 fragment 而非 model 增长；
- [ ] autograd/optimizer ownership 无破坏。

**本循环持久化输出。**

- [ ] fragment access API；
- [ ] equivalence report。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 3 — Streaming reducer

**目标。** 逐 proposal 累加，不同时保留 quorum tensors。

**先产生的失败证据或规范。**

- [ ] 不同 q、weights、staleness、dtype、input order。

**实现任务。**

- [ ] 实现 weighted accumulator；
- [ ] 校验每个输入后释放；
- [ ] deterministic/reference mode；
- [ ] bounded prefetch。

**本循环验证。**

- [ ] 与 reference tolerance 一致；
- [ ] peak working set 对 q 不线性增长；
- [ ] corrupt input 中途失败不 commit。

**本循环持久化输出。**

- [ ] streaming reducer；
- [ ] memory profile。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 4 — Scanner/prefetch/telemetry

**目标。** 减少历史目录重复扫描，并完整测量 storage pipeline。

**先产生的失败证据或规范。**

- [ ] list omission/duplicate；cursor restart；telemetry writer crash。

**实现任务。**

- [ ] incremental cursor；
- [ ] key sharding；
- [ ] prefetch queue/backpressure；
- [ ] scanner/prefetch 对同一 immutable manifest/object snapshot 验证和使用，避免 TOCTOU；
- [ ] 结构化 event IDs；
- [ ] 单写者 metrics。

**本循环验证。**

- [ ] restart 不漏 committed manifest；
- [ ] 重复 discovery 幂等；
- [ ] telemetry 可重建每个 commit timeline。

**本循环持久化输出。**

- [ ] scanner/prefetch；
- [ ] telemetry schema；
- [ ] dashboard-ready raw data。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

## 7. 不变量与失败注入

### 7.1 本阶段必须维护的不变量

- [ ] 优化路径与 reference 数值语义一致；
- [ ] 不相关 fragment 参数不被改写；
- [ ] peak merge working set 不随 quorum 线性增长；
- [ ] corrupt/incomplete input 不产生 commit；
- [ ] telemetry 不成为 authority；
- [ ] scanner listing 只发现，不决定 committed state。

### 7.2 必须覆盖的故障与反例

- [ ] input corruption mid-stream；
- [ ] prefetch timeout/cancel；
- [ ] OOM pressure；
- [ ] scanner duplicate/omission/restart；
- [ ] telemetry file crash；
- [ ] mixed dtype/shape；
- [ ] q scaling。

## 8. 验收标准

以下条件是阶段 gate，不是建议。Maker 必须给出命令、退出码和 artifact 路径；Checker 必须逐项复核。

- [ ] P08-A01：direct fragment access 与 legacy/reference 等价；
- [ ] P08-A02：streaming reducer 与 reference 等价；
- [ ] P08-A03：峰值工作内存随 q 增长不呈现旧实现的 q×fragment 线性驻留；
- [ ] P08-A04：fragment access copy/I/O 由测量证明接近 fragment scope；
- [ ] P08-A05：scanner restart/duplicate/list omission tests 通过；
- [ ] P08-A06：每个 commit 可从 telemetry 重建 publish→select→read→merge→CAS→adopt timeline；
- [ ] P08-A07：performance 结果保存 raw manifests，不只保留汇总；
- [ ] P08-A08：Miyabi 1-node GPU profile 与 2-node storage pipeline evidence。
- [ ] P08-A09：optimized/runtime/reference 在 adversarial order、restart 和并发 prefetch 下的 decision/state digest 等价，且回归能杀死一个独立 policy 实现 mutant；
- [ ] P08-A10：profile/benchmark 的 fail、inconclusive、queued-cancelled 和 retry 都有 raw manifest lineage，最终 Checker 在最终干净 commit 重放当前等价套件。

## 9. 验证矩阵

| 层级 | 要求 |
|---|---|
| 本地 | 数值等价、CPU memory、scanner tests。 |
| Miyabi 1-node | 必须：真实 GPU/model fragment gather/scatter、streaming reduce、10-step E2E profile。 |
| Miyabi 2-node | 必须：learner→Lustre→syncer pipeline latency与backpressure。 |
| 9-node | P11 才做扩展接受。 |

性能 gate 以相对复杂度和完整测量为主；不得把单次噪声测量硬编码成通用绝对阈值。

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

- [ ] CUDA/C++ extension、tensor layout 或默认 precision 变更由 agent 依据 profile、numeric equivalence、portable fallback 和回滚证据决定，经 Checker 复核后生效。
- [ ] P08 必需 gate 通过后标记 `completed`；等待依赖图中的 P07 完成并通过集成 Checker 后自动进入 P10，不等待人工审核，也不等待可选 P09。

## 12. 阻塞与停止规则

- 同一根因连续三次修复后仍未通过同一 gate：写入 `BLOCKERS.md` 并停止扩大改动。
- 若实现当前目标需要调整 research contract、failure model、协议线性化点或数值语义：agent 记录 ADR、profile/numeric evidence 和 fallback，经 Checker 复核后继续；只有 materially 超出用户授权研究目标时才停止请求决策。
- 需要在 Miyabi 登录节点运行被禁止的 runtime 命令：停止，转为 PBS allocation。
- 单个 Miyabi 作业可由 agent 自主决定并提交（`select<=16`、`walltime<=02:00:00`，包括 9 节点）；超出该范围或需要付费公共云资源时停止并取得明确批准。
- 发现基础分支包含未合并的用户改动或基线漂移：保留改动，生成 drift report，不得覆盖。

## 13. 阶段完成报告模板

报告 model/fragment/q、legacy vs optimized peak RSS/VRAM、bytes copied、P50/P95/P99 timeline、numeric error、scanner ops 和 raw run IDs。

## 14. 可直接复制给 Codex 的启动指令

```text
使用 miyabi-development skill 执行 P08。

仓库：https://github.com/UnbearableFate/fs_based_decoupled_diloco
规划基线：codex/fs-diloco-miyabi @ afc50a1e179c64321645b278b2497ea3ab3fe24d
目标分支：codex/duraloco-p08-performance-core
阶段计划：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/09_P08_DIRECT_FRAGMENT_IO_STREAMING_REDUCER_AND_TELEMETRY.md
共同契约：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/00_CODEX_LOOP_OPERATING_CONTRACT.md

先执行 hostname、git status --short --branch、git rev-parse HEAD，并读取 AGENTS.md、共同契约、当前阶段文件、上一阶段报告和相关研究草稿。若基线漂移，先写 drift report；不要 reset 用户改动。

按阶段文件中的 Loop 顺序工作。每个 Loop 都要先建立失败测试或可执行规范，再做最小实现，随后运行分层验证和独立 checker。持续更新 plans/duraloco/STATE.yaml；不要自动合并 main；不要在 Miyabi 登录节点运行 pytest、torch/transformers/datasets 导入、训练、mpirun 或其他 runtime 工作。

结束时在全部必需 gate 有证据且 Checker 通过时标记 completed，并按依赖图自动启动下一个可执行 goal/phase，不等待用户审核；否则输出 BLOCKED，并给出最小复现、已尝试方案和下一项决策。
```

## 15. 参考输入

- `references/DuraLoCo_research_draft_zh.md`
- 现有实现：`https://github.com/UnbearableFate/fs_based_decoupled_diloco/tree/codex/fs-diloco-miyabi`
- Miyabi skill：`https://github.com/UnbearableFate/miyabi-development`
