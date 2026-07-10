---
plan_id: "P01"
title: "Protocol v2 Schema、身份与严格验证"
status: "planned"
date: "2026-07-10"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/fs-diloco-miyabi"
planning_basis_commit: "011e180980e90c500bcd479a594ba47e507bb5d1"
target_branch: "codex/duraloco-p01-protocol-v2"
depends_on:
  - "P00"
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
human_approval_gates:
  - "若需要改变 P00 冻结的 proposal identity、payload kind、recovery 或 numeric contract，必须审批。"
---

# P01 — Protocol v2 Schema、身份与严格验证

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

建立 DuraLoCo Protocol v2 的机器可验证数据边界：canonical manifests、content identities、严格因果验证、payload 完整性和 quarantine。修复当前协议会接受 future base、路径越界、错误 hash/size/shape/dtype/NaN 等问题的根因。

### 1.1 本阶段支撑的研究主张

DuraLoCo 的任何 crash consistency 与 exactly-once 结论都以前置输入验证为条件。本阶段提供“只有完整、同 run、因果合法且内容一致的 proposal 才能进入选择集合”的可测保证。

### 1.2 完成后的系统增量

新增独立 `protocol` package 和 v1→v2 只读迁移适配器；现有 runtime 可在 feature flag 下调用 validator，但尚不切换 commit path。

## 2. 前置条件

- [ ] P00 research contract 已批准；
- [ ] 参数索引与 fragment layout digest 生成规则已有基线；
- [ ] 确定是否允许新增 jsonschema/pydantic 依赖；若未批准，使用标准库实现。

## 3. 范围

### 3.1 必须完成

- [ ] Proposal、Commit、Frontier、Head、ObjectRef、DropDecision schema；
- [ ] canonical JSON 与稳定 digest；
- [ ] learner session + sequence + content identity；
- [ ] run/generation/model/index/layout/base/frontier 因果验证；
- [ ] payload path containment、size、SHA-256、safetensors key/shape/dtype/finite 验证；
- [ ] future-version/stale/conflicting-identity 拒绝；
- [ ] 错误分类、quarantine 和审计记录；
- [ ] v1 manifest read-only adapter。

### 3.2 明确不做

- 不实现 head CAS；
- 不改变 syncer commit pipeline；
- 不实现 S3；
- 不让 v1 和 v2 写入同一 authority namespace。

## 4. 预期仓库变更

建议新增：

```text
fs_diloco/protocol/
  __init__.py
  schemas.py
  canonical_json.py
  identities.py
  manifests.py
  validation.py
  errors.py
  invariants.py
  v1_adapter.py
tests/protocol/
  test_canonical_json.py
  test_identities.py
  test_schema_roundtrip.py
  test_validation_matrix.py
  test_quarantine.py
  golden/
```

可能小幅修改 `param_index.py`、`fragment_index.py` 以提供稳定 digest API；旧调用保持兼容。

## 5. 需要先冻结的设计决策

- [ ] D-0101：identity-bearing manifest 中是否禁止 JSON float；推荐禁止或使用规范 decimal string；
- [ ] D-0102：proposal ID 的精确定义及自引用规避；
- [ ] D-0103：payload_kind 初版选择 `pseudo_gradient`、`local_end_weight` 或二者；
- [ ] D-0104：finite check 是全量还是可配置抽样；correctness suite 必须全量；
- [ ] D-0105：quarantine object layout 与保留策略；
- [ ] D-0106：v1 adapter 是仅解析、仅导入，还是允许迁移工具重写。

每项决策必须写入 `plans/duraloco/DECISIONS.md`，包含：上下文、候选方案、所选方案、拒绝方案、兼容性影响和可逆性。不得把未决语义隐藏在实现细节中。

## 6. Codex 执行循环

### Loop 1 — Canonical encoding 与 ID

**目标。** 相同逻辑内容在所有 host/backend 上生成相同 bytes 和 digest。

**先产生的失败证据或规范。**

- [ ] 为 key order、Unicode、hex 大小写、NaN/Inf、额外字段、float 表示、重复 identity 制作 golden tests。

**实现任务。**

- [ ] 实现 canonical JSON；
- [ ] 定义 ObjectRef 和各类 content IDs；
- [ ] 生成跨进程 golden vectors；
- [ ] 禁止隐式时间戳进入 content identity。

**本循环验证。**

- [ ] golden bytes/digests 稳定；
- [ ] 随机 key order 不改变 digest；
- [ ] 非法数值和 unknown fields 被拒绝。

**本循环持久化输出。**

- [ ] canonical spec；
- [ ] golden vector fixtures；
- [ ] identity API。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 2 — Schema types

**目标。** 让协议对象具有显式、不可变、可 round-trip 的类型。

**先产生的失败证据或规范。**

- [ ] 缺字段、错误类型、额外字段、范围错误和未知 enum 均有失败用例。

**实现任务。**

- [ ] 实现 Proposal/Commit/Frontier/Head/ObjectRef/DropDecision；
- [ ] 分离 identity fields 与 observational fields；
- [ ] 增加 protocol_version/run_generation。

**本循环验证。**

- [ ] round-trip 保持 canonical bytes；
- [ ] schema version mismatch 返回 typed error；
- [ ] 所有 required fields 有测试。

**本循环持久化输出。**

- [ ] protocol schemas；
- [ ] JSON examples；
- [ ] schema documentation。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 3 — 分层 validator

**目标。** 将 metadata、causal 和 payload 验证分层并可审计。

**先产生的失败证据或规范。**

- [ ] 复现 path escape、错误 hash/size、wrong key/shape/dtype、NaN、future base、wrong run/layout；
- [ ] 验证不会因 KeyError 终止 scanner。

**实现任务。**

- [ ] 实现 fast metadata validation；
- [ ] 实现 current frontier 上下文的 causal validation；
- [ ] 实现 payload read/verify；
- [ ] 错误映射到 retryable/quarantine/fatal categories。

**本循环验证。**

- [ ] 完整恶意/损坏矩阵；
- [ ] future base 永不 eligible；
- [ ] shared root 外路径永不读取。

**本循环持久化输出。**

- [ ] validator；
- [ ] error taxonomy；
- [ ] validation report object。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 4 — Quarantine 与兼容适配

**目标。** 错误 proposal 不崩溃 syncer且不会悄然消失。

**先产生的失败证据或规范。**

- [ ] 同一坏 manifest 多次发现；冲突 proposal_id；v1 缺 v2 字段。

**实现任务。**

- [ ] 实现 quarantine record；
- [ ] 保证重复 quarantine 幂等；
- [ ] 实现 v1 read-only adapter 和显式 compatibility mode；
- [ ] 增加 inspect CLI。

**本循环验证。**

- [ ] 重复扫描无重复副作用；
- [ ] 冲突 identity 被升级为 fatal protocol conflict；
- [ ] 默认 v2 namespace 不接受 v1。

**本循环持久化输出。**

- [ ] quarantine module；
- [ ] migration docs；
- [ ] CLI evidence。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

## 7. 不变量与失败注入

### 7.1 本阶段必须维护的不变量

- [ ] 只有 validator 返回 `VALID` 的 proposal 才能进入 eligibility；
- [ ] proposal_id 对应唯一 canonical identity 和 payload hash；
- [ ] `base_version <= current_version`；
- [ ] 路径不能逃逸 backend namespace；
- [ ] manifest 不一致不会导致进程级未捕获异常；
- [ ] v1/v2 authority namespace 不混写。

### 7.2 必须覆盖的故障与反例

- [ ] truncated JSON；
- [ ] unknown fields；
- [ ] duplicate keys（parser 策略需定义）；
- [ ] payload missing/short/extra bytes；
- [ ] checksum mismatch；
- [ ] wrong safetensors key；
- [ ] shape/dtype mismatch；
- [ ] NaN/Inf；
- [ ] future/stale base；
- [ ] same proposal ID different content；
- [ ] wrong run/generation/layout/index。

## 8. 验收标准

以下条件是阶段 gate，不是建议。Maker 必须给出命令、退出码和 artifact 路径；Checker 必须逐项复核。

- [ ] P01-A01：所有 protocol objects 有 canonical encoding 和 stable digest golden tests；
- [ ] P01-A02：future base、path escape、wrong hash/size/key/shape/dtype、NaN/Inf 均被拒绝；
- [ ] P01-A03：坏输入被 typed quarantine，不使 scanner/syncer crash；
- [ ] P01-A04：同一 identity 不允许映射到不同内容；
- [ ] P01-A05：v1 adapter 默认不写 v2 authority；
- [ ] P01-A06：validator 不依赖目录 listing 或 filename 提供关键字段；
- [ ] P01-A07：现有非协议 tests 无回归；
- [ ] P01-A08：Checker 增加至少一个 malformed manifest 反例并通过。

## 9. 验证矩阵

| 层级 | 要求 | 核心命令/证据 |
|---|---|---|
| 本地静态 | 必须 | compile、schema examples、golden fixture check。 |
| 本地 unit | 必须 | `tests/protocol/` 全部通过；随机 malformed corpus。 |
| Miyabi login | 仅静态 | `bash -n`、`py_compile`；不得运行 pytest。 |
| Miyabi 1-node | 条件 | 仅在本地缺少 safetensors/torch 运行环境时跑 payload validator tests。 |
| 多节点 | 不要求 | 协议输入边界不需要多节点。 |

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

- [ ] 若需要改变 P00 冻结的 proposal identity、payload kind、recovery 或 numeric contract，必须审批。

## 12. 阻塞与停止规则

- 同一根因连续三次修复后仍未通过同一 gate：写入 `BLOCKERS.md` 并停止扩大改动。
- 需要改变 research contract、failure model、协议线性化点或数值语义：停止并请求人工决策。
- 需要在 Miyabi 登录节点运行被禁止的 runtime 命令：停止，转为 PBS allocation。
- 单个 Miyabi 作业可由 agent 自主决定并提交（`select<=16`、`walltime<=02:00:00`，包括 9 节点）；超出该范围或需要付费公共云资源时停止并取得明确批准。
- 发现基础分支包含未合并的用户改动或基线漂移：保留改动，生成 drift report，不得覆盖。

## 13. 阶段完成报告模板

记录 schema version、golden digest 集、malformed case 数、quarantine 分类、v1 compatibility decision、未决协议语义。

## 14. 可直接复制给 Codex 的启动指令

```text
使用 miyabi-development skill 执行 P01。

仓库：https://github.com/UnbearableFate/fs_based_decoupled_diloco
规划基线：codex/fs-diloco-miyabi @ 011e180980e90c500bcd479a594ba47e507bb5d1
目标分支：codex/duraloco-p01-protocol-v2
阶段计划：plans/duraloco/codex/02_P01_PROTOCOL_V2_SCHEMAS_AND_VALIDATION.md
共同契约：plans/duraloco/codex/00_CODEX_LOOP_OPERATING_CONTRACT.md

先执行 hostname、git status --short --branch、git rev-parse HEAD，并读取 AGENTS.md、共同契约、当前阶段文件、上一阶段报告和相关研究草稿。若基线漂移，先写 drift report；不要 reset 用户改动。

按阶段文件中的 Loop 顺序工作。每个 Loop 都要先建立失败测试或可执行规范，再做最小实现，随后运行分层验证和独立 checker。持续更新 plans/duraloco/STATE.yaml；不要自动合并 main；不要在 Miyabi 登录节点运行 pytest、torch/transformers/datasets 导入、训练、mpirun 或其他 runtime 工作。

结束时只在全部 gate 有证据时标记 ready_to_merge；否则输出 BLOCKED，并给出最小复现、已尝试方案和下一项决策。
```

## 15. 参考输入

- `references/DuraLoCo_research_draft_zh.md`
- 现有实现：`https://github.com/UnbearableFate/fs_based_decoupled_diloco/tree/codex/fs-diloco-miyabi`
- Miyabi skill：`https://github.com/UnbearableFate/miyabi-development`
