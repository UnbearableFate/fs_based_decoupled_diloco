---
title: "DuraLoCo Codex Loop Operating Contract"
version: "1.3"
date: "2026-07-10"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis: "codex/fs-diloco-miyabi @ afc50a1e179c64321645b278b2497ea3ab3fe24d"
---

# DuraLoCo Codex Loop Operating Contract

本文件定义所有阶段共享的执行协议。阶段文件描述“做什么”，本文件描述 Codex “怎样持续、可审计地做”。任何阶段计划与本文件冲突时，优先采用更安全、更可验证、权限更小的规则，并在 `DECISIONS.md` 记录冲突。

## 1. 总目标

将当前 filesystem-backed Decoupled DiLoCo prototype 演进为 DuraLoCo：一个以 durable fragment commit log 为全局优化器权威状态的 event-sourced storage-native optimizer。实现过程必须同时优化以下目标：

1. **Correctness first**：先建立不变量、参考模型和故障验证，再接入昂贵训练。
2. **Small reversible increments**：每个阶段、每个循环都产生可独立验证和回退的增量。
3. **Persistent state**：进度、决策、阻塞、运行证据和研究结论写入仓库或 artifact，不依赖会话记忆。
4. **Maker–checker separation**：实现者和检查者使用不同上下文；Checker 不接受“测试通过”作为唯一证据。
5. **Environment-aware execution**：本地、Miyabi 登录节点、PBS compute node 的权限和验证职责严格分离。
6. **Research integrity**：计划值、目标值和实测值严格区分；任何论文 claim 都必须追溯到不可变 run manifest。

## 2. Agent Loop

每个工作单元采用以下六拍循环：

```text
ORIENT → SPECIFY/RED → IMPLEMENT/GREEN → HARDEN → CHECK → PERSIST
   ↑                                                       │
   └──────────────── next smallest failing gap ─────────────┘
```

### 2.1 ORIENT

Codex 必须先执行并记录：

```bash
hostname
git status --short --branch
git rev-parse HEAD
git log -5 --oneline
```

然后读取：

- 根目录和当前目录链上的 `AGENTS.md`；
- 当前阶段文件；
- `plans/duraloco/STATE.yaml`；
- 尚未关闭的 `DECISIONS.md`、`BLOCKERS.md`；
- 上一阶段 `PHASE_REPORT.md`；
- 被修改模块及其现有测试；
- 与本阶段有关的 DuraLoCo 草稿章节。

不得在未理解现有兼容路径、数据格式和测试意图前进行大范围重命名或目录搬迁。

### 2.2 SPECIFY/RED

在写生产实现前，先产生至少一种可执行失败证据：

- 单元测试；
- 状态机 trace；
- golden manifest；
- crash failpoint；
- storage contract test；
- benchmark baseline；
- 静态 invariant checker；
- 明确的 CLI/output schema。

测试必须证明它会捕获目标缺陷。对于修复 bug，先在原实现上复现；对于新协议，先用 reference model 固定期望行为。

### 2.3 IMPLEMENT/GREEN

- 只实现让当前最小失败证据通过所需的变更；
- 不借机重写无关模块；
- 保留迁移期兼容路径，除非阶段计划明确删除；
- 新增依赖必须有 ADR、版本约束和无依赖替代方案评估；
- 权威状态只能有一个来源，缓存必须可以从权威状态重建；
- 协议行为必须通过类型、schema 和显式错误表达，不能依靠目录名或隐含排序。

### 2.4 HARDEN

在 happy path 通过后，补充：

- 边界值；
- 重复、乱序、陈旧、future 和冲突输入；
- crash-before / crash-after；
- I/O timeout、短读、校验失败；
- 多进程竞态；
- 兼容性和迁移；
- 可观测性、错误分类和 artifact 捕获。

### 2.5 CHECK

独立 Checker 使用只读工作树或独立 worktree：

1. 阅读 research contract 和阶段 gate；
2. 先审查 diff，再运行验证；
3. 设计至少一个 Maker 未运行的反例；
4. 检查测试是否误把 mock 成功当作真实 backend 成功；
5. 检查是否在 Miyabi 登录节点进行了 runtime 工作；
6. 输出结构化 checker report；
7. 若 milestone Checker 未通过，明确记录失败现象、预期与实际、证据和原因；原因尚未证实时必须写 `unknown`，不得把推测写成 root cause。

写密集型任务不得由多个 subagent 并行修改同一核心目录。适合并行的工作仅限独立的文献核查、测试设计、日志分析、静态审查和互不重叠的 backend 实现。

### 2.6 PERSIST

每个循环结束时更新：

```text
plans/duraloco/STATE.yaml
plans/duraloco/DECISIONS.md
plans/duraloco/BLOCKERS.md
artifacts/duraloco/<phase>/<run_id>/manifest.json
artifacts/duraloco/<phase>/<run_id>/commands.log
artifacts/duraloco/<phase>/<run_id>/checker_report.md
plans/duraloco/phases/<phase>_PHASE_REPORT.md
```

`STATE.yaml` 必须能让一个全新的 Codex 会话在不依赖聊天历史的情况下恢复：当前阶段、当前 loop、通过/失败 gate、下一动作和仅限外部风险操作所需的审批。

### 2.7 双语里程碑与 Checker 失败报告

这里的 milestone 指每个 `PXX` 阶段（`P00`–`P12`）的 gate 结果。阶段首次进入 `checking`，以及随后到达 `completed` 或 `blocked` 时，Maker 必须创建或更新：

```text
plans/duraloco/phases/PXX_PHASE_REPORT.md
```

该 Markdown 报告必须在同一文件中包含 `## English` 和 `## 中文`，两部分陈述相同事实，至少包括：milestone/phase、当前状态、已完成与未完成的 acceptance targets、branch/commit、验证命令或 job/run IDs、Checker verdict、已知限制和下一动作。只翻译标题、不翻译正文不算双语报告。

当 Checker 给出 `FAIL`、`BLOCKED`，或带有阻塞必需 gate 的 `PASS_WITH_FOLLOWUPS` 时，agent 必须在修复或重试前，把以下内容追加到该报告的 Checker failure history，并同步写入对应 artifact 的 `checker_report.md`：

- failure attempt、时间和 Checker identity；
- **phenomenon / 现象**：可观察到的失败、最小复现、expected vs actual；
- **reason / 原因**：已证实的 root cause；若尚未证实则明确标记 `unknown` 并列出待验证假设；
- 受影响的 acceptance IDs/invariants、证据路径、job/run IDs；
- 修复动作、重试 lineage（新 run ID 和 `parent_run_id`）及当前结果。

失败历史是 append-only evidence。后续通过不得删除、覆盖或改写早先失败；只能追加 resolution。阶段不得在双语报告未反映最终 Checker 结果时标记 `completed` 或开始下一阶段。

当一个新的 `PXX` target 通过全部必需 gate 和独立 Checker 后，agent 必须创建一个 milestone archival Git commit，提交该阶段实现、最终 `STATE.yaml`、双语 phase report 和受版本控制的 evidence references。报告/状态必须记录 verified implementation/evidence commit；如还需记录刚生成的 archival commit SHA，则用紧随其后的 metadata-only commit 写入，避免要求 commit 自我引用。archival（及必要的 metadata）commit 成功前不得把下一 `PXX` 标记为已开始。此规则只要求 feature-branch commit，不授权 merge `main`。

### 2.8 自动目标与阶段推进

- 一个 loop/goal 的必需 acceptance gates 全部有证据且独立 Checker 结论为 `PASS`，或 `PASS_WITH_FOLLOWUPS` 且 follow-up 不影响必需 gate 时，agent 立即把该 goal 标记为完成并自动进入下一个 goal，无需用户复核。
- 一个 phase 的全部必需 acceptance IDs 通过后，agent 把 phase 标记为 `completed`，持久化报告和 verified commit，并按照依赖图自动创建/切换到下一 phase 分支继续执行；阶段之间不设置人工审核或等待状态。
- 可逆且位于既定 research contract 内的协议、默认值和实现选择由 agent 决定，写入 `DECISIONS.md`，经独立 Checker 复核后生效。
- 自动推进不授权 merge `main`、发布 artifact/公开数据、使用真实凭据或公共云/付费资源、超过 Miyabi 自主资源范围、删除共享数据或执行 destructive lifecycle 操作；这些外部风险动作仍按明确审批门处理，但不阻止不依赖该动作的后续工作。
- 若下一 phase 有多个依赖，只有所有依赖 phase 都 `completed` 且集成 Checker 通过后才自动进入；P08/P09 等并行分支必须按依赖图汇合，不得以单分支完成冒充集成完成。

## 3. 分支与 Worktree 纪律

- 每个阶段使用独立分支：`codex/duraloco-pXX-<slug>`。
- 阶段开始时记录 base branch 和 base commit；基线漂移时生成 `drift_report.md`。
- Codex 可以创建和 push feature branch，但不得默认合并 `main`。
- 阶段分支通过全部 gate 后状态为 `completed`；下一阶段从该 verified commit（或通过集成 Checker 的依赖汇合 commit）自动继续。是否最终 merge `main` 仍由用户决定，但不作为阶段推进条件。
- Worktree 只用于独立任务。协议核心、frontier/head、syncer pipeline 等共享写热点必须单 writer。
- Checker 必须使用不同工作树或至少干净 checkout，不能在 Maker 的未提交状态上判断。
- 禁止 `git reset --hard`、覆盖用户未提交修改、无授权 force push 或重写共享分支历史。

建议提交粒度：

```text
spec/test → minimal implementation → hardening → docs/migration → evidence
```

WIP commit 可以存在于 feature branch；提交合并候选前可在用户授权范围内整理，但只能使用 `--force-with-lease`，不得覆盖其他人的远端更新。

## 4. 持久化状态格式

### 4.1 STATE.yaml 最小字段

```yaml
phase: P00
status: in_progress  # planned | in_progress | blocked | checking | completed | ready_to_merge | merged
base_branch: codex/fs-diloco-miyabi
base_commit: <sha>
feature_branch: codex/duraloco-p00-contract
current_loop: 1
current_goal: "..."
attempts_for_current_failure: 0
last_verified_commit: null
checks:
  local_static: not_run
  local_runtime: not_run
  miyabi_login_static: not_run
  miyabi_1node: not_run
  miyabi_2node: not_run
  miyabi_9node: not_run
open_decisions: []
open_blockers: []
artifacts: []
next_action: "..."
automatic_progression: true
requires_human_approval: false
approval_reason: null  # 仅用于外部风险动作，不用于 goal/phase 过渡
```

### 4.2 Run manifest 最小字段

每次验证或实验产生不可变 manifest：

```json
{
  "run_id": "<uuid-or-content-id>",
  "purpose": "unit|contract|smoke|chaos|benchmark|experiment",
  "phase": "P00",
  "git_commit": "<sha>",
  "dirty_tree": false,
  "hostname": "<host>",
  "pbs_job_id": null,
  "pbs_nodefile_digest": null,
  "config_path": null,
  "config_digest": null,
  "dataset_revision": null,
  "model_revision": null,
  "backend": "memory|posix|lustre|minio|s3|hybrid",
  "seed": null,
  "commands_log": "commands.log",
  "stdout": "stdout.log",
  "stderr": "stderr.log",
  "exit_code": 0,
  "started_at_utc": "...",
  "ended_at_utc": "...",
  "result": "pass|fail|inconclusive",
  "assertions": []
}
```

禁止覆盖同一 run manifest。重试必须使用新的 run ID，并通过 `parent_run_id` 指向前一次尝试。

## 5. Miyabi 执行契约

### 5.1 Host routing

首先运行 `hostname`：

- 非 `miyabi-g*` / `interact-g*`：本地 workflow；
- `miyabi-g*`：登录/控制平面；
- PBS allocation 中的 `mg<number>`：compute/debug node；
- 不确定时同时检查 `$PBS_JOBID` 和 `$PBS_NODEFILE`，采用更安全解释。

### 5.2 登录节点允许与禁止

登录节点只允许：

- 读写文件、git 操作；
- `bash -n`；
- 使用满足 `pyproject.toml` 版本要求的项目解释器做 `py_compile` 等纯静态检查；本仓库使用 `.venv/bin/python`，不得因登录节点裸 `python` 可用而忽略其版本；
- 不执行项目 runtime 的静态检查；
- `qsub`、`qstat`、日志检查；
- 配置和命令 dry run。

登录节点禁止：

- `pytest`；
- 导入 `torch`、`transformers`、`datasets` 等重 runtime；
- 模型加载、训练、评估、预处理；
- `mpirun`、`torchrun`、CUDA/NCCL；
- 用“很小”作为绕过 PBS 的理由。

所有 PBS/interactive runtime 在启动项目代码前必须禁用 module pager、记录 `module list`、记录 Python 版本，并在作业 shell 内加载所需的精确 module/version。若明确依赖 Miyabi-G compute-node 默认栈，可以使用空 `REQUIRED_MODULES`，但必须在脚本和日志中声明并记录实际默认栈。

### 5.3 验证阶梯

```text
L0  test/spec construction
L1  local safe static/unit checks
L2  GitHub feature-branch sync
L3  Miyabi login-node static checks
L4  1-node PBS targeted runtime
L5  1-node real model/data ≤10 optimizer steps
L6  2-node PBS distributed/runtime contract ≤10 minutes
L7  full Miyabi batch within the autonomous envelope: select<=16 and walltime<=02:00:00
```

1-node interactive：

```bash
GROUP_ID="${GROUP_ID:-$(groups | tr ' ' '\n' | awk '/^xg/ {print; exit}')}"
GROUP_ID="${GROUP_ID:-$(groups | awk '{print $1}')}"
qsub -I -l select=1 -W group_list="$GROUP_ID" -q interact-g -l walltime=00:30:00
```

2-node interactive：

```bash
GROUP_ID="${GROUP_ID:-$(groups | tr ' ' '\n' | awk '/^xg/ {print; exit}')}"
GROUP_ID="${GROUP_ID:-$(groups | awk '{print $1}')}"
qsub -I -l select=2:mpiprocs=1 -W group_list="$GROUP_ID" -q interact-g -l walltime=00:10:00
```

进入 allocation 后确认 `hostname` 为 compute node。每次 runtime 尝试后执行：

```bash
qstat "$PBS_JOBID"
qstat -f "$PBS_JOBID" | egrep 'Job Id|job_state|resources_used.walltime|Resource_List.walltime'
```

若剩余 walltime 不足以完成下一次完整尝试和清理，退出并申请新 allocation。

Open MPI 环境传递使用：

```bash
mpirun ... /usr/bin/env "KEY=value" ... bash -lc '...'
```

不得混用 `mpirun -x` 与 `OMPI_MCA_mca_base_env_list`。

## 6. 验证证据分级

任何“通过”必须注明层级：

- `STATIC_PASS`：语法、schema、lint 或纯静态检查；
- `UNIT_PASS`：dependency-complete 单进程测试；
- `REFERENCE_PASS`：与 deterministic reference 比较；
- `CONTRACT_PASS`：真实 backend contract；
- `RUNTIME_PASS`：真实 process/runtime path；
- `MIYABI_1NODE_PASS`；
- `MIYABI_2NODE_PASS`；
- `MIYABI_9NODE_PASS`；
- `EXPERIMENT_COMPLETE`。

较低层级不得替代阶段要求的较高层级。MinIO 结果不得写成公共 S3 结果；synthetic smoke 不得写成模型质量结果；mock storage 不得写成 Lustre contract 结果。

## 7. 自动重试与停止

允许自动重试的情况：

- 确定为 transient 的 PBS 排队/连接、对象存储 5xx、受控随机故障；
- 重试策略本身是被测试对象；
- 每次重试有新 run ID 和 parent link。

必须停止的情况：

- 同一根因连续三次修复仍失败；
- 五个连续 loop 没有缩小失败面；
- 当前问题要求超出用户授权的研究目标或 materially 扩大研究主张；既定目标内的可逆语义选择由 agent 记录 ADR、经 Checker 复核后自动继续；
- 需要单个 Miyabi 作业超过 16 节点或 2 小时，或需要公共云/其他付费资源；
- 需要真实凭据、删除共享数据、运行 destructive GC；
- 出现可能污染论文结果的数据/代码版本不一致；
- 无法判断当前是否处于 Miyabi login 或 compute node。

停止时创建 `BLOCKER-<date>-<slug>.md`，包括最小复现、预期/实际、已尝试方案、证据、影响范围、候选决策和推荐下一步。不要用扩大重构来掩盖阻塞。

## 8. 研究结果纪律

- 不得填充虚构 loss、throughput、P99、cost 或 improvement。
- 目标阈值以 `target` 标记，实测以 `observed` 标记。
- 所有图表只从不可变 run manifests 和原始日志生成。
- 分析脚本必须能在丢失某个 run、seed 不齐、配置不匹配时拒绝聚合。
- 负面结果保留，不删除异常 seed；排除 run 必须给出预注册规则和理由。
- 每个论文 claim 维护 `claim → metric → experiment ID → run IDs → figure/table` 追踪链。

## 9. 安全和成本

- 凭据只能来自环境、Miyabi 允许的 secret 机制或用户明确提供的临时凭据；禁止写入 Git、配置、日志或 artifact。
- Agent 可自行决定并提交单个 `select<=16` 且 `walltime<=02:00:00` 的 Miyabi 作业，包括 9-node 作业，无需用户批准；仍须遵守阶段前置 gate、作业预检和 1→2→9 验证阶梯。
- 单个 Miyabi 作业超过 16 节点或 2 小时，以及 public cloud、跨区域 egress、其他付费资源和 destructive lifecycle policy，均需用户批准。
- GC 默认 dry-run，直到 reachability proof 和并发恢复测试通过；实际 destructive apply 仍需外部风险审批，但不构成 phase-transition review。
- 故障注入只能作用于隔离的 run root/bucket prefix，不得向共享根目录发送 kill/delete。

## 10. 完成定义

阶段只有同时满足以下条件才可标记 `completed` 并自动进入下一阶段：

1. 所有阶段 acceptance IDs 有证据；
2. Checker 结论为 `PASS`，或 `PASS_WITH_FOLLOWUPS` 且 follow-up 不影响任何必需 gate；
3. 必需的 Miyabi 层级已运行，或明确标为 `BLOCKED`，不能用“未运行但应当可以”代替；
4. 文档、迁移说明和 config schema 与实现一致；
5. branch 已 push，工作树干净；
6. 结果中没有未解释的 NaN、重复 apply、split-brain、live-object deletion 或状态漂移；
7. 未自动 merge `main`；阶段推进使用 verified phase/integration commit，不等待 main merge。

## 11. 共同启动指令

```text
读取仓库根 AGENTS.md、miyabi-development skill、DuraLoCo 共同执行契约和当前阶段计划。先识别 hostname、branch、commit 和工作树状态。使用单 writer 的 maker loop；先写失败测试/规范，再做最小实现；独立 checker 复核。每轮更新 STATE.yaml 和 artifact manifest。goal/phase 必需 gate 达成并通过 Checker 后立即标记 completed，并按依赖图自动推进，不等待用户审核。遵守 Miyabi 登录节点 control-plane 限制与 1→2→9 节点验证阶梯。单个 select<=16 且 walltime<=02:00:00 的 Miyabi 作业（包括 9 节点）由 agent 自主决定和提交；超出此范围或使用公共云/其他付费资源前取得用户批准。不得自动合并 main，不得虚构实验结果。
```

## 12. 参考

- Miyabi Codex skill：https://github.com/UnbearableFate/miyabi-development
- 当前 prototype：https://github.com/UnbearableFate/fs_based_decoupled_diloco/tree/codex/fs-diloco-miyabi
- OpenAI Codex skills：`https://developers.openai.com/codex/skills`
- OpenAI Codex `AGENTS.md`：`https://developers.openai.com/codex/guides/agents-md`
- OpenAI Codex worktrees：`https://developers.openai.com/codex/app/worktrees`
- 研究草稿：`references/DuraLoCo_research_draft_zh.md`
