# DuraLoCo 当前架构

## 核心设计

DuraLoCo 把一次 fragment merge、outer-optimizer update 和恢复点绑定为同一个持久事务。共享
文件系统既承载 proposal/参数/optimizer 大对象，也承载不可变 commit log；系统没有第二套
持久 optimizer authority。

```text
learner GPU
  │ local interval + proposal（payload-first, marker-last）
  ▼
immutable proposal catalog
  │ validate → select → fenced fragment work order (FWO)
  ▼
learner-hosted CPU executors (LFE, factor 1 or factor 2)
  │ immutable prepared fragment result (PFR, marker-last)
  ▼
floating committer
  │ verify ownership/result → write params/outer/commit/frontier
  ▼
single head CAS ───────► committed global optimizer trajectory
```

任何在 head CAS 前存在的 payload、work order、prepared result、commit 或 frontier 都只是 prepare
或 orphan。目录 listing 只做 discovery/GC inventory，不决定 committed state。

## Runtime 角色

### Learner

每个 learner 独立在一张 GPU 上训练 local interval。它从 committed frontier 采用全局参数，维护
私有 inner optimizer、scheduler/scaler、RNG、data cursor 和 interval state，随后发布 fragment
proposal。proposal 绑定 learner/session/sequence、因果 base、fragment、local steps/tokens、layout
digest、payload ObjectRef 与 dtype/shape/finite contract。

learner adoption 可选择 `reset_all`、`reset_updated_fragment` 或 `preserve`，但只有与实验配置和
验收证据一致的行为才能支撑结果。exact capsule 可保存完整私有状态；普通 proposal 本身不是
learner checkpoint。

### Learner-hosted fragment executor (LFE)

LFE 是 CPU 进程，读取一个 authoritative FWO 及其 input bundle，验证 params、outer state 和
selected proposal payload，执行 deterministic aggregation/outer update，并 marker-last 发布 PFR。
executor 不能推进 head，也不能自行改变 membership、selection 或 fencing epoch。

factor 2 时，一个 FWO 绑定 primary/backup owner：

- `warm_standby`：backup 等待显式激活；
- `active_active`：两份结果并行计算；
- `hedged`：backup 在固定 delay 或故障证据后启动。

同一 backend identity 下的 duplicate result 必须 identity-equal；不同 digest 的结果是 blocker，
不能以“先到者获胜”掩盖数值分歧。

### Floating committer

committer candidate 运行在 learner host 上。lease 是 mutable coordination record，但 owner 权威
必须由 committed epoch bump 进入 head chain。owner 负责 strict replay、proposal validation/
selection、FWO 发布、PFR 验证、commit/frontier prepare 和最终 head CAS。

active owner 失效后，standby 必须等待 lease 安全失效、取得更高 epoch，并在空缓存上 strict
replay。旧 epoch owner 此后不能推进 head。D8-R2 有两个 eligible candidate，没有 dedicated
syncer node。

## Authority 与非权威数据

唯一 mutable authority：

```text
authority/runs/<run>/generations/<generation>/control/head.json
```

不可变但可被 committed chain 引用的对象包括 run manifest、proposal、learner publication、
membership、FWO/input bundle、PFR/attempt envelope、params、outer state、commit、frontier、
snapshot、pin/ack、capsule、GC mark/request/result 和 failure evidence。

`control/lease.json` 是协调对象，只有 committed fencing transition 才能改变 optimizer authority。
`latest.json`、`stop.json`、heartbeat、topology convenience files、materialized checkpoint、日志和
W&B 都是 derived/observational；损坏或删除它们不会改变 replay 结果。

## Generation、membership 与 identity

run generation 隔离 schema/compatibility 边界。RunSpec 冻结 codec、numeric mode、optimizer、
weighting、parameter/fragment layout digest、coordination protocol、revision-zero membership、
replication factor 和 execution backend digest。跨 generation 只能显式 warm start，不能继承旧的
proposal consumption、session sequence 或 exact-continuation 权威。

membership revision 是 committed transition。FWO identity 同时绑定 parent、selection、canonical
weights、membership revision、ownership/fencing、backend 和 layout。因此 failover 或 reconfiguration
后不能把旧 prepared result 误用于新 owner/new membership。

## 当前验证拓扑与兼容路径

H0 D8-R2 在 9-node allocation 上使用前 8 个节点承载 8 learner + 8 LFE，两个 floating
committer candidate，replication factor 2；第 9 节点是 allocation control-plane host。该拓扑通过
10 transitions、executor loss、whole-host loss、membership revision 与 lifecycle gate。

`fs_diloco.syncer`、`fs-diloco-syncer` 和早期 `run_*debug.pbs` 仍保留为 central/reference 路径。
它们不是当前 distributed qualification，不应被描述成 DuraLoCo 的唯一或推荐拓扑。
