# DuraLoCo 项目状态

状态日期：2026-07-12

当前已验证阶段：P07 已完成

下一个必需阶段：P08

当前 feature branch：`codex/duraloco-p07-distributed-lifecycle`

P07 已验证 implementation/Checker commit：`c099adc3c3a99127569a7d9bf38a58547022173c`

## 执行摘要

DuraLoCo 已经从 baseline contract 推进到 distributed lifecycle，形成经过验证的 SQLite-free、
event-sourced 实现。当前 production 路线使用 learner-hosted fragment executor 与
learner-hosted floating committer candidate，不需要 dedicated syncer node。immutable
transition object 与唯一 global head compare-and-swap 仍是唯一持久 optimizer authority。

已完成工作在 D8-R2 拓扑上证明 correctness、recovery、redundancy 与 lifecycle safety：八个
learner node、八个 learner、八个 learner-hosted fragment executor、replication factor 2、
零 dedicated syncer node。P07 增加 ancestry-pinned snapshot、snapshot+suffix replay、typed
reachability、guarded GC、exact learner capsule、bounded lifecycle retention，以及长 lifecycle
操作期间的 lease safety。独立 Checker 已通过全部 24 项验收。

项目尚未全部完成。P08 必须在不削弱 validation 或 authority 的前提下，减少 prototype 数据
移动与 lifecycle overhead，增加可重建 stage telemetry，并量化 learner/LFE resource
interference。P08 之后仍有必需的 P10、P11、P12。P09 是 P12 之后的可选 object-store
扩展，不属于自动推进路线。

## 已冻结的 authority 与架构

持久 source of truth 是 committed DuraLoCo transition chain 加唯一 global head CAS。一次
commit 可以原子引用 parameter fragment、对应 outer-optimizer state、membership/ownership
事实、fencing 事实与 control transition。系统没有 per-fragment head，也没有 mutable database
authority。

其他内容均为 immutable input/evidence 或 derived observation：proposal、work order、prepared
result、execution attempt、lease、heartbeat、snapshot、capsule、ack、GC mark、`latest.json`、
checkpoint、telemetry 与 report。这些对象可以改进 discovery、performance、audit 或 recovery，
但不能独立选择或推进 optimizer trajectory。

learner-hosted fragment executor 只有 prepare capability。floating committer 只有在持有当前
committed fencing identity 与 observational lease 时，才能更新 global head。membership 与
ownership 变化是 committed fact；heartbeat suspicion 只是 evidence，而不是 authority。
duplicate work 是允许的，但一个 work-order identity 最多只能产生一个 logical committed
result。等价 duplicate 会收敛；divergent result 必须 fail closed 并保留审计证据。

fresh open、takeover、explicit verification、CAS ambiguity、head jump、corruption suspicion 或
ownership boundary 变化都必须从 empty-cache strict replay 开始。process-local verified-object
memoization 只能在完整成功 replay 后使用，不能序列化，也不能跨 ownership 传递。

## 已完成 milestone 路线

| Milestone | 状态 | 已交付能力 | 主要验证证据 |
|---|---|---|---|
| P00 | 已完成 | baseline inventory、research contract、invariant 与 Agent Spine | `993accd`、独立报告 |
| P01 | 已完成 | Protocol v2 schema、identity、strict validation、quarantine、v1 adapter | `cfa7442`、单节点/Checker |
| P02 | 已完成 | 独立 deterministic reference simulator 与 in-memory backend | `7e12997`、10,000 trace/Checker |
| P03 | 已完成 | semantic storage API 与 POSIX/Lustre capability/fault contract | `952b39b`、单/双节点/Checker |
| P04 | 已完成 | transactional fragment log、one-CAS commit、prefix recovery、strict replay | `a655413`、单/双/九节点/Checker |
| M00 | 已完成 | 删除 SQLite authority，并在 log-only runtime 上重验 P00–P04 | `c052438`、单/双/九节点及 Checker |
| P05 | 已完成 | production syncer lease、committed fencing、failover、control transition | `82dbec1`、最终 1/2/9 节点；Checker `fe41f80` |
| P06 | 已完成 | learner interval、boundary adoption、response-loss publication、warm recovery | `2581a4d`、最终 1/2/9 节点；Checker `030129e` |
| P06A | 已完成 | pure syncer kernel 分解与 archived CRS equivalence | `5a71502`、C1/C2/C9；Checker `cea5a6d` |
| P06B | 已完成 | learner-hosted executor、distributed prepare、无 dedicated syncer 的 factor-one D8 | `d5e2901`、D1/D2/D8；Checker PBS `2362890` |
| P06C | 已完成 | factor-two ownership、duplicate convergence、hedging、reconfiguration、failover | `cba9f48`、D1-R2/D2-R2/D8-R2；Checker PBS `2363373` |
| P07 | 已完成 | snapshot、reachability、guarded GC、exact capsule、bounded lifecycle | `2295467` runtime；报告 PBS `2368976`；Checker `c099adc`/PBS `2369002` |

P00–P04 是原 staged route 的历史证据。M00 是强制 runtime rebase：历史 database-era 报告仅
作为证据，不恢复 compatibility database runtime。P05/P06 建立 central reference behavior，
P06A 将其分解，P06B/P06C 再实现 distributed 路径。

## 当前已验证 distributed behavior

P06B factor-one D8 使用八个 learner node、八个 learner、八个 LFE、两个 learner-hosted
committer candidate 与零 dedicated syncer，在 470 秒内完成 GPT-2/WikiText-2 50×10、十次
optimizer transition 与完整 publish→prepare→commit→adopt timing。它仍是冻结的 factor-one
baseline。

P06C hedged factor-two D8-R2 用 528 秒完成同一 workload，证明 redundant prepared
execution、whole-node membership reconfiguration、committer takeover、strict replay 与
authoritative stop。它也保留了重要负结果：在当前 storage 与六秒 hedge delay 下，elapsed
增加 12.3%，logical executor input 为 factor-one 的 1.77 倍，output 为 1.90 倍。
correctness/availability 通过，但该 regime 下 redundancy 没有带来 throughput 收益。

P07 lifecycle-enabled D8-R2 用 1100 秒完成十次 optimizer transition，并增加五个
snapshot/GC cycle、五个 snapshot pin、每个 learner 一个 exact capsule、executor-process
loss、whole learner-host loss、membership revision 1 与 authoritative stop。有效 authority
已经完成，但旧的 900 秒 report envelope 拒绝了 wrapper；PBS `2368976` 使用保留的 authority
恢复出 PASS 报告。

P07 effective-live sample 为 150、196、220、248、276，最后三个 sample 的增量是 56，低于
预注册上限 64。因为真实 namespace 按设计只执行 dry-run，raw inventory 仍会增长；terminal
有 245 个可解释且在 guarded policy 下 eligible 的 candidate。这是 bounded active window
主张，不是说 dry-run storage 的物理容量恒定。

## 已建立的 safety 与 recovery property

- strict、memoized 与合法 snapshot+suffix replay 一致；snapshot 失败只影响性能，并回退到
  strict replay；
- snapshot 只有通过 committed ancestry pin 才成为 root，不会形成第二 mutable head；
- reachability 以 typed root/edge 解释所有 live/candidate object，包括 FWO/PFR lineage、
  equivalent loser grace、divergent evidence、response loss、capsule、snapshot、ack、pin 与
  quarantine；
- listing 缺失不能证明 unreachable，unknown schema 默认受保护；
- 真实 namespace 默认 GC dry-run；没有 explicit human gate 时 destructive apply 只允许
  synthetic namespace，并在删除前重新验证 authority；
- partial delete 与 response loss 通过 immutable request identity 恢复，删除顺序 marker-last；
- exact capsule 必须包含 model/frontier、inner optimizer、scheduler/scaler、RNG、data cursor、
  interval state 与兼容 topology；不完整 state 不能标记为 exact；
- 两个独立验证的 snapshot base 能在 compaction/GC 后承受 newest-base corruption；
- long lifecycle substage 期间持续续租；续租或 ownership 失败会阻止 stale result 被使用；
- active source、configuration、script、test 与新 artifact 均没有 SQLite 或替代 embedded
  database。

## 失败历史与工程经验

项目保留 failed/inconclusive evidence，而不是只展示成功运行。当前 operating contract 已吸收
以下反复出现的经验：

1. control-plane 与 runtime evidence 必须分开。Miyabi login node 只用于 static work 与 job
   submission；runtime validation 必须在 PBS compute node 上执行。
2. process exit success 不足以作为证据。报告必须断言 optimizer transition count、
   authoritative stop、committed ancestry、participant topology 与 evidence identity。
3. reporting failure 不能抹掉有效 authority。P07 D8 的 fixed report envelope 失败时，authority
   已经完成；后续从 raw authority 通过明确 schema validation 恢复报告。
4. terminal retry 必须由证据驱动。九节点出现 non-transient failure 后，workflow 保存 manifest
   与 stage timing、撰写 review、用最小 targeted benchmark 证明修复，再依次重跑单节点、双节点，
   最后只执行一次新的九节点 attempt。
5. lease 必须覆盖 substage，而不仅是 outer loop。replay、reachability 与 lifecycle scan 可能
   超过 nominal TTL，因此 fenced owner 必须在整个长操作期间由 fail-closed guard 续租。
6. marker-last publication 与 deletion grace 是 protocol requirement。早期 cleanup race 已证明
   目录 appearance 不是 durable object identity。
7. performance claim 必须保留负结果。P06C redundancy overhead 与 P07 lifecycle latency 是
   optimization input，不能成为削弱 safety 的理由。

## 当前 gap 与风险

P08 是当前直接 gap。现有实现在部分路径仍有 prototype whole-model/repeated fragment copy；
Python graph/replay 路径使 D8 后期单次 lifecycle 时间达到 141.89 秒；系统也缺少统一重建每个
publish/plan/prepare/commit/adopt stage 的最终 structured telemetry。scanner work、validation
reuse、CPU/NUMA placement、pinned-buffer budget 与 learner GPU interference 都需要 matched
measurement。

P08 不能预设 bundling 有收益。它必须先 profile direct fragment I/O、streaming reduction、
validation reuse、scanner bound 与 resource isolation。只有 preregistered bottleneck gate 触发，
并且新 generation/schema 能证明 canonical serial equivalence 与 P07 reachability integration，
才实现 multi-FWO/one-CAS bundle；否则相关验收应由独立 Checker 以有证据的
`not_applicable` 关闭。

后续 gap 包括 P10 storage-aware coordination、P11 正式 Miyabi chaos/final
dedicated-syncer-free acceptance，以及 P12 experiment/artifact/paper evidence。algorithm-affecting
adaptation 必须等 fixed/shadow mode 证明 observation/controller boundary 后才能进入。正式科学
主张需要 matched baseline、raw immutable run ID、analysis script 与保留的负结果。

## 已授权下一路线

当前必需路线为：

```text
P07 completed → P08 performance core → P10 SACC → P11 Miyabi acceptance → P12 evaluation
```

P08 应从已验证 P07 implementation 顺序创建分支，先执行 orientation/profile loop，并把完整 P07
lifecycle test 与 Checker contract 作为 regression。阶段完成不授权自动合并 `main`。
