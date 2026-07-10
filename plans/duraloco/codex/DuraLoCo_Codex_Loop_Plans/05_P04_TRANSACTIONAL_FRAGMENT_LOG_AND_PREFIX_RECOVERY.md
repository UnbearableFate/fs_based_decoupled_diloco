---
plan_id: "P04"
title: "Transactional Fragment Log 与 Prefix Recovery"
status: "planned"
date: "2026-07-10"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/fs-diloco-miyabi"
planning_basis_commit: "011e180980e90c500bcd479a594ba47e507bb5d1"
target_branch: "codex/duraloco-p04-transaction-log"
depends_on:
  - "P03"
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
human_approval_gates:
  - "确认 single global head 作为初版唯一线性化点；改变为多 head/分片事务需另行审批。"
---

# P04 — Transactional Fragment Log 与 Prefix Recovery

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

实现 DuraLoCo 核心：proposal、output fragment、outer optimizer state、commit record、frontier 和 head。所有大对象先不可变写入，唯一 head CAS 共同提交 selected proposals、new fragment 与 outer state。

### 1.1 本阶段支撑的研究主张

已提交 log 是 global optimizer 的唯一权威来源；任意 syncer crash 后可恢复到合法 committed prefix；proposal 在 at-least-once transport 下最多一次 logical inclusion。

### 1.2 完成后的系统增量

在 memory/POSIX backend 上运行完整 transactional commit、replay、inspect 和 cache rebuild；尚未把现有 learner/syncer 默认切到 v2。

## 2. 前置条件

- [ ] P03 CAS contract 在目标 backend 通过；
- [ ] P02 reference state machine 和 optimizer oracle 通过；
- [ ] P01 schemas 已冻结；
- [ ] single global head 决策获批。

## 3. 范围

### 3.1 必须完成

- [ ] 不可变 proposal/commit/frontier/snapshot object layout；
- [ ] global head schema 与 CAS；
- [ ] prepared outputs/outer state；
- [ ] selected proposal consumption set；
- [ ] one-CAS commit algorithm；
- [ ] startup replay、prefix verification、orphan detection；
- [ ] SQLite/materialized index 从 log 重建；
- [ ] inspect/verify/replay CLI；
- [ ] 每个 commit stage crash injection。

### 3.2 明确不做

- 不实现 leader lease；CAS 防止双提交，但不提供高效 single leader；
- 不实现 learner adoption；
- 不实现 compaction/GC；
- 不优化大 tensor I/O。

## 4. 预期仓库变更

```text
fs_diloco/log/
  __init__.py
  layout.py
  head.py
  frontier.py
  proposal_index.py
  consumption_index.py
  commit.py
  replay.py
  verify.py
  cache.py
  inspect_cli.py
fs_diloco/optimizer/
  transition.py
  reference_adapter.py
tests/log/
  test_commit_happy_path.py
  test_commit_crash_matrix.py
  test_cas_conflict.py
  test_replay_prefix.py
  test_cache_rebuild.py
  test_orphans.py
```

## 5. 需要先冻结的设计决策

- [ ] D-0401：head CAS 是唯一 commit point；
- [ ] D-0402：frontier 包含 per-fragment commit/version/object refs 和 global scheduler state；
- [ ] D-0403：outer optimizer state 是 per-fragment immutable object；
- [ ] D-0404：proposal consumption 记录在 commit 还是独立 index；
- [ ] D-0405：commit selection/weights 使用哪些 canonical representations；
- [ ] D-0406：orphan 的定义和最小保留期。

每项决策必须写入 `plans/duraloco/DECISIONS.md`，包含：上下文、候选方案、所选方案、拒绝方案、兼容性影响和可逆性。不得把未决语义隐藏在实现细节中。

## 6. Codex 执行循环

### Loop 1 — Object layout 与 genesis

**目标。** 建立可验证的 run generation、genesis commit/frontier/head。

**先产生的失败证据或规范。**

- [ ] wrong run/generation、missing genesis object、head ref hash mismatch。

**实现任务。**

- [ ] 定义 key layout；
- [ ] 创建 idempotent run initialization；
- [ ] 验证 model/index/layout digests；
- [ ] 禁止复用非空 generation。

**本循环验证。**

- [ ] 重复 init same config 幂等；
- [ ] 不同 config 冲突失败；
- [ ] genesis fold 可恢复。

**本循环持久化输出。**

- [ ] layout/genesis API；
- [ ] run init CLI。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 2 — Prepare transition

**目标。** 从合法 proposals 确定性地产生 output fragment、outer state、commit/frontier objects。

**先产生的失败证据或规范。**

- [ ] proposal input order shuffled；
- [ ] selected duplicate；
- [ ] wrong base；
- [ ] outer state step mismatch。

**实现任务。**

- [ ] 调用 reference-compatible reducer/outer step；
- [ ] canonical selection/weight record；
- [ ] 写 immutable outputs 和 commit/frontier；
- [ ] prepare 不改变 head。

**本循环验证。**

- [ ] 相同 logical input 产生相同 commit ID/digests；
- [ ] prepared orphan 对 reader 不可见为 committed。

**本循环持久化输出。**

- [ ] prepare pipeline；
- [ ] transition artifacts。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 3 — CAS commit 与 exactly-once inclusion

**目标。** 通过单一 head CAS 线性化整个 optimizer transition。

**先产生的失败证据或规范。**

- [ ] 两个 writers 基于同 parent；
- [ ] CAS 成功响应丢失后重试；
- [ ] 同 proposal 在后继 commit 再次出现。

**实现任务。**

- [ ] 实现 commit_head；
- [ ] CAS conflict 后重读/revalidate；
- [ ] 消费集合检查；
- [ ] response-loss idempotency。

**本循环验证。**

- [ ] competing writer 只有一个 commit；
- [ ] 成功响应丢失后能识别已提交；
- [ ] double inclusion 被拒。

**本循环持久化输出。**

- [ ] transactional commit API；
- [ ] CAS/conflict logs。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 4 — Replay、verify 与 cache rebuild

**目标。** 只凭 durable log 恢复 global optimizer state 和派生索引。

**先产生的失败证据或规范。**

- [ ] 删除 SQLite/cache；
- [ ] 截断到每个 prefix；
- [ ] 注入 dangling/orphan/bad ref。

**实现任务。**

- [ ] fold commit chain；
- [ ] 校验 parent、seq、hash、frontier；
- [ ] 重建 proposal consumption/cache；
- [ ] inspect 与 verify CLI。

**本循环验证。**

- [ ] 每个 prefix digest 与 reference model 相同；
- [ ] cache 删除后结果不变；
- [ ] orphan 不进入 committed view。

**本循环持久化输出。**

- [ ] replay/verify CLI；
- [ ] cache rebuild；
- [ ] crash matrix report。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

## 7. 不变量与失败注入

### 7.1 本阶段必须维护的不变量

- [ ] head 是唯一可变权威指针；
- [ ] commit_seq 单调且 parent 链连续；
- [ ] head 可达的所有 refs 存在并校验；
- [ ] proposal 最多一次出现在 committed selected set；
- [ ] fragment 与 outer state 由同一 commit/frontier 原子引用；
- [ ] 删除所有缓存后可恢复相同 state digest；
- [ ] prepared/orphan objects 不影响 committed state。

### 7.2 必须覆盖的故障与反例

- [ ] crash before/after each immutable put；
- [ ] crash before/after head CAS；
- [ ] CAS success response lost；
- [ ] two writers same parent；
- [ ] missing/corrupt referenced object；
- [ ] cache loss/corruption；
- [ ] orphan proliferation；
- [ ] replay every prefix。

## 8. 验收标准

以下条件是阶段 gate，不是建议。Maker 必须给出命令、退出码和 artifact 路径；Checker 必须逐项复核。

- [ ] P04-A01：head CAS 是代码中唯一 committed transition 线性化点；
- [ ] P04-A02：所有 crash points 恢复为旧或新合法 prefix；
- [ ] P04-A03：CAS response loss 不造成 double commit；
- [ ] P04-A04：proposal double logical inclusion 为零；
- [ ] P04-A05：fragment/outer state pairing 不可部分可见；
- [ ] P04-A06：SQLite/cache 删除后可完全重建；
- [ ] P04-A07：memory 与 POSIX 产生相同 committed state digest；
- [ ] P04-A08：inspect/verify CLI 能定位首个损坏 commit；
- [ ] P04-A09：Checker 审核 one-CAS proof path。

## 9. 验证矩阵

| 层级 | 要求 |
|---|---|
| 本地 reference/unit | 必须：完整 crash matrix、two-writer threads/processes。 |
| Miyabi 1-node | 必须：Lustre commit/replay 与 cache rebuild。 |
| Miyabi 2-node | 必须：two-writer same-parent CAS、response-loss/takeover simulation。 |
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

## 11. 人工审批门

- [ ] 确认 single global head 作为初版唯一线性化点；改变为多 head/分片事务需另行审批。

## 12. 阻塞与停止规则

- 同一根因连续三次修复后仍未通过同一 gate：写入 `BLOCKERS.md` 并停止扩大改动。
- 需要改变 research contract、failure model、协议线性化点或数值语义：停止并请求人工决策。
- 需要在 Miyabi 登录节点运行被禁止的 runtime 命令：停止，转为 PBS allocation。
- 需要提交 9 节点、长时间或付费公共云作业：停止并取得明确批准。
- 发现基础分支包含未合并的用户改动或基线漂移：保留改动，生成 drift report，不得覆盖。

## 13. 阶段完成报告模板

报告 crash point 数、prefix digests、double inclusion count、CAS conflict/retry、orphan 数、cache rebuild 证据和线性化点审查。

## 14. 可直接复制给 Codex 的启动指令

```text
使用 miyabi-development skill 执行 P04。

仓库：https://github.com/UnbearableFate/fs_based_decoupled_diloco
规划基线：codex/fs-diloco-miyabi @ 011e180980e90c500bcd479a594ba47e507bb5d1
目标分支：codex/duraloco-p04-transaction-log
阶段计划：plans/duraloco/codex/05_P04_TRANSACTIONAL_FRAGMENT_LOG_AND_PREFIX_RECOVERY.md
共同契约：plans/duraloco/codex/00_CODEX_LOOP_OPERATING_CONTRACT.md

先执行 hostname、git status --short --branch、git rev-parse HEAD，并读取 AGENTS.md、共同契约、当前阶段文件、上一阶段报告和相关研究草稿。若基线漂移，先写 drift report；不要 reset 用户改动。

按阶段文件中的 Loop 顺序工作。每个 Loop 都要先建立失败测试或可执行规范，再做最小实现，随后运行分层验证和独立 checker。持续更新 plans/duraloco/STATE.yaml；不要自动合并 main；不要在 Miyabi 登录节点运行 pytest、torch/transformers/datasets 导入、训练、mpirun 或其他 runtime 工作。

结束时只在全部 gate 有证据时标记 ready_to_merge；否则输出 BLOCKED，并给出最小复现、已尝试方案和下一项决策。
```

## 15. 参考输入

- `references/DuraLoCo_research_draft_zh.md`
- 现有实现：`https://github.com/UnbearableFate/fs_based_decoupled_diloco/tree/codex/fs-diloco-miyabi`
- Miyabi skill：`https://github.com/UnbearableFate/miyabi-development`
