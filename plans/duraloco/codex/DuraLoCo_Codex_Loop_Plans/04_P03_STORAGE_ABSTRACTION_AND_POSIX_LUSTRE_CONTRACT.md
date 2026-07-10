---
plan_id: "P03"
title: "语义化 Storage API 与 POSIX/Lustre Contract"
status: "planned"
date: "2026-07-10"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/fs-diloco-miyabi"
planning_basis_commit: "afc50a1e179c64321645b278b2497ea3ab3fe24d"
target_branch: "codex/duraloco-p03-posix-storage"
depends_on:
  - "P02"
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
agent_decision_gates:
  - "若 Lustre 实测无法支持计划中的 CAS/locking 语义，agent 基于 contract evidence 选择最小替代设计，记录 ADR，经独立 Checker 复核。"
human_approval_gates: []
---

# P03 — 语义化 Storage API 与 POSIX/Lustre Contract

> **历史计划声明（2026-07-11）：** 本阶段已按旧系统完成，文中 SQLite/DB 相关内容只记录当时基线与证据。活跃路线由 M00 的 SQLite-free 设计取代；不得从本文恢复、保留或新建 SQLite 依赖。

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

把当前对 `Path`、glob、rename 的直接依赖替换为语义化 storage contract，并在本地 POSIX 与 Miyabi Lustre 上验证 immutable write、conditional replace、durability、visibility 与并发行为。

### 1.1 本阶段支撑的研究主张

DuraLoCo 的 correctness 依赖一小组明确 storage primitives，而不是依赖“共享目录通常能工作”。本阶段刻画 POSIX/Lustre 能提供和不能提供的语义边界。

### 1.2 完成后的系统增量

新增 backend-neutral API、POSIX implementation、capability probe、fault-injection wrapper 和跨进程 contract suite；尚不迁移 production commit path。

## 2. 前置条件

- [ ] Reference backend contract 通过；
- [ ] 确认 Miyabi 可使用的共享 run root；
- [ ] 所有 contract tests 使用隔离 prefix；
- [ ] 明确 parent fsync 与 Lustre durability 仅在所声明 failure model 内解释。

## 3. 范围

### 3.1 必须完成

- [ ] `put_immutable`、`put_if_absent`、`conditional_replace`、`get`、`head`、`range_get`、`delete_batch`；
- [ ] ObjectRef/version token/error taxonomy；
- [ ] POSIX temp write、file fsync、rename/link/O_EXCL、parent directory fsync；
- [ ] CAS/lock 实现与 stale lock 恢复；
- [ ] listing 只作 discovery/GC；
- [ ] fault injection：before-effect/after-effect timeout、short read、corruption、EIO；
- [ ] capability probe 与报告；
- [ ] 本地多进程和 Miyabi 2-node Lustre contract tests。

### 3.2 明确不做

- 不接入 syncer commit；
- 不实现 S3；
- 不声称 fsync 等于所有节点/存储故障下的物理持久性；
- 不在共享非测试 prefix 执行 delete。

## 4. 预期仓库变更

```text
fs_diloco/storage/
  __init__.py
  base.py
  errors.py
  object_ref.py
  posix.py
  fault_injection.py
  capability_probe.py
  layout.py
tests/storage/
  contract.py
  test_memory_contract.py
  test_posix_contract.py
  test_posix_multiprocess.py
  test_fault_injection.py
scripts/miyabi/
  run_storage_contract_1node.pbs
  run_storage_contract_2node.pbs
```

保留 `atomic_io.py` 作为 legacy adapter；新代码不得继续扩散直接 Path 操作。

## 5. 需要先冻结的设计决策

- [ ] D-0301：POSIX conditional replace 的版本 token 与锁策略；
- [ ] D-0302：目录 fsync 不支持时的 capability downgrade；
- [ ] D-0303：读后校验频率与 always-verify correctness mode；
- [ ] D-0304：namespace/object layout 与 key normalization；
- [ ] D-0305：对 EIO/ESTALE/ENOENT visibility race 的重试分类。

每项决策必须写入 `plans/duraloco/DECISIONS.md`，包含：上下文、候选方案、所选方案、拒绝方案、兼容性影响和可逆性。不得把未决语义隐藏在实现细节中。

## 6. Codex 执行循环

### Loop 1 — Backend interface 与 conformance suite

**目标。** 先以 memory backend 固定所有操作的可观察语义。

**先产生的失败证据或规范。**

- [ ] 定义 duplicate immutable put、stale CAS、after-effect timeout、delete missing 等 contract cases。

**实现任务。**

- [ ] 实现 Protocol/ABC；
- [ ] 定义 typed results/errors；
- [ ] 编写可对任意 backend 重用的 contract suite。

**本循环验证。**

- [ ] memory backend 全部 conformance tests；
- [ ] 调用方不需要检查 backend 类型。

**本循环持久化输出。**

- [ ] storage base API；
- [ ] contract test harness。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 2 — POSIX durable object operations

**目标。** 实现 immutable object 与可校验读取。

**先产生的失败证据或规范。**

- [ ] 并发 put same/different bytes；
- [ ] kill between write/fsync/rename/dir-fsync；
- [ ] short/corrupt read。

**实现任务。**

- [ ] 同目录 temp；
- [ ] file fsync；
- [ ] atomic publish；
- [ ] parent fsync capability；
- [ ] checksum/size verification；
- [ ] safe key-to-path mapping。

**本循环验证。**

- [ ] 多进程 tests；
- [ ] path traversal 被拒；
- [ ] after-effect timeout 可幂等重试。

**本循环持久化输出。**

- [ ] PosixBackend；
- [ ] durability notes。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 3 — Conditional head operation

**目标。** 在声明的 failure model 下提供单 key compare-and-swap。

**先产生的失败证据或规范。**

- [ ] 两个进程/节点用同 expected version 并发 replace；必须只有一个成功。

**实现任务。**

- [ ] 实现 lock/fencing token；
- [ ] 处理 stale lock；
- [ ] 返回新 version；
- [ ] 不依赖 mtime 作为唯一版本。

**本循环验证。**

- [ ] 本地多进程 race；
- [ ] Miyabi 2-node race；
- [ ] 100+ rounds 无双成功。

**本循环持久化输出。**

- [ ] conditional replace；
- [ ] CAS evidence。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

### Loop 4 — Capability probe 与 fault wrapper

**目标。** 使 runtime 在 backend 不满足要求时 fail closed。

**先产生的失败证据或规范。**

- [ ] 模拟不支持 dir fsync、非原子 rename、list 延迟、EIO。

**实现任务。**

- [ ] 实现 probe CLI；
- [ ] 生成 JSON capability report；
- [ ] 实现 deterministic fault schedule wrapper；
- [ ] 配置 required capabilities。

**本循环验证。**

- [ ] 不满足 required capability 时 startup 非零退出；
- [ ] fault schedule 可 replay。

**本循环持久化输出。**

- [ ] probe report；
- [ ] fault wrapper；
- [ ] Miyabi run scripts。

**停止条件。** 上述验证全部通过，且未引入未记录的行为变化。

## 7. 不变量与失败注入

### 7.1 本阶段必须维护的不变量

- [ ] commit correctness 不依赖 listing；
- [ ] immutable key 不可被不同 bytes 覆盖；
- [ ] 同 expected version 的 competing CAS 最多一个成功；
- [ ] 任何读取返回内容都经过 size/hash 验证或显式标记未验证；
- [ ] backend capability 不足时 fail closed；
- [ ] 测试删除只作用于 run-isolated prefix。

### 7.2 必须覆盖的故障与反例

- [ ] process kill at every publication step；
- [ ] two-process/two-node CAS race；
- [ ] stale lock；
- [ ] after-effect timeout；
- [ ] short read/corruption；
- [ ] delayed list visibility；
- [ ] EIO/ESTALE/permission/full quota；
- [ ] path traversal。

## 8. 验收标准

以下条件是阶段 gate，不是建议。Maker 必须给出命令、退出码和 artifact 路径；Checker 必须逐项复核。

- [ ] P03-A01：memory 与 POSIX 通过同一 conformance suite；
- [ ] P03-A02：immutable key 冲突被检测；
- [ ] P03-A03：本地和 Miyabi 2-node CAS race 每轮最多一个 winner；
- [ ] P03-A04：listing omission 不影响 head read/commit；
- [ ] P03-A05：parent fsync/capability 结果被记录，不做超出证据的 durability claim；
- [ ] P03-A06：fault wrapper 可按 seed/replay schedule 复现；
- [ ] P03-A07：legacy runtime 未被默认切换；
- [ ] P03-A08：Checker 审查 lock/CAS failure window。

## 9. 验证矩阵

| 层级 | 要求 |
|---|---|
| 本地 unit | 必须：memory/posix contract、multiprocess race、fault wrapper。 |
| Miyabi login | 必须：脚本 `bash -n`、路径/config review；不得运行 contract pytest。 |
| Miyabi 1-node | 必须：真实 Lustre prefix 的 immutable/read/durability probe。 |
| Miyabi 2-node | 必须：CAS race、visibility 和 stale-lock takeover；最大 10 分钟。 |
| 9-node | 不要求。 |

每个 Lustre run 记录 filesystem path、mount/stripe 可观察信息、两个 hostname、PBS job ID 和 operation trace。

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

- [ ] 若 Lustre 无法支持原 CAS/locking 语义，agent 在 single-writer namespace、external lock service 或 head sharding 中选择有证据的最小可逆替代方案，写入 ADR，经 Checker 复核后继续。
- [ ] P03 必需 gate 通过后自动进入 P04，无需人工审核。

## 12. 阻塞与停止规则

- 同一根因连续三次修复后仍未通过同一 gate：写入 `BLOCKERS.md` 并停止扩大改动。
- 若实现当前目标需要调整 research contract、failure model、协议线性化点或数值语义：agent 记录 ADR、contract evidence 和兼容性影响，经 Checker 复核后继续；只有 materially 超出用户授权研究目标时才停止请求决策。
- 需要在 Miyabi 登录节点运行被禁止的 runtime 命令：停止，转为 PBS allocation。
- 单个 Miyabi 作业可由 agent 自主决定并提交（`select<=16`、`walltime<=02:00:00`，包括 9 节点）；超出该范围或需要付费公共云资源时停止并取得明确批准。
- 发现基础分支包含未合并的用户改动或基线漂移：保留改动，生成 drift report，不得覆盖。

## 13. 阶段完成报告模板

报告每项 storage capability、支持/降级状态、2-node CAS winner 统计、故障窗口、未覆盖的 physical failure assumptions。

## 14. 可直接复制给 Codex 的启动指令

```text
使用 miyabi-development skill 执行 P03。

仓库：https://github.com/UnbearableFate/fs_based_decoupled_diloco
规划基线：codex/fs-diloco-miyabi @ afc50a1e179c64321645b278b2497ea3ab3fe24d
目标分支：codex/duraloco-p03-posix-storage
阶段计划：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/04_P03_STORAGE_ABSTRACTION_AND_POSIX_LUSTRE_CONTRACT.md
共同契约：plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/00_CODEX_LOOP_OPERATING_CONTRACT.md

先执行 hostname、git status --short --branch、git rev-parse HEAD，并读取 AGENTS.md、共同契约、当前阶段文件、上一阶段报告和相关研究草稿。若基线漂移，先写 drift report；不要 reset 用户改动。

按阶段文件中的 Loop 顺序工作。每个 Loop 都要先建立失败测试或可执行规范，再做最小实现，随后运行分层验证和独立 checker。持续更新 plans/duraloco/STATE.yaml；不要自动合并 main；不要在 Miyabi 登录节点运行 pytest、torch/transformers/datasets 导入、训练、mpirun 或其他 runtime 工作。

结束时在全部必需 gate 有证据且 Checker 通过时标记 completed，并按依赖图自动启动下一个可执行 goal/phase，不等待用户审核；否则输出 BLOCKED，并给出最小复现、已尝试方案和下一项决策。
```

## 15. 参考输入

- `references/DuraLoCo_research_draft_zh.md`
- 现有实现：`https://github.com/UnbearableFate/fs_based_decoupled_diloco/tree/codex/fs-diloco-miyabi`
- Miyabi skill：`https://github.com/UnbearableFate/miyabi-development`
