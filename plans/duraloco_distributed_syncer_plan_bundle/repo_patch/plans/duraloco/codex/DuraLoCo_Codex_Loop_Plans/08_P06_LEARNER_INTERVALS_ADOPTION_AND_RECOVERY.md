---
plan_id: "P06"
title: "Learner Contribution Intervals、Adoption 与 Warm Recovery"
status: "completed_in_repository"
date: "2026-07-11"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/duraloco-p05-syncer-failover"
planning_basis_commit: "419577899a64a12cc602870d059a092f9319bed1"
target_branch: "codex/duraloco-p06-learner-protocol"
verified_implementation_commit: "2581a4d6286c7d0666f76aa3cc9d8122e66f6d25"
checker_persistence_commit: "030129e045c4e5a2abb80eb100a0e28fb78d384d"
archive_commit: "06e3ca2299d5eb1a720c1d8f9107af5223095525"
depends_on:
  - "P05"
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
agent_decision_gates:
  - "inner optimizer adoption policy 默认值由 agent 基于 numeric/recovery evidence 决定并经独立 Checker 复核；"
  - "SQLite-free learner/syncer 路径在兼容性和 1/2/9-node gates 通过后由 agent 自动推进。"
human_approval_gates: []
---

# P06 — Learner Contribution Intervals、Adoption 与 Warm Recovery

> 本文件是可直接交给 Codex 执行的阶段计划，不是背景说明。执行前必须同时读取：
>
> 1. 仓库根目录 `AGENTS.md`；
> 2. `00_CODEX_LOOP_OPERATING_CONTRACT.md`；
> 3. `miyabi-development` skill 的 `SKILL.md`；
> 4. 上一阶段的 `PHASE_REPORT.md`、`STATE.yaml` 和未关闭的决策记录；
> 5. `P00_P04_IMPLEMENTATION_LESSONS.md`；
> 6. `SQLITE_FREE_SYSTEM_DESIGN.md`；
> 7. `M00_IMPLEMENTATION_LESSONS.md`；
> 8. `references/DuraLoCo_research_draft_zh.md` 中与本阶段对应的章节。
>
> P06 必须以 P05 双语报告记录的 verified commit 为基线。执行开始时验证真实 commit；若仓库已经前进，先产生 drift report，不得强制 reset 或丢弃用户改动。

## 1. 阶段使命

在 M00 已验证的 marker-last immutable publication、committed-successor backpressure、bfloat16 proposal transport 和 P05 authoritative stop/fencing 上，完成 learner session/sequence、interval base freeze、boundary-only adoption、warm restart 与数据/RNG cursor hooks。不重建并行 `learner_v2` runtime。

### 1.1 本阶段支撑的研究主张

DuraLoCo 的 selected proposal 表示一段唯一 local work，而不是可能重复包含已应用训练进展的任意参数快照；learner crash 最多损失未提交 interval，并能从 committed frontier warm restart。

### 1.2 完成后的系统增量

现有 `fs_diloco.learner` 增量获得可重放 interval/session 语义、boundary adoption 和 warm recovery，并与 P05 production syncer 完成 end-to-end run；公共 entrypoint 和 authority path 保持单一。

> **当前仓库对齐说明（2026-07-11）。** P06 已由 archive commit `06e3ca2`
> 完成，权威验收范围是 `P06-A01`–`P06-A20`，Checker verdict 为 `PASS`。
> 本计划包不得追溯追加 P06-A21–A25 或改写该 verdict。分散路线所需的 CRS
> characterization/oracle trace 由 P06A Loop 1 从 P06 archive tip 建立；旧 P06
> 1/2/9-node artifacts是baseline，不是尚未执行的P06A实现证据。

## 2. 前置条件

- [ ] P05 production syncer lease/fencing/authoritative-stop path 已通过；
- [ ] proposal payload kind 已冻结；
- [ ] fragment schedule 初版定义；
- [ ] warm restart 的非精确性已在 research contract 中明确。
- [ ] M00/P05 forbidden-surface gate 仍证明没有 SQLite 或替代嵌入式数据库。
- [ ] M00 marker-last publication、learner no-head-CAS、same-base flood rejection、bfloat16 transport/float32 committed-state 反例仍通过。

## 3. 范围

### 3.1 必须完成

- [ ] learner_session_id 与 durable monotonic sequence；
- [ ] interval base/frontier freeze；
- [ ] local work token/step accounting；
- [ ] proposal payload/content publication；
- [ ] response-loss/idempotent retry；
- [ ] publication request ID 持久化，不以 payload equality 推断 retry；
- [ ] global adoption 仅在 interval boundary；
- [ ] per-fragment base vector/cursor；
- [ ] warm restart；
- [ ] global stop 优先级；
- [ ] inner optimizer adoption policies 与实验标记；
- [ ] RNG/data cursor 抽象 hooks。
- [ ] publication 后持续等待 committed successor、authoritative stop 或明确 no-progress outcome，不以单次空 listing/短 timeout 开始重叠 interval；
- [ ] absent optional identity field 使用 canonical omission，不写 `null`；
- [ ] typed validated publication result 在当次 attempt 内复用，不重复 read/hash/finite-check/publish 大对象。

### 3.2 明确不做

- 不实现 exact learner capsule；
- 不实现 lazy streaming dataset 完整重构，除非为 cursor 正确性所需；
- 不实现 SACC 动态 local interval；
- 不保证 warm restart bitwise continuation。
- 不为 session、sequence、cursor 或 adoption 引入本地数据库；持久事实必须是 immutable object/commit，查询状态必须由 replay 派生。

## 4. 预期仓库变更

```text
fs_diloco/learner.py
fs_diloco/learner_protocol/
  session.py
  interval.py
  publication.py
  adoption.py
  recovery.py
  data_cursor.py
  rng_state.py
tests/learner_protocol/
  test_interval_base_freeze.py
  test_sequence_idempotency.py
  test_boundary_adoption.py
  test_warm_restart.py
  test_stop_priority.py
  test_inner_optimizer_policy.py
```

不得建立与现有 `fs_diloco.learner` 并行的 runtime/default path。可抽取无冲突的纯 policy/state modules，但公共 entrypoint、publication 和 adoption 路径必须唯一。

## 5. 需要先冻结的设计决策

- [ ] D-0601：proposal 是 pseudo-gradient 还是 local end weight；
- [ ] D-0602：同 session/base 的 superseding proposal 是否允许；
- [ ] D-0603：fragment schedule 是 committed round-robin、acceptable set 还是 learner-local cursor；
- [ ] D-0604：inner optimizer reset-all/reset-fragment/preserve 的默认策略；
- [ ] D-0605：target token 计数定义；
- [ ] D-0606：session sequence 在 immutable publication/request object 中的 durable identity，以及如何从 log/listing 恢复；不得使用数据库 counter。
- [ ] D-0607：publication/adoption request identity 与 committed-ancestry reconciliation；
- [ ] D-0608：reference、runtime 与 replay 共用的 interval/adoption policy kernel 边界。
- [ ] D-0609：M00 bfloat16 proposal transport 与 float32 aggregation/committed params 的 implementation identity 如何在 interval/adoption manifest 中冻结；
- [ ] D-0610：committed-successor/no-progress/authoritative-stop 等待状态机，以及 P05 epoch/owner 变更时如何重新绑定 base；
- [ ] D-0611：optional predecessor identity 的 canonical omission 和 cross-session 边界。

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
- [ ] 不同 request ID 但相同 payload 的并发 publication。

**实现任务。**

- [ ] 使用 storage API immutable puts；
- [ ] 先 payload 后 manifest；
- [ ] 用 immutable publication/request identity 恢复重试，不保存本地持久化 publication state；
- [ ] 冲突 fail closed。
- [ ] 复用 M00 marker-last publication 和 typed validated bytes/result；
- [ ] publication 后进入 committed-successor/stop/no-progress 等待状态，新 epoch/head 到达前不开始重叠 interval。

**本循环验证。**

- [ ] 任意 publication crash 重启后最多一个 canonical proposal；
- [ ] syncer 可验证/消费。
- [ ] payload 发布后 marker 前 crash 留下的 orphan 不可见为 proposal，恢复可重用同 ObjectRef；
- [ ] absent optional predecessor 不以 `null` 进入 identity，显式 `null`/conflict fail closed。

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
- [ ] interval/adoption 选择调用与 reference/replay 相同的 policy kernel；

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
- [ ] learner restart 只从 committed frontier 与 immutable publication facts 恢复，本地 `RuntimeView` 丢失不影响 correctness。

### 7.2 必须覆盖的故障与反例

- [ ] crash before/after payload、manifest、ack；
- [ ] restart sequence reuse；
- [ ] head changes mid-interval；
- [ ] multiple fragment updates；
- [ ] global stop race；
- [ ] same ID conflicting payload；
- [ ] slow learner stale proposal。
- [ ] 单次 listing omission/短 timeout 后的 committed-successor backpressure；
- [ ] payload-before-marker crash 与 marker response loss；
- [ ] epoch/owner 在 interval 中切换；
- [ ] bfloat16 proposal 与 float32 committed state numeric/identity 回归。

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
- [ ] P06-A10：2-node learner + P05 production syncer E2E。
- [ ] P06-A11：`fs-diloco-learner` 和 `python -m fs_diloco.learner` 一致使用 SQLite-free authority，旧 DB flags/config keys 明确 fail closed。
- [ ] P06-A12：publication response-loss 以 request identity 辨识，并覆盖同 ID/同内容、不同 ID/同内容和同 ID/冲突内容；
- [ ] P06-A13：reference/runtime/replay 在 adversarial proposal order、restart 与 cross-session boundary 上生成相同 adoption digest；
- [ ] P06-A14：最终 1/2-node 证据包含失败/取消/重试 manifests 和 `parent_run_id` lineage，当前 state/report/tests 一致。
- [ ] P06-A15：active source/config/CLI/scripts/tests/new artifacts 中没有 SQLite/embedded-DB 依赖，session/sequence 可在空本地目录下恢复且不重用。
- [ ] P06-A16：9-node GPT-2/WikiText-2 terminal run 以 1 syncer + 8 learners、`inner_steps=50`、10 outer transitions 在 15 分钟 walltime 内通过，且 interval/adoption/warm-restart 断言全部成立。
- [ ] P06-A17：重放 M00 same-base flood 反例，publication 后的空 listing/短 timeout 不产生重叠 interval，并在 payload read 前拒绝已消费 base；
- [ ] P06-A18：marker-last publication 的 payload/marker crash-response-loss matrix 通过，learner 包含 immutable publication 能力但静态和 runtime audit 均证明无 head-CAS surface；
- [ ] P06-A19：absent optional predecessor 采用 canonical omission，`null`/unknown/conflicting field 的 identity tests fail closed；
- [ ] P06-A20：M00 bfloat16 proposal transport/float32 aggregation 与 committed state 在 full/fragment、restart、adoption 中的 numeric/implementation digest 不回归，且一次 attempt 不重复大对象 I/O/验证。

## 9. 验证矩阵

| 层级 | 要求 |
|---|---|
| 本地 | interval/publication/restart tests；tiny synthetic E2E。 |
| Miyabi 1-node | 必须：真实 model/data ≤10 optimizer steps，finite loss，至少一个 production commit/boundary adoption。 |
| Miyabi 2-node | 必须：syncer 与 learner 分节点，proposal→commit→adopt→stop。 |
| 9-node | 必须：GPT-2/WikiText-2 1S+8L、50×10、15 分钟 terminal gate，包含 interval/adoption/warm-restart 断言。 |

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
- [ ] SQLite-free learner/syncer 兼容性和 1/2/9-node gates 通过后由 agent 自动推进；
- [ ] 当前仓库中的P06已完成；计划包应用后的唯一下一阶段是P06A。该handoff是路线修订，不追溯改变P06-A01–A20 verdict；可选P09不在此处启动。

## 12. 阻塞与停止规则

- 同一根因连续三次修复后仍未通过同一 gate：写入 `BLOCKERS.md` 并停止扩大改动。
- 若实现当前目标需要调整 research contract、failure model、协议线性化点或数值语义：agent 记录 ADR、numeric/recovery evidence 和兼容性影响，经 Checker 复核后继续；只有 materially 超出用户授权研究目标时才停止请求决策。
- 需要在 Miyabi 登录节点运行被禁止的 runtime 命令：停止，转为 PBS allocation。
- 单个 Miyabi 作业可由 agent 自主决定并提交（`select<=16`、`walltime<=02:00:00`，包括 9 节点）；超出该范围或需要付费公共云资源时停止并取得明确批准。
- 发现基础分支包含未合并的用户改动或基线漂移：保留改动，生成 drift report，不得覆盖。
- 非 transient 9-node terminal 失败后禁止立即同 shape 重提；必须先完成 workflow review、targeted 1-node benchmark 和同 clean commit 1→2-node 重验收，再只提交一次新 retry。

## 13. 阶段完成报告模板

报告 sessions、interval lineage、proposal IDs、adopted frontiers、warm restart lost/repeated tokens、optimizer policy、1/2-node run IDs。

## 14. 可直接复制给 Codex 的启动指令

```text
使用 miyabi-development skill 执行 P06。

仓库：https://github.com/UnbearableFate/fs_based_decoupled_diloco
规划基线：P05 双语报告中的 verified commit（执行时解析）
目标分支：codex/duraloco-p06-learner-protocol
阶段计划：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/08_P06_LEARNER_INTERVALS_ADOPTION_AND_RECOVERY.md
共同契约：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/00_CODEX_LOOP_OPERATING_CONTRACT.md
系统设计：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/SQLITE_FREE_SYSTEM_DESIGN.md
M00 经验：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/M00_IMPLEMENTATION_LESSONS.md

先执行 hostname、git status --short --branch、git rev-parse HEAD，并读取 AGENTS.md、共同契约、当前阶段文件、上一阶段报告和相关研究草稿。若基线漂移，先写 drift report；不要 reset 用户改动。

按阶段文件中的 Loop 顺序工作。每个 Loop 都要先建立失败测试或可执行规范，再做最小实现，随后运行分层验证和独立 checker。持续更新 plans/duraloco/STATE.yaml；不要自动合并 main；不要在 Miyabi 登录节点运行 pytest、torch/transformers/datasets 导入、训练、mpirun 或其他 runtime 工作。

本文件保留为已完成P06的执行规范。当前仓库不要重跑或改写P06 verdict；从archive commit `06e3ca2`按08A计划开始P06A characterization/decomposition，不要直接启动P07/P08。
```

## 15. 参考输入

- `references/DuraLoCo_research_draft_zh.md`
- 现有实现：`https://github.com/UnbearableFate/fs_based_decoupled_diloco/tree/codex/fs-diloco-miyabi`
- Miyabi skill：`https://github.com/UnbearableFate/miyabi-development`
