---
plan_id: "P09"
title: "可选：S3-Compatible Backend、MinIO 与 Hybrid Baseline"
status: "planned"
date: "2026-07-10"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/fs-diloco-miyabi"
planning_basis_commit: "afc50a1e179c64321645b278b2497ea3ab3fe24d"
target_branch: "codex/duraloco-p09-object-store"
depends_on:
  - "P12"
optional: true
required_for_core_completion: false
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
automatic_progression: false
agent_decision_gates:
  - "对象存储依赖策略、SDK/version 和 lockfile 由 agent 记录 ADR，经独立 Checker 复核。"
human_approval_gates:
  - "真实 S3/GCS/Azure 运行、凭据使用、跨区域流量或付费资源必须审批；"
  - "新增持久化/共享服务或对外暴露端口前需审批；job-owned、隔离且随测试退出的 MinIO/临时端口由 agent 自主使用。"
---

# P09（可选，暂缓）— S3-Compatible Backend、MinIO 与 Hybrid Baseline

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

> 当前必需主线到 P12 结束。本阶段仅作为未来可选实现保留，暂时不需要支持，不得自动启动，不得阻塞 P10–P12、默认运行或主线完成。只有用户未来显式选择 object-store 支持后才执行下述 gates。

证明 transactional protocol 不依赖 POSIX rename/listing。实现 S3-compatible backend、MinIO contract/chaos、conditional head、multipart 和重试，并建立 metadata-control + object-payload hybrid baseline。

### 1.1 本阶段支撑的研究主张

DuraLoCo 是 storage-native abstraction，而不是 Lustre 特例；同一 committed-prefix correctness suite 可跨 POSIX 和 object storage，通过 conditional object updates 实现 head commit。

### 1.2 完成后的系统增量

新增可选 object-store extra、MinIO test environment、S3 backend 与 hybrid control-plane baseline；公共云验证保持人工 gate。

## 2. 前置条件

- [ ] P04 log API 完全 backend-neutral；
- [ ] 对象存储依赖策略和 lockfile 已由 agent 决定、记录 ADR 并通过独立 Checker；
- [ ] 本地/CI 可运行 MinIO 或提供替代 integration environment；
- [ ] 秘密管理约定已写入 AGENTS。

## 3. 范围

### 3.1 必须完成

- [ ] S3 immutable put/get/head/range/delete；
- [ ] If-None-Match/If-Match conditional head；
- [ ] ETag 与 content hash 区分；
- [ ] multipart upload/recovery/abort；
- [ ] retry/backoff/jitter、429/5xx/timeout；
- [ ] response-loss idempotency；
- [ ] strong correctness 不依赖 list；
- [ ] MinIO conformance/crash suite；
- [ ] hybrid metadata coordinator + object payload baseline；
- [ ] public cloud capability harness（默认不执行）。

### 3.2 明确不做

- 不把 MinIO 性能写成公有云性能；
- 不把 provider-specific strong consistency 无条件外推到所有对象存储；
- 不自动创建付费 bucket/跨区域复制；
- 不在本阶段实现 SACC。

## 4. 预期仓库变更

```text
fs_diloco/storage/
  s3.py
  multipart.py
  retry.py
  credentials.py
  object_capability_probe.py
fs_diloco/hybrid/
  metadata_service.py
  client.py
scripts/object_store/
  start_minio_test.sh
  stop_minio_test.sh
  run_contract.sh
  public_cloud_probe.py
tests/storage/
  test_s3_contract.py
  test_s3_response_loss.py
  test_multipart.py
  test_listing_independence.py
tests/hybrid/
```

在 `pyproject.toml` 中使用可选依赖组并固定版本；核心 POSIX 安装不应被迫安装云 SDK。

## 5. 需要先冻结的设计决策

- [ ] D-0901：SDK 与版本；
- [ ] D-0902：conditional write token 使用 ETag/version ID；
- [ ] D-0903：multipart threshold/part size 与 orphan cleanup；
- [ ] D-0904：provider capability matrix 和 fail-closed 策略；
- [ ] D-0905：hybrid baseline 的 metadata API 最小范围；
- [ ] D-0906：public cloud region/topology 与成本预算。

每项决策必须写入 `plans/duraloco/DECISIONS.md`，包含：上下文、候选方案、所选方案、拒绝方案、兼容性影响和可逆性。不得把未决语义隐藏在实现细节中。

## 6. Codex 执行循环

### Loop 1 — S3 semantic backend

**目标。** 实现与 memory/POSIX 相同 storage contract。

**先产生的失败证据或规范。**

- [ ] same key same/different bytes；stale If-Match；timeout after PUT/CAS；ETag 非 MD5。

**实现任务。**

- [ ] 实现 immutable/conditional/get/range/delete；
- [ ] PUT/CAS/delete/multipart complete/abort 都持久化 request ID；
- [ ] 显式 hash metadata；
- [ ] typed provider errors；
- [ ] typed errors 覆盖 credential/client setup、upload、lock/conditional call、cleanup/abort 和 inspect/recovery；
- [ ] credential redaction。

**本循环验证。**

- [ ] 通用 conformance suite；
- [ ] 响应丢失重试幂等；
- [ ] 同 ID/同内容、不同 ID/同内容和同 ID/冲突内容的结果与 POSIX contract 一致；
- [ ] 日志无 secrets。

**本循环持久化输出。**

- [ ] S3 backend；
- [ ] capability matrix。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 2 — Multipart 与重试

**目标。** 支持模型 fragment 大对象且不会留下不可控 multipart state。

**先产生的失败证据或规范。**

- [ ] 每个 part/complete/abort 阶段 crash；throttling；retry budget exhaustion。

**实现任务。**

- [ ] 可恢复 multipart state；
- [ ] content hash；
- [ ] bounded concurrency；
- [ ] backoff/jitter；
- [ ] orphan report/cleanup。

**本循环验证。**

- [ ] crash suite；
- [ ] 重复 complete 不破坏 identity；
- [ ] 失败能解释并停止。

**本循环持久化输出。**

- [ ] multipart manager；
- [ ] fault traces。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 3 — MinIO E2E 与 listing independence

**目标。** 在真实 object API 上运行 P04/P05/P06 的小型路径。

**先产生的失败证据或规范。**

- [ ] 故意隐藏/延迟 list results，同时直接 head/get 正常。

**实现任务。**

- [ ] 可重复启动隔离 MinIO；
- [ ] 运行 contract、transaction、syncer/learner tiny E2E；
- [ ] 捕获 server/client logs。

**本循环验证。**

- [ ] committed correctness 不受 list omission；
- [ ] POSIX/MinIO state digest 一致。

**本循环持久化输出。**

- [ ] MinIO harness；
- [ ] E2E manifests。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 4 — Hybrid baseline

**目标。** 隔离 persistent tensor payload 与 durable metadata protocol 的贡献。

**先产生的失败证据或规范。**

- [ ] metadata service restart；payload exists but metadata absent；duplicate request。

**实现任务。**

- [ ] 实现最小 metadata control service；
- [ ] payload 仍用 storage backend；
- [ ] run manifest 标记 transport/checkpoint mode；
- [ ] 不复用 DuraLoCo durable head 伪装 baseline。

**本循环验证。**

- [ ] small E2E；
- [ ] failure semantics 清楚；
- [ ] metrics 可与 pure storage 对照。

**本循环持久化输出。**

- [ ] hybrid baseline；
- [ ] factorized config。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 5 — 公共云 probe（人工 gate）

**目标。** 准备而非默认执行 provider capability/cost test。

**先产生的失败证据或规范。**

- [ ] 无凭据时必须安全跳过；错误 region/bucket 不得创建。

**实现任务。**

- [ ] dry-run 命令；
- [ ] estimate request/egress；
- [ ] explicit prefix；
- [ ] cleanup plan。

**本循环验证。**

- [ ] 无 secret leak；
- [ ] 只有 approval flag 才实际运行。

**本循环持久化输出。**

- [ ] probe script；
- [ ] cost/approval checklist。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

## 7. 不变量与失败注入

### 7.1 本阶段必须维护的不变量

- [ ] object-store head CAS 语义与 reference contract 一致；
- [ ] ETag 不被假设为 payload checksum；
- [ ] listing 不参与 committed state determination；
- [ ] multipart 未完成对象不可被 manifest 引用；
- [ ] credentials 不进入 Git/log/artifact；
- [ ] MinIO 与 public cloud 结果严格区分。

### 7.2 必须覆盖的故障与反例

- [ ] PUT/CAS response loss；
- [ ] 429/5xx/timeout；
- [ ] stale If-Match；
- [ ] multipart part/complete crash；
- [ ] list omission/duplicate；
- [ ] metadata service restart；
- [ ] credentials missing/expired；
- [ ] orphan multipart。

## 8. 验收标准

以下条件是阶段 gate，不是建议。Maker 必须给出命令、退出码和 artifact 路径；Checker 必须逐项复核。

- [ ] P09-A01：S3 backend 通过通用 storage contract；
- [ ] P09-A02：head conditional update 在 competing writers 下单 winner；
- [ ] P09-A03：response-loss/multipart crash 幂等恢复；
- [ ] P09-A04：correctness 不依赖 listing；
- [ ] P09-A05：MinIO transactional E2E 与 POSIX state digest 一致；
- [ ] P09-A06：hybrid baseline 可独立配置和测量；
- [ ] P09-A07：云依赖为 optional pinned extra；
- [ ] P09-A08：无凭据和未批准时 public cloud tests 安全 skip；
- [ ] P09-A09：Checker 检查 secret/cost/list assumptions。
- [ ] P09-A10：所有可重试 mutation 用 request identity 区分 after-effect retry 与独立调用，并对 SDK setup/publish/abort/cleanup 完成 typed-error matrix；
- [ ] P09-A11：MinIO/云 probe 的 fail、inconclusive、queued-cancelled 和 retry 均保留 manifest lineage，最终 Checker 在最终干净 commit 重放 contract 和历史反例。

## 9. 验证矩阵

| 层级 | 要求 |
|---|---|
| 本地 | SDK unit/mock + 真实 MinIO integration（环境允许时）必须。 |
| Miyabi login | 仅静态；不得启动服务或 runtime。 |
| Miyabi compute | 只有站点策略允许时运行 MinIO/client E2E；否则在独立环境完成。 |
| 公共云 | 人工批准后；记录 provider/region/API consistency/cost。 |
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

- [ ] 真实 S3/GCS/Azure 运行、凭据使用、跨区域流量或付费资源必须审批；
- [ ] 新增持久化/共享服务或对外暴露端口前需审批；job-owned、隔离且随测试退出的 MinIO/临时端口由 agent 自主使用。
- [ ] 仅在用户显式选择 P09 后，MinIO/local conformance 和默认不执行的 public-cloud harness 才构成本可选 phase 的 gate；未获公共云批准不阻止已选中的 P09 `completed`。P09 完成后不自动启动其他 phase。

## 12. 阻塞与停止规则

- 同一根因连续三次修复后仍未通过同一 gate：写入 `BLOCKERS.md` 并停止扩大改动。
- 若实现当前目标需要调整 research contract、failure model、协议线性化点或数值语义：agent 记录 ADR、backend capability evidence 和兼容性影响，经 Checker 复核后继续；只有 materially 超出用户授权研究目标或涉及真实凭据/付费资源时才停止请求决策。
- 需要在 Miyabi 登录节点运行被禁止的 runtime 命令：停止，转为 PBS allocation。
- 单个 Miyabi 作业可由 agent 自主决定并提交（`select<=16`、`walltime<=02:00:00`，包括 9 节点）；超出该范围或需要付费公共云资源时停止并取得明确批准。
- 发现基础分支包含未合并的用户改动或基线漂移：保留改动，生成 drift report，不得覆盖。

## 13. 阶段完成报告模板

报告 backend/provider/version、contract cases、conditional winner、multipart faults、list-independence、MinIO vs POSIX digest、hybrid mode和云审批状态。

## 14. 可直接复制给 Codex 的启动指令

```text
仅在用户显式选择 object-store 可选实现后，使用 miyabi-development skill 执行 P09。

仓库：https://github.com/UnbearableFate/fs_based_decoupled_diloco
规划基线：codex/fs-diloco-miyabi @ afc50a1e179c64321645b278b2497ea3ab3fe24d
目标分支：codex/duraloco-p09-object-store
阶段计划：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/14_P09_OBJECT_STORE_BACKEND_AND_HYBRID_BASELINE_OPTIONAL.md
共同契约：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/00_CODEX_LOOP_OPERATING_CONTRACT.md

先执行 hostname、git status --short --branch、git rev-parse HEAD，并读取 AGENTS.md、共同契约、当前阶段文件、上一阶段报告和相关研究草稿。若基线漂移，先写 drift report；不要 reset 用户改动。

按阶段文件中的 Loop 顺序工作。每个 Loop 都要先建立失败测试或可执行规范，再做最小实现，随后运行分层验证和独立 checker。持续更新 plans/duraloco/STATE.yaml；不要自动合并 main；不要在 Miyabi 登录节点运行 pytest、torch/transformers/datasets 导入、训练、mpirun 或其他 runtime 工作。

结束时在全部必需 gate 有证据且 Checker 通过时标记 completed，并按依赖图自动启动下一个可执行 goal/phase，不等待用户审核；否则输出 BLOCKED，并给出最小复现、已尝试方案和下一项决策。
```

## 15. 参考输入

- `references/DuraLoCo_research_draft_zh.md`
- 现有实现：`https://github.com/UnbearableFate/fs_based_decoupled_diloco/tree/codex/fs-diloco-miyabi`
- Miyabi skill：`https://github.com/UnbearableFate/miyabi-development`
