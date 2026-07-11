---
title: "DuraLoCo Codex Loop Operating Contract"
version: "3.0"
date: "2026-07-11"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
architecture_target: "learner-hosted distributed fragment syncer"
---

# DuraLoCo Codex Loop Operating Contract

本文件定义所有阶段共享的执行协议。阶段文件描述“做什么”，本文件描述 Codex 如何以可恢复、可审计的 loop-engineering 方式持续完成工作。任何实现捷径只要引入第二 authority、不可重放状态或无法验证的研究 claim，都必须视为 blocker。

## 1. Agent Loop

每个最小工作单元执行：

```text
ORIENT → SPECIFY/RED → IMPLEMENT/GREEN → HARDEN → CHECK → PERSIST
   ↑                                                       │
   └────────────── next smallest failing gap ───────────────┘
```

### ORIENT

先记录：

```bash
hostname
git status --short --branch
git rev-parse HEAD
git log -5 --oneline
```

然后读取根 `AGENTS.md`、当前阶段、上一阶段 report/checker、`STATE.yaml`、未关闭 ADR/blocker、`SQLITE_FREE_SYSTEM_DESIGN.md`、`DISTRIBUTED_SYNCER_SYSTEM_DESIGN.md`、实现经验文件和相关研究差异文档。P06A 以后还必须读取 CRS oracle trace schema 和最近一个 equivalence report。

### SPECIFY/RED

生产实现前，先建立至少一种会在旧实现或错误实现上失败的证据：

- state-machine trace 或 golden transition；
- unit/property test；
- crash/fencing failpoint；
- capability audit；
- storage contract test；
- topology manifest checker；
- numeric digest comparison；
- interference/latency baseline；
- reachability/GC counterexample。

测试必须能证明目标缺陷，而不是只覆盖新代码行。

### IMPLEMENT/GREEN

只做让当前最小失败证据通过的修改。P06A 后遵守：

- pure policy/kernel 不读取 process identity、wall clock、directory order 或 mutable global；
- executor 只 prepare，不能隐式升级为 committer；
- committer 只通过当前 fenced lease 和 head CAS 成为 authority；
- immutable object 先写、校验、再由 commit transition 引用；
- listing/heartbeat 只 discovery；
- executor local cache 可删除且不可影响结果；
- duplicate work order 必须 deterministic；
- 所有影响算法结果的 policy/config identity 进入 work order 与 transition digest。

### HARDEN

至少覆盖：response loss、duplicate delivery、partial publication、stale epoch、owner/committer crash、node co-failure、head advance、CAS ambiguity、corrupt object、listing omission、slow storage 和 cancellation。P06C 后每个新 mutation path 必须加入 fault matrix。

### CHECK

Maker 与 Checker 使用不同上下文。Checker 必须：

1. 从 invariant 和 diff 反推漏项；
2. 执行至少一个 Maker 未列出的反例；
3. 删除本地 runtime state 并验证恢复；
4. 检查 capability/authority surface；
5. 核对 acceptance ID、manifest、raw trace、commit 和报告；
6. 对性能 claim 检查 matched topology、资源预算和置信区间；
7. 只输出 `PASS`、`PASS_WITH_FOLLOWUPS` 或 `BLOCKED`。

### PERSIST

每个 loop 更新：

- `plans/duraloco/STATE.yaml`；
- `DECISIONS.md`/`BLOCKERS.md`；
- artifact manifest、commands、raw outputs；
- acceptance evidence map；
- 当前 clean commit；
- 下一项最小 failing gap。

会话结束不得是唯一进度保存点。

## 2. Authority 与 capability contract

### 2.1 唯一 authority

只有从 current global head 可达的 committed transition prefix 是 optimizer truth。以下均不是 authority：

- proposal listing；
- executor heartbeat；
- ownership cache；
- local queue/cursor；
- Fragment Work Order（在未 commit 前）；
- Prepared Fragment Transition；
- materialized latest model；
- telemetry、report、CSV/JSONL；
- Central Reference Syncer 的内存状态。

### 2.2 Capability separation

P06B 以后至少定义：

| capability | 允许操作 | 禁止操作 |
|---|---|---|
| learner | publish immutable proposal；读取 committed model/frontier | head CAS、ownership control、prepared winner decision |
| executor | 读取 committed parent/FWO；写 immutable PFT | head CAS、membership change、authoritative stop |
| committer | 计划/发布 FWO；验证 PFT；写 final transition；head CAS | 修改 learner local state；绕过 replay/validation |
| lifecycle worker | snapshot、reachability、dry-run GC；经审批 apply | 改写 committed history |
| CRS | reference execution、baseline、fallback | 在 distributed production run 中成为隐式第二 authority |

静态 import audit、runtime credential/path audit 和 fault test 必须共同证明 capability boundary。
该边界是当前非Byzantine failure model下的software/API least-authority边界，不是同一Unix
账号内对恶意Python代码的安全sandbox。LFE production entrypoint只能接收不含head key和
`conditional_replace`的restricted facade；source/import audit用于防止意外越权，论文和
报告不得声称OS级隔离。

### 2.3 Identity hierarchy

```text
run_generation
  ├── committer_fencing_epoch
  └── membership_revision
       └── ownership_digest
            └── work_order_id(parent_head, fragment, selection, policy, execution_backend)
                 ├── prepared_result_digest(work_order_id, input/output content)
                 └── attempt_envelope_id(result_digest, executor_session, attempt)
                      └── committed_transition_id(parent_head, work_order_id, result_digest)
```

同 identity/不同内容 fail closed；不同 identity/相同 payload 不得被误判为同一 request。

## 3. 阶段切换 contract

### P06 → P06A

当前仓库P06-A01–A20已经完成；完整CRS oracle trace不是其历史gate。P06A从P06 archive
tip建立只读characterization bundle，并只做decomposition/equivalence，不改变生产拓扑。

### P06A → P06B

只有 pure kernels、shared schemas、capability audit 和 central-vs-decomposed digests 全部通过，才允许 learner hosts 执行 prepare。

### P06B → P06C

P06B 以 replication factor 1 建立 no-dedicated-syncer D8 主路径；P06C 才引入 overlapping ownership、backup/hedge 和 reconfiguration。

### P06C → P07R → P08R

P06C failure matrix完成后先启动P07R并冻结lifecycle/object identity接口；P08R从P07
verified commit顺序启动。不得并行修改尚未存在或尚未冻结的shared schema/commit semantics。

## 4. Validation topology contract

- 本地：pure kernel、simulator、storage fake、property tests。
- Miyabi D1：单节点 learner + LFE + bootstrap/floating committer；真实 model/data 小步运行。
- Miyabi D2：两 learner 节点，无专用 syncer；kill executor、kill committer、kill whole node。
- Miyabi D8：八 learner 节点，无专用 syncer；主验收。
- Miyabi D8-R2：八节点、replication factor 2；重叠执行与故障验收。
- C9：八 learner + 一 dedicated CRS，只用于 reference/baseline 和 matched comparison。

禁止在 Miyabi login 节点运行 pytest、torch/transformers/datasets import、training、mpirun 或其他 runtime；login 节点仅做 git、文本检查、PBS submit/inspect 和 artifact 下载。

## 5. Determinism contract

相同 committed parent、work-order identity、proposal object digests、policy/config identity 和 implementation identity 必须生成相同：

1. selected proposal IDs 与 weights；
2. aggregate digest；
3. new parameter fragment digest；
4. new outer optimizer state digest；
5. final transition semantic digest。

同一FWO的LFE primary/backup和replay必须冻结相同execution backend/thread/reduction identity
并满足bitwise/content equivalence。当前GPU CRS与CPU LFE的跨backend比较必须保留双方
content digest并使用预注册tolerance report，不能声称digest相等；如需exact比较，offline
CRS必须使用同一backend。浮点nondeterminism不能通过“任选成功者”掩盖。

## 6. Failure handling contract

- crash before object marker：对象不可见，安全重试；
- crash after immutable PFT、before commit：PFT 是 orphan/evidence，可复用或回收，不能被 learner adopt；
- commit response loss：通过 request identity、head ancestry 和 committed transition reconciliation；
- stale membership/ownership：PFT 可保留但必须被 current committer拒绝；
- stale committer：P05 fencing + CAS 拒绝；
- duplicate same digest：可选择一个 winner，其他标记 loser；
- duplicate divergent digest：阻塞 run、保存两个 outputs 和 environment evidence；
- whole learner node loss：committed reconfiguration 后由新 owner 从共享存储重算，不迁移私有 optimizer state；
- storage ambiguity：strict replay，不基于 listing absence 宣告未提交；
- false failure suspicion：允许影响 latency/额外计算，不得影响 safety。

## 7. Performance and interference integrity

learner-hosted CPU 计算可能竞争 CPU cores、memory bandwidth、PCIe/NVLink path 和 Lustre I/O。每个 D8 性能结论必须报告：

- GPU step time/MFU 或可用等价指标；
- LFE CPU cores、affinity、NUMA、RSS、memory bandwidth proxy；
- proposal/PFT/transition bytes 与 metadata operations；
- publish→work-order→prepare→commit→adopt 分段延迟；
- executor queue、hedge rate、duplicate wasted CPU；
- C9 与 D8 的 node-hours、GPU-hours 和 useful-token goodput；
- training quality under matched tokens/compute。

不得只报告“节省一个节点”而忽略 learner GPU slowdown。

## 8. Terminal failure discipline

同一根因三次修复仍失败，写 blocker 并缩小问题，不扩大重构。非 transient D8/D8-R2 terminal failure 后禁止立即同 shape 重提；先完成 workflow review、targeted D1 benchmark、同 clean commit 的 D1→D2 重验收，再提交一次新 retry。所有失败、取消和重试保持 `parent_run_id` lineage。

## 9. Research integrity

计划值、目标值和实测值必须分开。相关工作中已有的单项机制——CPU syncer、parameter sharding、external storage communication、serverless aggregation、backup execution、logging/replay——不得被包装为独立首创。论文主张应聚焦经过证据支持的组合：storage-resident stateful outer optimizer authority、learner-hosted roleless executors、redundant prepare 与 single logical commit、ownership change without optimizer-state migration，以及 HPC no-dedicated-syncer resource trade-off。

## 10. Error reporting contract

非预期错误必须在下一次修复或重提作业前及时报告并写入phase error ledger。报告至少包含：

- 错误现象：原始异常/exit code、实际terminal state、job/host/commit和日志路径；
- 预期行为及受影响的acceptance/invariant；
- 原因：明确区分direct evidence支持的`confirmed`与尚未证明的`unknown/hypothesis`；
- 解决方法：代码、配置或流程的具体修改，及为什么能修复根因；
- 验证方法：最小复现、targeted gate、后续D1/D2/D8资格验证；
- retry决定、parent lineage、保留的manifest/checksum/artifact。

预期fault injection必须标为`expected_rejection`或`expected_blocked`，不得与unexpected
failure混为一谈。shell `|| true`只能用于best-effort artifact capture，不能把runtime或
checker失败转换成pass。详细格式使用`templates/ERROR_RECORD.yaml`。
