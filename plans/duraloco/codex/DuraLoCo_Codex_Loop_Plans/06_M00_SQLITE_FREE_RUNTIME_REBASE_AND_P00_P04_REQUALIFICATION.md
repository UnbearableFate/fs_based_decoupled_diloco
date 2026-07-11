---
plan_id: "M00"
title: "无 SQLite 运行时重构与 P00–P04 再验收"
status: "completed"
date: "2026-07-11"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/duraloco-p04-transaction-log"
planning_basis_commit: "a655413cea6ebe9bc368b5827318efd766683b5a"
target_branch: "codex/duraloco-m00-sqlite-free-rebase"
depends_on:
  - "P04"
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
agent_decision_gates:
  - "无数据库 RuntimeView、production tensor ObjectRef codec 和 warm-start generation 格式由 agent 依据 P00–P04 contracts 冻结并经独立 Checker 复核。"
human_approval_gates: []
verified_implementation: "c052438a3cfe5e16c3b154fc842f32dcd61ec6ff"
corrected_archival_tip: "89ae48aae5956b09fc6685074d3ea0eaea36b816"
checker_verdict: "PASS; required_gate_followups: none"
---

# M00 — 无 SQLite 运行时重构与 P00–P04 再验收

> **完成声明（2026-07-11）：** M00-A01–A12、全部 41 个 P00–P04 重映射 gate、1/2/9-node ladder 和独立 Checker 均已通过。执行证据以 `plans/duraloco/phases/M00_PHASE_REPORT.md` 和 `M00_IMPLEMENTATION_LESSONS.md` 为准；本文保留为已完成 milestone 的原始执行契约，当前路线从 P05 开始。

> M00 是 P00–P04 之后的新路线第 0 milestone，已取代原计划
> “P05 内把 SQLite 降级为 cache”的方案并完成。P05 现已获得启动授权。

执行前必须同时读取：

1. 仓库根目录 `AGENTS.md`；
2. `00_CODEX_LOOP_OPERATING_CONTRACT.md`；
3. `SQLITE_FREE_SYSTEM_DESIGN.md`；
4. `P00_P04_IMPLEMENTATION_LESSONS.md`；
5. `miyabi-development` skill 的 `SKILL.md`；
6. `plans/duraloco/STATE.yaml`、`DECISIONS.md`、`BLOCKERS.md`；
7. P00–P04 的 phase reports/states、P04 drift report 和所有最终/失败 Checker 记录；
8. P00–P04 阶段计划与 research draft 相关章节。

## 1. 阶段使命

在当前 P04 实现上构建一个完整无 SQLite/无本地数据库的生产运行时，
将 full-vector 与 fragment syncer 的 discovery、selection、merge、outer step、publish、
resume 和 analysis 迁移到“committed log + 进程内 RuntimeView + append-only telemetry”
模型，然后在最终干净 commit 上重新通过 P00–P04 的全部审核等级。

### 1.1 必须实现的结果

- 源码、运行配置、scripts、tests 和当前 evidence tooling 中不存在 SQLite
  import、schema、DB dump、CLI 或 config dependency；
- production syncer 只从 committed log 恢复权威状态；
- pending/eligible/selected 仅存在进程内，applied/dropped 由 committed decisions 推导；
- 当前 full-vector 与 fragment 两种运行路径都通过同一 head-CAS transaction；
- 恢复、takeover 演练、analysis 和 evidence checker 不需要任何 DB；
- 旧 DB-backed run 不就地恢复；只允许显式 checkpoint warm-start 新 generation。

### 1.2 明确不做

- 不保留 SQLite 只读兼容层、converter 或可选 extra；
- 不引入 LMDB、DuckDB、LevelDB、Redis 或另一个持久化数据库替代；
- 不将 JSONL、CSV、heartbeats、`latest.json` 或内存 RuntimeView 提升为权威；
- 不在 M00 实现 lease/fencing、learner v2 adoption、GC 或 SACC；
- 不修改 P00–P04 历史 artifacts 来伪造无 SQLite 证据。

## 2. 前置条件与基线

- [ ] 基于已完成 P04 verified implementation `a655413...`，不回退到 planning basis；
- [ ] 保留 P00–P04 reports/artifacts 为历史审计证据；
- [ ] 生成 M00 drift report，列出当前实际 branch/commit 和未提交用户改动；
- [ ] 冻结无 SQLite 设计 ADR 和 P00–P04 acceptance 重映射；
- [ ] 未提交用户工作不被 reset、覆盖或混入证据 commit。

## 3. 预期代码重构

```text
fs_diloco/
  runtime_view.py              # replay-derived immutable process view
  proposal_catalog.py          # listing-as-discovery + P01 validation
  syncer.py                    # one sqlite-free dispatcher/runtime
  analysis.py                  # committed-log + JSONL/manifests fold
  log/
    replay.py
    commit.py
    production_codec.py        # safetensors/ObjectRef bridge
    bootstrap.py               # new-generation warm start, no DB reader
    inspect_cli.py              # verify/replay/orphans, no rebuild-cache

removed:
  fs_diloco/sqlite_store.py
  fs_diloco/schema.sql
  fs_diloco/log/cache.py
  scripts/miyabi/dump_sqlite.sh
```

同时删除配置、paths、retention、analysis、PBS/local scripts、evidence validators 和 tests
中的 DB dump/SQLite 表面。

## 4. 需要先冻结的决策

- [ ] D-M0001：RuntimeView 字段、不变性和 CAS 后替换时机；
- [ ] D-M0002：production full/fragment tensor ObjectRef codec 与实现 digest；
- [ ] D-M0003：proposal discovery 重扫、重复、漏项和 quarantine 语义；
- [ ] D-M0004：JSONL/CSV telemetry schema 与 analysis deterministic fold；
- [ ] D-M0005：旧 checkpoint 到新 generation 的 warm-start 语义和显式 non-claim；
- [ ] D-M0006：旧 SQLite config/CLI 字段的 fail-closed 错误和删除时点。

## 5. Codex 执行循环

### Loop 1 — 规范、静态禁止项与接口重构

**先产生的失败证据。**

- [ ] 静态 checker 在 active source/config/script/test 中发现 `sqlite3`、`sqlite_store`、
  `schema.sql`、`db_dump`、`resume_db_dump`、`sqlite_local_dir` 或旧 CLI 时失败；
- [ ] 旧 config/CLI keys 被传入时 fail closed，不静默忽略；
- [ ] 删除本地 runtime 目录后，旧 syncer 恢复测试必须先失败。

**实现任务。**

- [ ] 建立 `RuntimeView`、proposal catalog 和接口协议；
- [ ] 将 liveness、selection、analysis 从 `SQLiteStore` 类型解耦；
- [ ] 删除 SQLite source/schema/config/path/retention/CLI/evidence code；
- [ ] 替换 SQLite tests 为 runtime-view/replay/catalog/telemetry tests；
- [ ] 更新 README、design、user guide、runbook 和配置示例。

**本循环 gate。**

- [ ] active runtime 静态 forbidden-surface checker 通过；
- [ ] package import/CLI/config static checks 通过；
- [ ] 无 DB 时 unit fixtures 可构造 full/fragment runtime state。

### Loop 2 — 无数据库 discovery、selection 与 RuntimeView

**先产生的失败证据。**

- [ ] listing duplicate/omission/reorder；scanner restart；malformed/future/stale proposal flood；
- [ ] 同 lineage rollback；newer ID 排在 older proposal 之前；CAS conflict 后旧 selection 重用；
- [ ] 进程内 view 丢失后重启。

**实现任务。**

- [ ] replay 构建 RuntimeView；
- [ ] 全量可重入 scanner + P01 validator/quarantine；
- [ ] 复用 P02 selection kernel，禁止独立 runtime policy；
- [ ] CAS conflict 后 replay/revalidate/reselect；
- [ ] commit 成功后才生成新 RuntimeView。

**本循环 gate。**

- [ ] restart 前后 eligible/consumed/drop/lineage digest 一致；
- [ ] 无 durable selected，每个 proposal 最多一次 logical inclusion；
- [ ] listing 行为不改变 committed state。

### Loop 3 — Production tensor transition 与无 DB resume

**先产生的失败证据。**

- [ ] full/fragment params 与 outer-state 部分发布；
- [ ] crash before/after every immutable object 与 head CAS；
- [ ] CAS 成功响应丢失后 successor 继续推进；
- [ ] 删除所有本地状态和 compatibility exports 后重启；
- [ ] warm-start 试图伪装 exact continuation。

**实现任务。**

- [ ] 将现有 safetensors/outer-state 发布绑定到 P04 commit/frontier ObjectRefs；
- [ ] `latest.json` 改为 committed frontier 的导出物；
- [ ] full-vector 与 fragment syncer 都通过同一 transaction API；
- [ ] 实现 log-only resume 和 `bootstrap-new-generation`；
- [ ] response-loss 以 request identity + ancestry 解析；
- [ ] metrics/analysis 改为 committed log + JSONL/manifests fold。

**本循环 gate。**

- [ ] 从空本地目录恢复后 params/outer-state/consumption/scheduler digest 相同；
- [ ] memory/POSIX 与 production full/fragment path 在 numeric contract 内一致；
- [ ] 旧 DB-backed run 只能显式 warm-start 新 generation。

### Loop 4 — P00–P04 完整再验收

**本地/静态。**

- [ ] P00 contract/state/evidence/checksum/PBS static suite；
- [ ] P01 strict schemas/validation/quarantine/goldens 和独立反例；
- [ ] P02 reference/crash/model-check/mutants/numeric oracle，包括显式 10,000 traces；
- [ ] P03 memory/POSIX conformance、fault schedule、error taxonomy 与 capability checker；
- [ ] P04 transaction/crash/CAS/replay/orphan/inspect 套件，将 cache gate 改为“空本地目录恢复”。

**Miyabi 阶梯。**

- [ ] login node 只运行 `bash -n`、checksum、static checker；
- [ ] 1-node：全量 dependency-complete tests + real Lustre log-only recovery + full/fragment tiny path；
- [ ] 2-node：100 轮 backend race + 20 轮 transaction same-parent race + 无 DB process takeover；
- [ ] 9-node terminal：真实 GPT-2/WikiText-2，1 syncer + 8 learners，`inner_steps=50`，
  恰好 10 outer transitions，15 分钟硬 walltime，full SQLite-free runtime 断言；
- [ ] 最终独立 Checker 在最终干净 commit 上重跑当前套件、P00–P04 历史反例
  和至少一个新反例。

## 6. 原 P00–P04 审核标准重映射

| 原阶段 | M00 必须重新证明的内容 | 有意的语义变更 |
|---|---|---|
| P00 | contracts、invariants、state/evidence validators、clean manifests、full/fragment real baseline | P00-A06 的 legacy compatibility 改为 SQLite-free CLI/config 兼容；旧 DB keys 必须显式拒绝 |
| P01 | A01–A08 全部 schema/canonical/validation/quarantine/v1-read-only 反例 | v1 adapter 不得读取或输出 DB 状态 |
| P02 | A01–A08 reference、crash prefix、double inclusion、mutants、numeric oracle、deterministic replay | 无 |
| P03 | A01–A08 memory/POSIX contract、single winner、listing independence、capability、fault/error matrix | 无 |
| P04 | A01–A05/A07–A09 one-CAS、crash、response loss、pairing、backend equality、inspect/checker | P04-A06 改为删除所有本地派生状态后从 committed log 精确恢复，不再构建 DB cache |

原始 reports 和 artifacts 保留原结果。M00 不得把过去含 SQLite 的 PASS 直接当作
新结构的证据；所有重映射 gate 必须产生新 run IDs 和新 Checker report。

## 7. M00 验收标准

- [ ] M00-A01：active source/config/scripts/tests/evidence tooling 中无 SQLite/DB-dump dependency，静态 forbidden-surface checker fail closed；
- [ ] M00-A02：唯一 committed transition 路径是 P04 head CAS，`latest.json`/telemetry/heartbeats 都为导出或观测；
- [ ] M00-A03：RuntimeView 可从 full replay 确定性构建，丢失进程/本地目录后 digest 不变；
- [ ] M00-A04：full/fragment syncer 都无 durable selected/pending/applied state，proposal double inclusion 为零；
- [ ] M00-A05：production safetensors params/outer state 成对进入 commit/frontier，部分发布不可见为 committed；
- [ ] M00-A06：无 DB resume、successor 后 response-loss 和新 generation warm-start 的语义与证据完整；
- [ ] M00-A07：analysis/evidence checker 只 fold committed log + JSONL/manifests，缺失/损坏导出不影响权威；
- [ ] M00-A08：P00–P04 所有可适用 acceptance IDs 在最终干净 commit 上产生新 PASS 证据，两个显式重映射项经 Checker 批准；
- [ ] M00-A09：Miyabi 1-node full suite/log-only recovery/full+fragment tiny real path 通过；
- [ ] M00-A10：Miyabi 2-node races/takeover 无 split-brain、double winner、double inclusion 或本地持久化依赖；
- [ ] M00-A11：9-node GPT-2/WikiText-2 50×10 terminal gate 在无 SQLite 代码/配置/artifact 条件下通过；
- [ ] M00-A12：独立 Checker 验证删除面、单权威 proof、P00–P04 mapping、历史失败回归和 attempt lineage，`required_gate_followups: none`。

## 8. 证据与 Maker–Checker 交接

Maker 必须提交：

- M00 feature branch 和最终干净 verified commit；
- SQLite surface 删除 inventory 与 forbidden checker output；
- P00–P04 acceptance mapping JSON/Markdown；
- 1/2/9-node manifests、PBS job IDs、hosts、config digests、qstat 和 parent lineage；
- crash/response-loss/restart/takeover 最小 traces；
- 双语 `plans/duraloco/phases/M00_PHASE_REPORT.md` 和 `M00_STATE.yaml`；
- 已知 non-claims、warm-start 限制和后续 P05 输入。

Checker 必须独立：

- 从最终 commit 反向审计所有 SQLite/import/config/path/script/artifact 表面；
- 删除本地目录并在新进程中恢复；
- 重跑 P02 oldest-first divergence、P03 identical-payload distinct-request CAS、P04 delayed
  response-loss ancestry 和 corrupt-local-state 等历史反例；
- 增加至少一个“工作目录无任何 DB 但有 listing omission + process kill”新反例；
- 审核 M00-A01–A12 和所有重映射 P00–P04 gates。

## 9. 自动推进与停止规则

- M00 全部 gate 通过、独立 Checker `PASS`、双语报告/状态持久化并完成
  archival commit 后，自动进入 P05；
- 任何 SQLite 代码/配置/运行 artifact 在 active path 中仍被要求，M00 必须阻塞；
- 任何绕过 committed log 的本地持久化权威或 durable selected 必须阻塞；
- 同一根因连续三次修复仍未通过同一 gate，按共同契约记录 blocker；
- 不得在 Miyabi login node 运行 runtime；先 1-node，再 2-node，最后 9-node。

## 10. 可直接复制给 Codex 的启动指令

```text
使用 miyabi-development skill 执行 M00 SQLite-free runtime rebase。

基线：已完成 P04 verified implementation a655413cea6ebe9bc368b5827318efd766683b5a
目标分支：codex/duraloco-m00-sqlite-free-rebase
阶段计划：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/06_M00_SQLITE_FREE_RUNTIME_REBASE_AND_P00_P04_REQUALIFICATION.md
系统设计：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/SQLITE_FREE_SYSTEM_DESIGN.md
共同契约：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/00_CODEX_LOOP_OPERATING_CONTRACT.md

先读取 AGENTS.md、共同契约、无 SQLite 设计、P00–P04 经验、当前 STATE/DECISIONS/BLOCKERS、
P00–P04 reports/states/checker artifacts 和 M00 计划。保留用户改动，不 reset，不 merge main。

按 ORIENT -> SPECIFY/RED -> IMPLEMENT/GREEN -> HARDEN -> CHECK -> PERSIST 执行。删除所有 SQLite/本地数据库运行表面，不建兼容 reader 或替代数据库。在最终干净 commit 上按顺序完成静态、1-node、2-node、9-node 验证和独立 Checker。只有 M00-A01–A12 以及重映射 P00–P04 gates 均有新证据且 Checker 无 required-gate follow-up 时才标记 completed 并进入 P05。
```
