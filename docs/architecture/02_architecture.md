# Architecture / 体系结构

## Runtime roles / 运行时角色

```text
 ┌────────────────────────────── learner host × 8 ──────────────────────────────┐
 │                                                                              │
 │  Learner (GPU)                     LFE — fragment executor (CPU)             │
 │  local inner training              reads FWO + input bundle,                 │
 │  publishes proposals ──────┐       streams weighted reduction,               │
 │  (payload-first,           │       runs outer optimizer,                     │
 │   marker-last)             │       publishes PFR (marker-last)               │
 │                            │                        ▲          │             │
 └────────────────────────────┼────────────────────────┼──────────┼─────────────┘
                              ▼                        │          ▼
 ┌──────────────────────────── shared Lustre filesystem ────────────────────────┐
 │  immutable objects: proposals, params, outer state, commits, frontiers,      │
 │  membership, FWO, input bundles, PFR, snapshots, capsules, GC marks…         │
 │  ONE mutable authority: control/head.json  (conditional replace = CAS)       │
 │  ONE coordination record: control/lease.json (hint only, never authority)    │
 └──────────────────────────────────────────────────────────────────────────────┘
                              ▲                        ▲
                              │ validate/select        │ verify + commit
 ┌────────────────────────────┴────────────────────────┴─────────────────────────┐
 │  Floating committer (CPU, runs on a learner host; 2 candidates, 1 active)     │
 │  strict replay → catalog scan → selection → publish FWO → wait PFR →          │
 │  validate → prepare commit/frontier → head CAS → materialize derived views    │
 └────────────────────────────────────────────────────────────────────────────────┘
```

### Learner

**EN** — One process per GPU (`fs_diloco/learner.py`). It adopts committed global fragments
from the materialized derived views, keeps private inner optimizer / scheduler / RNG / data
cursor state, trains a *contribution interval* (`training.inner_steps` steps), and publishes a
fragment proposal: a bfloat16 safetensors payload plus a canonical manifest binding
learner/session/sequence, the causal base (commit id/seq, frontier digest, fragment version),
token/step counts, tensor metadata, and payload `ObjectRef`. Publication is payload-first,
marker-last, with a durable request identity so a crash/retry can never create two different
proposals for the same interval. Optional *exact capsules* capture full private state for
bitwise-exact restart.

**中文** — 每 GPU 一个进程（`fs_diloco/learner.py`）。它从物化派生视图采用已提交的全局
fragment，维护私有 inner optimizer / scheduler / RNG / data cursor 状态，训练一个
*contribution interval*（`training.inner_steps` 步），然后发布 fragment proposal：bfloat16
safetensors payload 加 canonical manifest，绑定 learner/session/sequence、因果 base（commit
id/seq、frontier digest、fragment version）、token/step 计数、张量元数据与 payload
`ObjectRef`。发布采用 payload 先行、marker 最后的顺序，并带持久 request identity，因此崩溃
重试不可能为同一 interval 造出两个不同 proposal。可选的 *exact capsule* 捕获完整私有状态，
支持逐位精确重启。

### Learner-hosted fragment executor (LFE)

**EN** — A CPU process on each learner host (`fs_diloco/distributed_syncer/executor.py`). It
consumes exactly one authoritative Fragment Work Order (FWO) at a time, verifies the referenced
params/outer-state/proposal payloads, performs the ordered streaming weighted reduction and the
deterministic outer-optimizer step, and publishes a Prepared Fragment Result (PFR) marker-last.
It can never advance the head, change membership, selection, or fencing. Under replication
factor 2, a fragment's FWO names a primary and a backup owner with a redundancy policy
(`warm_standby` / `active_active` / `hedged`); duplicate results for the same backend identity
must be bit-identical or the commit is blocked.

**中文** — 每个 learner 主机上的 CPU 进程（`fs_diloco/distributed_syncer/executor.py`）。它一
次只消费一个权威 Fragment Work Order（FWO），校验其引用的 params / outer state / proposal
payload，执行有序流式加权归约与确定性 outer-optimizer 步骤，然后以 marker-last 方式发布
Prepared Fragment Result（PFR）。它永远不能推进 head，也不能改变 membership、selection 或
fencing。复制因子为 2 时，FWO 绑定 primary/backup 两个 owner 及冗余策略（`warm_standby` /
`active_active` / `hedged`）；同一 backend identity 下的重复结果必须逐位一致，否则提交被阻断。

### Floating committer

**EN** — The only writer of authority (`fs_diloco/distributed_syncer/committer.py`). Candidates
run on learner hosts; exactly one is active. The active owner: acquires the lease, commits an
epoch-bump into the head chain (fencing), strict-replays authority, scans and validates the
proposal catalog, freezes a deterministic selection and canonical weights, publishes the FWO +
input bundle, waits for the PFR, re-validates everything, prepares the commit/frontier objects,
and performs the single head CAS. On owner loss, the standby waits for safe lease expiry
(TTL + skew), takes a higher fencing epoch, and starts from an empty-cache strict replay.

**中文** — 权威的唯一写者（`fs_diloco/distributed_syncer/committer.py`）。候选运行在 learner
主机上，同一时刻只有一个 active。active owner 的职责：获取 lease，把 epoch-bump 提交进 head
链（fencing），strict replay 权威，扫描并验证 proposal catalog，冻结确定性 selection 与
canonical 权重，发布 FWO + input bundle，等待 PFR，重新验证一切，准备 commit/frontier 对象，
最后执行唯一的 head CAS。owner 失效时，standby 等待 lease 安全过期（TTL + 时钟偏差），取得更
高 fencing epoch，并从空缓存 strict replay 开始。

## The authority model / 权威模型

**EN**

| Class | Examples | Mutability | Role in recovery |
|---|---|---|---|
| Mutable authority | `control/head.json` | conditional replace only | the *only* thing recovery trusts |
| Coordination hint | `control/lease.json` | conditional replace | liveness only; never grants authority |
| Immutable committed objects | commits, frontiers, params, outer state, proposals, membership, snapshots | create-once, content-addressed | reachable from head ⇒ part of state |
| Prepared / orphan objects | FWO, input bundle, PFR, losing CAS attempts | immutable | ignored unless referenced by a committed chain |
| Derived / observational | `latest.json`, `stop.json`, heartbeats, checkpoints, CSV/JSONL/W&B, telemetry | rewritable | never consulted by recovery |

Recovery is a *fold* over the head-reachable committed prefix: strict replay walks the
parent-linked chain from the verified head back to genesis, checks every manifest, digest,
causal rule, weight, and consumption fact, and rebuilds the runtime view. Snapshot+suffix replay
must produce a state identical to strict replay (invariant I-008) or it is discarded.

**中文**

| 类别 | 例子 | 可变性 | 恢复中的角色 |
|---|---|---|---|
| 可变权威 | `control/head.json` | 仅条件替换 | 恢复唯一信任的对象 |
| 协调提示 | `control/lease.json` | 条件替换 | 仅关乎活性；永不授予权威 |
| 不可变已提交对象 | commit、frontier、params、outer state、proposal、membership、snapshot | 一次创建、内容寻址 | head 可达 ⇒ 属于状态 |
| prepared / 孤儿对象 | FWO、input bundle、PFR、CAS 落败尝试 | 不可变 | 除非被已提交链引用，否则忽略 |
| 派生 / 观测数据 | `latest.json`、`stop.json`、heartbeat、checkpoint、CSV/JSONL/W&B、telemetry | 可重写 | 恢复从不读取 |

恢复是对 head 可达已提交前缀的一次 *fold*：strict replay 从校验过的 head 沿 parent 链回溯到
genesis，检查每个 manifest、digest、因果规则、权重与消费事实，重建运行时视图。snapshot+suffix
replay 的结果必须与 strict replay 完全一致（不变量 I-008），否则被丢弃。

## Fencing & why stale owners cannot write / 围栏机制：为何旧 owner 无法写入

**EN** — Safety is layered:

1. The storage backend gives each envelope a random opaque version; `conditional_replace`
   succeeds only against the expected version (ABA-safe), with request-ID-based idempotency for
   lost responses (`fs_diloco/storage/posix.py`).
2. A takeover must first wait until `lease.expires_at + max_clock_skew` (so the old owner's
   in-flight window has provably ended), then commit an **epoch-bump** control transition. That
   commit changes the head version.
3. Any CAS the stale owner attempts afterwards carries the *old* expected head version and is
   rejected by (1). The lease itself never decides anything about optimizer state.

**中文** — 安全性分层实现：

1. 存储后端给每个 envelope 一个随机不透明版本号；`conditional_replace` 只在期望版本匹配时成功
  （防 ABA），并用 request ID 处理响应丢失的幂等重试（`fs_diloco/storage/posix.py`）。
2. 接管者必须先等到 `lease.expires_at + max_clock_skew`（确保旧 owner 的在途窗口已结束），然后
   提交一次 **epoch-bump** 控制事务。该提交会改变 head 版本。
3. 旧 owner 之后的任何 CAS 携带的都是*旧的*期望 head 版本，会被第 1 层拒绝。lease 本身从不对
   optimizer 状态做任何裁决。

## Generations, membership, ownership / 世代、成员关系、所有权

**EN** — A *run generation* freezes an immutable `RunSpec`: codec, numeric mode, optimizer
config, parameter/fragment layout digests, coordination protocol, revision-zero membership,
replication factor, and execution-backend digest. Schema-incompatible changes require a new
generation (explicit warm start; no inherited consumption or session state). *Membership* is a
committed transition (revision N → N+1); fragment→owner assignment is derived deterministically
from membership by rendezvous hashing (`distributed_syncer/ownership.py`), so every node
computes the same ownership map with no extra communication. FWO identity binds parent commit,
selection, weights, membership revision, ownership digest, and fencing epoch — a prepared result
can never be replayed against a different owner or membership.

**中文** — *run generation* 冻结一份不可变 `RunSpec`：codec、数值模式、优化器配置、参数/
fragment 布局 digest、协调协议、revision-zero membership、复制因子与执行后端 digest。schema
不兼容的变更必须开新 generation（显式 warm start；不继承消费状态或 session）。*membership*
是已提交事务（revision N → N+1）；fragment→owner 的分配用 rendezvous 哈希从 membership 确定性
推导（`distributed_syncer/ownership.py`），因此所有节点无需额外通信即可算出同一张所有权表。
FWO 的 identity 同时绑定 parent commit、selection、权重、membership revision、ownership
digest 与 fencing epoch —— prepared result 不可能被挪用到不同 owner 或不同 membership 上。

## Legacy paths / 遗留路径

**EN** — `fs_diloco/syncer.py` (the earlier central syncer loop) and several helper workers
(`log/m00_miyabi_worker.py`, `coordination/miyabi_worker.py`, …) remain as reference/smoke
paths and shared helper libraries; the distributed committer imports its lease and
generation-management helpers from `syncer.py`. They are not the qualified 8-node topology and
must not generate new recovery or performance claims.

**中文** — `fs_diloco/syncer.py`（早期中心式 syncer 循环）与若干 helper worker
（`log/m00_miyabi_worker.py`、`coordination/miyabi_worker.py` 等）作为 reference/smoke 路径和
公共辅助库保留；分布式 committer 从 `syncer.py` 导入 lease 与 generation 管理辅助函数。它们
不是经过资格验证的 8 节点拓扑，不得产生新的恢复或性能主张。
