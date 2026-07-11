---
plan_id: "P05"
title: "生产 Syncer 集成、Lease/Fencing 与 Failover"
status: "planned"
date: "2026-07-11"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/duraloco-m00-sqlite-free-rebase"
planning_basis_commit: "89ae48aae5956b09fc6685074d3ea0eaea36b816"
target_branch: "codex/duraloco-p05-syncer-failover"
depends_on:
  - "M00"
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
agent_decision_gates:
  - "M00 已将 SQLite-free runtime 设为唯一路径；P05 只在 lease/fencing 和 1/2/9-node gates 通过后推进。"
human_approval_gates:
  - "任何 destructive lifecycle 操作需要批准；历史 SQLite run 不转换。"
---

# P05 — 生产 Syncer 集成、Lease/Fencing 与 Failover

> 本文件是可直接交给 Codex 执行的阶段计划，不是背景说明。执行前必须同时读取：
>
> 1. 仓库根目录 `AGENTS.md`；
> 2. `00_CODEX_LOOP_OPERATING_CONTRACT.md`；
> 3. `miyabi-development` skill 的 `SKILL.md`；
> 4. 上一阶段的 `PHASE_REPORT.md`、`STATE.yaml` 和未关闭的决策记录；
> 5. `P00_P04_IMPLEMENTATION_LESSONS.md`；
> 6. `SQLITE_FREE_SYSTEM_DESIGN.md` 和 M00 最终报告；
> 7. `M00_IMPLEMENTATION_LESSONS.md` 和 `plans/duraloco/reviews/M00_PRODUCTION_REPLAY_WORKFLOW_REVIEW.md`；
> 8. `references/DuraLoCo_research_draft_zh.md` 中与本阶段对应的章节。
>
> P05 必须以 M00 corrected archival tip `89ae48aae5956b09fc6685074d3ea0eaea36b816` 为基线，其 verified runtime implementation 为 `c052438a3cfe5e16c3b154fc842f32dcd61ec6ff`。执行开始时必须证明 target branch 包含该 archival tip；现有 P05 branch 若落后，仅做保留历史的 fast-forward/正常集成，不得 reset 或丢弃用户改动。

## 1. 阶段使命

在 M00 已验证的 `fs_diloco.syncer`、`ProductionTransactionalLog`、`RuntimeView` 和 `ProposalCatalog` 上增量加入 lease/fencing、standby takeover、启动 reconciliation 和 authoritative stop。不重建并行 `syncer_v2` runtime；必须保留 M00 的 strict/memoized replay、marker-last publication、typed production validation 和分阶段 telemetry。

### 1.1 本阶段支撑的研究主张

syncer 不再是持有不可恢复本地状态的单点；在进程崩溃或 leader 切换后，新实例仅凭 durable log 恢复，并且旧 leader 无法以低 epoch 推进 head。

### 1.2 完成后的系统增量

在唯一 SQLite-free syncer runtime 上支持 synthetic production path、双 syncer chaos 和 failover；不保留数据库版 runtime 或双写开关。

## 2. 前置条件

- [ ] M00 全部 gate 和 P00–P04 重验收通过；
- [ ] P03 Miyabi CAS contract 通过；
- [ ] 明确 lease 时钟/TTL failure assumptions；
- [ ] active config/CLI forbidden-surface 扫描中 SQLite/embedded DB 为零。
- [ ] M00 corrected final Checker、41-ID mapping、real-prefix replay benchmark 和 7m24s terminal baseline 都可读；
- [ ] P05 branch ancestry 包含 `89ae48a`，并记录 M00 observed strict replay 6.177/6.875s 与 steady-state post-CAS replay 4.835–4.940s 作为 TTL/RTO 初始测量输入，而非安全假设。

## 3. 范围

### 3.1 必须完成

- [ ] syncer ingest 使用 P01 validator/quarantine；
- [ ] quorum selection 与 commit pipeline 解耦；
- [ ] lease acquisition/renewal、monotonic fencing epoch；
- [ ] lease/commit/stop mutation 使用持久化 request ID，区分丢响应重试与独立的相同调用；
- [ ] head commit 检查 epoch；
- [ ] standby startup full replay/`RuntimeView` rebuild；
- [ ] response-loss reconciliation 查询 committed ancestry，不只比较当前 head；
- [ ] 取消持久 `selected` 状态；
- [ ] stop/request/terminal 状态通过 log 提交；
- [ ] 可控 failpoints；
- [ ] 对应 M00 单一 runtime config namespace，不新增 DB 兼容开关。
- [ ] takeover 必须 empty-cache strict replay，verified ObjectRef memoization 不跨 owner/session；
- [ ] epoch/owner 变更后丢弃旧的未提交 selection/validated bytes，重做 cheap rejection、validation 和 selection；
- [ ] lease/renew/fence/takeover/stop 独立 stage telemetry，不混入单一 global interval。

### 3.2 明确不做

- 不完成 learner v2 publication/adoption；可用 test producer；
- 不实现 compaction/GC；
- 不实现 SACC；
- 不读取、迁移或转换旧 SQLite run；历史 checkpoint 只能按 M00 的新 generation warm-start 流程使用。

## 4. 预期仓库变更

```text
fs_diloco/syncer.py                 # 保留现有公共 runtime/entrypoint
fs_diloco/log/production.py         # epoch/owner-aware transactional commit
fs_diloco/log/replay.py             # strict/memoized ownership-bound replay
fs_diloco/log/model.py              # lease/fence/stop control schemas
fs_diloco/runtime_view.py           # committed coordination/stop projection
fs_diloco/proposal_catalog.py       # epoch/base cheap rejection + typed validation
fs_diloco/coordination/
  __init__.py
  lease.py
  fencing.py
  clock.py
  state_machine.py
tests/coordination/
  test_reference_state_machine.py
  test_ingest_quarantine.py
  test_commit_pipeline.py
  test_lease_fencing.py
  test_takeover.py
  test_stop_recovery.py
  test_replay_cache_ownership.py
scripts/chaos/
  run_dual_syncer.py
scripts/miyabi/
  run_duraloco_p05_1node.pbs
  run_duraloco_p05_2node.pbs
```

不得创建与现有 `fs_diloco.syncer` 并行的 runtime/policy/replay 实现。可以从现有文件中抽取纯 coordination module，但公共 entrypoint、selection kernel、production transaction 和 replay 契约必须保持单一。

## 5. 需要先冻结的设计决策

- [ ] D-0501：lease 使用 backend conditional object，epoch 如何单调分配；
- [ ] D-0502：clock skew 假设和 lease safety/liveness 分界；
- [ ] D-0503：旧 leader 在 lease 过期后如何被 head CAS fencing；
- [ ] D-0504：stop 作为 commit event 还是 head metadata；
- [ ] D-0505：M00 runtime 的 run/generation namespace 隔离，以及禁止历史 DB run 原地续跑的 fail-closed 语义。
- [ ] D-0506：lease/commit/stop request identity 的持久化位置、conflict 语义和 retry 结果；
- [ ] D-0507：response-loss 在 successor head 已推进时的 ancestry-aware reconciliation 界限。
- [ ] D-0508：fencing epoch/owner 如何由单一 head-CAS 可线性化地生效，避免 lease-object 与 optimizer head 之间的 TOCTOU 双权威；
- [ ] D-0509：control-only transition 与 optimizer transition 的 sequence/count/replay 语义，确保 50×10 中“10”只计 optimizer transitions；
- [ ] D-0510：owner/session 变更时 strict replay、memoization invalidation、uncommitted selection discard 和 corruption fallback；
- [ ] D-0511：TTL/renew margin/takeover RTO 如何从实测 strict replay、storage tail 和 clock-skew envelope 推导；clock 只影响 liveness，不得承担 fencing safety。

每项决策必须写入 `plans/duraloco/DECISIONS.md`，包含：上下文、候选方案、所选方案、拒绝方案、兼容性影响和可逆性。不得把未决语义隐藏在实现细节中。

## 6. Codex 执行循环

### Loop 1 — Coordination 参考状态机与权威边界

**目标。** 在修改 production runtime 前，用纯状态机冻结 acquire/renew/expire/takeover/release/stop 与 optimizer commit 的唯一线性化语义。

**先产生的失败证据或规范。**

- [ ] 双 contender、clock skew、acquire/renew response loss、owner pause/resume、control transition crash 的 model traces；
- [ ] 反例必须能杀死“仅检查 lease file”、“仅检查 wall clock”和“旧 epoch 仍可 CAS”的 mutant。

**实现任务。**

- [ ] 实现 dependency-free coordination reference state machine 和 canonical traces；
- [ ] 冻结 owner/session/epoch/request identity 和 control-only transition schema；
- [ ] 明确 lease observational object 与 head-anchored fencing fact 的边界；
- [ ] 确定 optimizer transition count 不被 renew/control transition 污染。

**本循环验证。**

- [ ] exhaustive bounded interleavings 中最多一个 epoch/owner 可 commit；
- [ ] safety 在极端 clock skew 下仍成立，只有 liveness 受影响；
- [ ] reference control replay 不依赖 listing、telemetry 或本地状态。

**本循环持久化输出。**

- [ ] coordination schema/reference model/goldens；
- [ ] M00 authority/replay compatibility matrix。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 2 — Lease 与 fencing

**目标。** 在两个 syncer 存活时只有当前 epoch 可以推进 head。

**先产生的失败证据或规范。**

- [ ] 双实例同时 acquire；旧 leader pause 后恢复；lease renew response lost。

**实现任务。**

- [ ] 实现 acquire/renew/release；
- [ ] 为每个 mutation 生成并持久化 request ID；
- [ ] epoch 写入 lease、commit、head；
- [ ] commit 前后验证 fencing；
- [ ] 记录 owner/session。
- [ ] 所有 head mutation 继续通过一个可审计 transactional head-CAS API；
- [ ] epoch/owner 改变时废弃旧 selection 和 typed validated result，重做 cheap base/epoch filter 后再读大对象。

**本循环验证。**

- [ ] 双 syncer 至多一个 active writer；
- [ ] 旧 epoch CAS 永远失败；
- [ ] standby 最终可 takeover。
- [ ] 同 ID/同内容 retry 幂等；不同 ID/同内容只有一个 winner；同 ID/不同内容 fail closed。

**本循环持久化输出。**

- [ ] lease/fencing module；
- [ ] dual-syncer trace。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 3 — Crash-recoverable runtime

**目标。** 在每个 syncer pipeline stage kill 后自动 reconcile。

**先产生的失败证据或规范。**

- [ ] kill ingest/compute/output/record/frontier/pre/post CAS；
- [ ] 删除全部进程本地派生状态。
- [ ] stale owner 持有 memoized genesis 时观察 head jump + distinct corrupt successor；
- [ ] acquire 成功后、fencing fact 生效前/后、strict replay 前/后的 crash matrix。

**实现任务。**

- [ ] fresh start/takeover 以 empty-cache strict replay 启动；
- [ ] 识别已提交 response-loss；
- [ ] 在 successor commit 已推进 head 后仍能从权威 ancestry 识别原操作；
- [ ] 忽略/记录 orphan；
- [ ] 从 committed log 重建 metrics/`RuntimeView`；
- [ ] 去除 selected-stuck state。
- [ ] 只在完整 strict replay 成功后建立新 owner 的 process-local ObjectRef memoization；
- [ ] 保留 M00 stage timings，新增 acquire/renew/fence/takeover/replay RTO 分段。

**本循环验证。**

- [ ] 所有 kill points 无永久 selected；
- [ ] 恢复后 state digest 与 reference 一致；
- [ ] 下一 commit 可继续。
- [ ] setup/lock/publish/cleanup/replay 的 retryable 与 non-retryable 错误都转换为 typed outcome。
- [ ] strict/memoized digest 一致，失败 replay 不污染 cache，memoization 不跨 owner/session。

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
- [ ] 将现有 `stop.json` 降为 committed stop 的派生导出，learner 以 committed/replayed stop fact 为最终判定。

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
- [ ] 不存在本地持久化状态；清空进程内 view 不改变 authority；
- [ ] 没有 durable `selected` 中间状态；
- [ ] stop 状态可从 log 恢复；
- [ ] 所有 proposal 先验证再选择。
- [ ] lease/renew 时钟只影响 liveness；单调 epoch + owner/session + head CAS 承担 safety；
- [ ] takeover 不继承旧 process memoization 或 selection，首个可写状态必须来自 empty-cache strict replay；
- [ ] learner/standby 无 head-CAS surface；所有 head mutation 经过唯一 audited API；
- [ ] control transitions 不计入 outer optimizer transition count；derived `stop.json` 不是 authority。

### 7.2 必须覆盖的故障与反例

- [ ] two syncers simultaneous start；
- [ ] leader pause beyond TTL then resume；
- [ ] renew response loss；
- [ ] leader kill every stage；
- [ ] process restart 和空本地目录；
- [ ] SQLite/embedded-DB forbidden-surface mutant；
- [ ] bad/future proposal flood；
- [ ] stop before/after CAS crash。
- [ ] acquire/renew/fence/control-event 每个 prepare/publish/CAS/response-loss point；
- [ ] stale owner + head jump + distinct corrupt successor；
- [ ] strict replay 超过 renew margin、clock forward/backward jump、lease object 丢失/损坏；
- [ ] same-base/future-epoch flood 在 payload read 前被拒绝。

## 8. 验收标准

以下条件是阶段 gate，不是建议。Maker 必须给出命令、退出码和 artifact 路径；Checker 必须逐项复核。

- [ ] P05-A01：production syncer 的 optimizer/control apply 全部通过单一 audited transactional head-CAS API；
- [ ] P05-A02：清空全部本地派生状态后，仅凭 committed log/head 重建 `RuntimeView` 并继续；
- [ ] P05-A03：双 syncer 测试无 split-brain；
- [ ] P05-A04：旧 epoch commit 全部被拒；
- [ ] P05-A05：每个 failpoint 后无永久 selected 更新；
- [ ] P05-A06：stop reason 与 terminal state 可重启恢复；
- [ ] P05-A07：公共 syncer entrypoint 只进入 SQLite-free runtime，旧 DB flags/config keys 明确 fail closed；
- [ ] P05-A08：Miyabi 2-node takeover 有 run artifact；
- [ ] P05-A09：Checker 审查 lease/fencing 的 clock assumptions，并独立复核 D-M0010–D-M0012 的 M00 evidence attribution；复核通过后这些决策才成为 P05+ 规范约束。
- [ ] P05-A10：`fs-diloco-syncer` 和 `python -m fs_diloco.syncer` 一致进入 SQLite-free runtime，并通过入口兼容测试。
- [ ] P05-A11：lease/commit/stop response-loss 测试证明 request identity 可区分原请求重试和独立的相同调用；
- [ ] P05-A12：successor 已推进后的延迟重试从 committed ancestry 得到唯一、可重放的结果；
- [ ] P05-A13：最终干净 commit 的 1/2-node Maker 与 Checker 证据均使用 run-manifest schema v2，具有完整 validation shape、attempt manifests/retry lineage，当前 suite、state 和双语 report 同步为绿。
- [ ] P05-A14：active source/config/CLI/scripts/tests/new artifacts 的 SQLite/embedded-DB forbidden-surface 扫描为零。
- [ ] P05-A15：9-node GPT-2/WikiText-2 terminal run 使用 1 个 syncer node + 8 个 learner node、`inner_steps=50`、10 outer transitions，在 15 分钟 walltime 内通过，并覆盖 lease/fencing/takeover 断言；syncer node 的进程拓扑由 P05-A20 定义。
- [ ] P05-A16：coordination reference/model-checker 覆盖 acquire/renew/expire/takeover/release/stop 与 crash/response-loss，并杀死 wall-clock-only、lease-file-only 和 stale-epoch mutants；
- [ ] P05-A17：takeover 以 empty-cache strict replay 开始，旧 owner memoization/selection 不被继承；stale-cache + head-jump + distinct-corrupt-successor 反例 fail closed 且恢复后 strict/memoized digest 一致；
- [ ] P05-A18：TTL/renew/takeover 报告绑定 M00 observed replay baseline、当前 storage tail 和 clock-skew envelope，并证明 safety 不依赖时间预测；
- [ ] P05-A19：authoritative stop/control replay 与 optimizer count 分离，`stop.json` 删除/损坏后可重建，50×10 仍恰好计 10 个 optimizer transitions；
- [ ] P05-A20：terminal run 在第 9 个 syncer node 上运行 active + standby 两个 syncer process，注入一次 active kill/pause 后 standby 接管，仍在 15 分钟内完成 8 learners + 10 outer transitions，零 split-brain/double inclusion。

## 9. 验证矩阵

| 层级 | 要求 |
|---|---|
| 本地 | unit、dual process、kill matrix 必须。 |
| Miyabi login | branch/config/script static only。 |
| Miyabi 1-node | 当前 production syncer + test producers；strict/memoized replay、coordination state machine 与实际 GPU outer path targeted。 |
| Miyabi 2-node | 必须：leader/standby、kill/takeover、旧 leader 恢复；≤10 分钟。 |
| 9-node | 必须：8 learner nodes + 1 syncer node；syncer node 同时运行 active/standby 两进程并注入一次 takeover；50×10、15 分钟、零 split-brain/double inclusion。 |

## 10. Maker–Checker 交接

### Maker 必须提交

- 只包含本阶段范围的 feature branch；
- 实现、测试、文档和历史 run warm-start 说明；
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

- [ ] lease/fencing、1/2/9-node 和 Checker gates 通过后，在 M00 的唯一 runtime 上自动推进；
- [ ] 历史 DB run 保持不变，不存在 migration/conversion gate。
- [ ] P05 必需 gate 通过后自动进入 P06。

## 12. 阻塞与停止规则

- 同一根因连续三次修复后仍未通过同一 gate：写入 `BLOCKERS.md` 并停止扩大改动。
- 若实现当前目标需要调整 research contract、failure model、协议线性化点或数值语义：agent 记录 ADR、migration impact 和 failover evidence，经 Checker 复核后继续；只有 materially 超出用户授权研究目标或需要 destructive migration 时才停止请求决策。
- 需要在 Miyabi 登录节点运行被禁止的 runtime 命令：停止，转为 PBS allocation。
- 单个 Miyabi 作业可由 agent 自主决定并提交（`select<=16`、`walltime<=02:00:00`，包括 9 节点）；超出该范围或需要付费公共云资源时停止并取得明确批准。
- 发现基础分支包含未合并的用户改动或基线漂移：保留改动，生成 drift report，不得覆盖。
- 任何 non-transient 9-node terminal 失败后：立即停止同 shape 重提，先保留 authority/stage/lease timeline 并写 workflow review，用 targeted 1-node benchmark 验证 root cause，再在同 clean commit 重跑 1→2-node 后只允许一次新 terminal retry。

## 13. 阶段完成报告模板

报告 epoch/owner/session sequence、control vs optimizer transition counts、leader changes、head commits、kill points、clock-skew envelope、TTL/renew margin、strict replay 与 memoized replay、takeover RTO（observed，不预设）、double/split count、cache invalidation、stop replay 和分阶段 critical path。

## 14. 可直接复制给 Codex 的启动指令

```text
使用 miyabi-development skill 执行 P05。

仓库：https://github.com/UnbearableFate/fs_based_decoupled_diloco
规划基线：M00 corrected archival tip 89ae48aae5956b09fc6685074d3ea0eaea36b816（verified runtime c052438a3cfe5e16c3b154fc842f32dcd61ec6ff）
目标分支：codex/duraloco-p05-syncer-failover
阶段计划：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/07_P05_SYNCER_LEASE_FENCING_AND_FAILOVER.md
共同契约：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/00_CODEX_LOOP_OPERATING_CONTRACT.md
系统设计：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/SQLITE_FREE_SYSTEM_DESIGN.md
M00 经验：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/M00_IMPLEMENTATION_LESSONS.md

先执行 hostname、git status --short --branch、git rev-parse HEAD，并读取 AGENTS.md、共同契约、当前阶段文件、上一阶段报告和相关研究草稿。若基线漂移，先写 drift report；不要 reset 用户改动。

按阶段文件中的 Loop 顺序工作。每个 Loop 都要先建立失败测试或可执行规范，再做最小实现，随后运行分层验证和独立 checker。持续更新 plans/duraloco/STATE.yaml；不要自动合并 main；不要在 Miyabi 登录节点运行 pytest、torch/transformers/datasets 导入、训练、mpirun 或其他 runtime 工作。

结束时在全部必需 gate 有证据且 Checker 通过时标记 completed，并按依赖图自动启动下一个可执行 goal/phase，不等待用户审核；否则输出 BLOCKED，并给出最小复现、已尝试方案和下一项决策。
```

## 15. 参考输入

- `references/DuraLoCo_research_draft_zh.md`
- 现有实现：M00 corrected archival tip `89ae48aae5956b09fc6685074d3ea0eaea36b816`
- Miyabi skill：`https://github.com/UnbearableFate/miyabi-development`
