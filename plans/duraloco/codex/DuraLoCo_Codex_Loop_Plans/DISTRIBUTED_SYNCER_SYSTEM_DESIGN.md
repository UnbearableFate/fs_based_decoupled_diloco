---
title: "DuraLoCo Distributed Syncer System Design"
version: "1.1"
date: "2026-07-11"
status: "normative for P06A+"
---

# DuraLoCo Distributed Syncer System Design

## 1. Purpose

本文件定义 P06 之后从 dedicated central syncer 迁移到 learner-hosted distributed syncer 的规范语义。它不删除 syncer 的逻辑职责，而是把职责分为：

- **data plane**：proposal validation、fragment aggregation、outer optimizer、prepared output publication；
- **control/authority plane**：membership/ownership、work-order planning、winner validation、final transition commit、head CAS、authoritative stop。

Data plane 分散到 learner 节点 CPU。Control plane 由任一 learner host 上的短期 Floating Committer 执行，但其 authority 只来自 P05 lease/fencing 和共享存储 head CAS。

### 1.1 当前仓库边界

P06 archive commit `06e3ca2`已经提供`ProposalCatalog`、`RuntimeView`、
`ProductionTransactionalLog`、`outer_optim`、reference adapter、fragment/parameter index和
storage contract。P06A/P06B必须复用这些边界。当前`head-fenced-v1` run generation没有
membership/FWO/PFT字段，因此distributed prepare从新run generation与新coordination
protocol开始；不得把未知control transition原地写入P06 generation。

## 2. Terminology

- **CRS — Central Reference Syncer**：P05/P06 中心式实现，P06A 后作为 oracle、baseline 和 fallback。
- **LFE — Learner-Hosted Fragment Executor**：运行在 learner 节点 CPU 上，只执行 prepare 的进程/sidecar。
- **Floating Committer**：可以在 learner hosts 间迁移的、持有短期 fenced commit lease 的 planner/committer。
- **Membership Revision**：新distributed generation中committed active executor candidates 与 session identities 的版本。它与P05 fencing epoch是两个不同概念；前者决定eligible executors，后者fence唯一committer。
- **Ownership Map**：由 membership epoch、fragment ID、replication factor 和确定性 hash 算法派生并记录 digest 的 owner 集合。
- **FWO — Fragment Work Order**：固定 parent、fragment、selected proposal IDs/weights 和 policy identities 的 immutable deterministic execution request。
- **PFT — Prepared Fragment Transition**：LFE 对 FWO 的不可变计算结果；不是 authority。
- **Final Transition**：committer 验证 winner PFT 后生成的 committed optimizer transition。
- **D8/D8-R2**：八 learner 节点的无专用 syncer拓扑，后者 replication factor 2。

LFE的prepare-only是非Byzantine crash/omission模型下的software capability boundary：其
production entrypoint只注入immutable read/write facade，不注入head key、lease manager或
`conditional_replace`。因为Miyabi进程通常共享同一Unix账号，这不是抵抗恶意代码的OS
sandbox；静态audit只能防止实现误接线，不能扩大安全主张。

## 3. Authority model

系统始终保持一个 global committed history：

```text
head_v → transition_v → transition_v-1 → ... → genesis
```

每个 transition 可以包含一个 fragment update，也可以在 P08 以后包含一个经过 serial-equivalence 验证的 fragment bundle。只有 head CAS 成功后，transition 及其引用的 parameter/outer-state objects 才是 authoritative。

FWO 和 PFT 的目的分别是固定输入与保存可替换执行结果。它们允许在不改变 committed history 的情况下重试、并行和容错。

## 4. Object model

### 4.1 Proposal

P06 proposal 至少绑定：

```text
run_generation
learner_session_id
sequence
base_frontier_digest
fragment_id
local_interval_start/end
processed_token_count
payload_object_ref + digest
implementation/numeric identities
```

Proposal immutable、marker-last、request-ID idempotent。Listing 只负责发现；是否被选择由 deterministic policy 和 committed parent 决定。

### 4.2 MembershipControlTransition

记录：

```text
epoch
previous_epoch
candidate learner/executor session IDs
eligibility and capability digests
replication_factor
ownership_algorithm/version
activation_reason
```

Heartbeat 只提出 evidence。只有 committed MembershipControlTransition 改变 owner eligibility。

### 4.3 Fragment Work Order

FWO identity 由 canonical content 计算。所有浮点权重使用规范化后的`float.hex`字符串，
不得把JSON decimal float直接放入identity：

```text
work_order_id = H(
  run_generation,
  parent_head,
  parent_frontier_digest,
  fragment_id or ordered bundle,
  membership_revision,
  ownership_digest,
  selected proposal IDs and weights,
  aggregation/outer-optimizer policy identity,
  dtype/layout/implementation identity
)
```

FWO 必须完整到使 CRS 和所有 LFE 无需重新做 policy decision 即可得到同一结果。任何使用 local wall clock、directory enumeration order 或 process-specific random seed 的字段都禁止进入执行语义。

### 4.4 Prepared Fragment Transition

PFT分成两层：canonical prepared result和attempt envelope。canonical result至少包含：

```text
work_order_id
parent_head
validated input digests
aggregate digest
new parameter object ref + digest
new outer-state object ref + digest
numeric/implementation digest
```

attempt envelope另外记录`executor_id`、`executor_session_id`、`attempt_id`、membership
revision、resource/latency evidence refs和publication marker。canonical result identity排除
这些observational/arrival字段。同一FWO的等价attempt必须得到相同result digest和content
refs。PFT本身不消费proposal、不前进frontier、不授权adoption。

### 4.5 Final Transition

Final transition 引用 FWO 和 canonical prepared result，并记录：

```text
parent_head
work_order_id
prepared_result_digest
selected proposals and logical consumption facts
parameter + outer-state pair
new frontier/scheduler cursor
epoch/fencing token
stop/control facts if any
```

Committer 使用existing one-CAS transaction protocol将它线性化。Final transition identity
不得绑定first-finish、winner executor/attempt、telemetry或listing order；attempt/loser
lineage是审计evidence，不是optimizer state identity。

### 4.6 Numeric identity and equivalence

- 同一FWO必须冻结device/backend、Torch/BLAS实现、dtype、thread/reduction order；
- same-FWO redundant attempts必须使用相同backend并产生相同content/result digest，任何
  divergence在真实run中fail closed；
- current CRS使用GPU，而目标LFE默认使用CPU。跨CPU/GPU比较不要求虚假的bitwise/content
  digest相等；必须保留双方content digest，并按预注册`atol/rtol`产生numeric comparison
  report；
- 如需跨拓扑exact digest comparison，必须让offline CRS使用与LFE完全相同的execution
  backend identity。

## 5. Role placement

```text
Learner node i
├── GPU learner process
├── LFE_i (CPU, bounded cores/RSS/I/O)
└── committer candidate client

Shared filesystem
├── committed log/head
├── proposals
├── membership/ownership controls
├── work orders
├── prepared transitions
├── parameter + outer-state objects
└── snapshots/capsules/telemetry
```

CRS 运行在专用节点仅用于 C9 reference/baseline，或用户显式 fallback。Distributed production run 中 CRS 不得同时写同 generation。

## 6. Normal protocol

1. Learners 从 committed frontier 开始 non-overlapping intervals 并发布 proposals。
2. 当前 Floating Committer strict-replays head，读取 committed membership revision与自身fencing epoch。
3. Committer 使用 shared deterministic selector 选择 fragment、quorum、weights，发布 FWO。
4. Ownership map 指定 primary 和可选 backup/hedge LFE。
5. LFE 验证 FWO、parent 和 inputs，streaming reduce，执行 pure outer step，marker-last 发布 PFT。
6. Committer 验证 PFT capability、membership revision、fencing context、parent、input/output digests 和 duplicate consistency。
7. Committer选择合法canonical result，创建不依赖attempt arrival的final transition，并执行fenced head CAS。
8. Learners只从 committed frontier/boundary adopt；PFT never directly adopted。
9. Loser PFT 进入可解释 grace/reachability，随后由 P07R GC。

## 7. Deployment migration

### P06：freeze semantics

保持 dedicated central syncer并完成learner protocol。当前仓库P06-A01–A20已经PASS；完整
CRS characterization trace不是P06历史gate，由P06A从archive tip补建。

### P06A：decomposition without topology change

把 current syncer 拆为 pure kernels 与 orchestration adapters。所有 production calls 仍从 CRS 发起；要求 old-vs-decomposed bitwise/semantic equivalence。

### P06B：distributed prepare, replication factor 1

以新distributed run generation在learner hosts启动LFEs；Floating Committer也位于learner
host。保留single global head，默认同一时刻最多一个active FWO，先证明D8无专用syncer
正确运行。CRS只shadow或离线复算，P06 generation保持只读。

为避免“先有membership才能选committer、先有committer才能提交membership”的循环，
operator/launcher在初始化前生成logical member/session IDs；原子genesis把revision-0
membership/capability digests与run spec一起冻结。只有该集合中的candidate可竞争P05 lease
并提交首个committer fencing epoch bump；之后的membership变化才走committed control
transition。

### P06C：redundancy and failover

committed ownership map 使用 replication factor ≥2。primary 正常执行；backup warm-standby 或在 hedge delay 后执行。节点 loss 触发 committed reconfiguration。重复计算不增加 logical proposal inclusion。

### P08：bounded concurrency/bundling

只有在 P06C safety 稳定后，才允许多个 independent PFT concurrently prepare。最终仍通过 single CAS serial commit；可选 `CommitBundlePlan` 必须证明与 canonical serial order 等价。

## 8. Ownership algorithm

建议使用 rendezvous hashing：

```text
score(fragment, member, membership_revision) = H(run_generation, membership_revision, fragment, member_session)
owners(fragment) = top_r(score)
```

但算法版本、tie-break、candidate ordering 和 replication factor 必须进入 committed control transition。不同节点只要看到同一 membership revision 就必须得到同一 ownership digest。

Owner 是执行责任而不是状态所有权。Owner change 不迁移 optimizer state；新 owner 读取 committed parent 和 immutable inputs。

## 9. Safety properties

1. **Single authority**：只有 current head 可达 prefix。
2. **Paired state**：parameter fragment 与 outer state 同 transition。
3. **At-most-one logical commit per work order**：CAS 和 parent check 保证。
4. **At-most-one logical proposal inclusion**：consumption facts 在 committed ancestry 中验证。
5. **At-least-once execution allowed**：PFT 可重复。
6. **Deterministic duplicates**：同 FWO 的 semantic digest 必须一致。
7. **Two-dimensional fencing**：stale membership/ownership result不能被采用，stale committer fencing epoch不能commit；两者不可混为一个epoch。
8. **No local authority**：删除所有 local state 后可恢复。
9. **Boundary adoption**：learner 不读取 uncommitted/PFT state。
10. **Committed reconfiguration**：heartbeat/listing 不能单独改变 owner。

## 10. Failure matrix

| Failure | Required behavior |
|---|---|
| primary LFE before PFT | backup/reassigned owner 重算；无 commit |
| primary after PFT before notify | committer通过 listing/reference发现并验证；或 backup生成同 digest |
| duplicate PFT same digest | 任选一个 object identity 作为 winner；其余为 loser evidence |
| duplicate PFT different digest | fatal determinism blocker；不得 commit |
| committer before FWO publication | new committer strict replay and re-plan with same deterministic selection |
| committer after FWO before final commit | new committer验证/reuse PFT，或重算 |
| committer after CAS before response | ancestry reconciliation；不得重复逻辑 commit |
| learner+LFE whole node failure | remaining learner持续；committed epoch change 后重assign |
| stale executor returns | membership revision/ownership validation rejects result；可只做丢弃/diagnostic |
| stale committer returns | P05 owner token/fencing epoch rejects head mutation |
| listing omission | 延迟 discovery，不证明 object/commit absent |
| partial object publication | marker-last keeps invisible；GC grace protects payload |
| head advances while prepare | PFT stale；committer rebase/replan，不把它套到新 parent |
| storage corruption | strict verification, quarantine, stop or safe fallback |

## 11. Concurrency policy

P06B首先选择safety-first模式：一个active parent/FWO，多个executor可以并行或冗余计算，
但final transitions严格串行。P08只有在profile gate触发且新schema/ADR通过时才可增加：

- bounded number of prepared FWOs based on same head；
- disjoint fragments；
- canonical bundle order；
- one-CAS bundle transition；
- conflict/cancellation and memory bounds。

未触发gate时bundle验收项以有Checker证据的`not_applicable`关闭。不允许在没有
serializability proof的情况下让多个independent heads同时成为authority。

## 12. Resource isolation

LFE 必须配置：CPU core set、thread count、NUMA policy、RSS budget、in-flight I/O、prefetch depth 和 process priority。默认以 GPU learner goodput 为优先，超预算时 backpressure 或延迟 hedge，而不是抢占 learner critical path。

## 13. Lifecycle

P07R reachability roots 至少包括：current head/prefix、latest safe snapshot、active FWO、合法 PFT winner candidates、loser grace window、membership epochs、learner capsules、pinned experiments 和 response-loss reconciliation records。Prepared output 不因“未 commit”立即删除。

## 14. Explicit non-goals

- 不声称没有逻辑协调；
- 不在必需主线实现 per-fragment heads；
- 不让 learner 直接写 head；
- 不把 local executor queue 作为 durable scheduler；
- 不在 P06B 同时更改 learner proposal semantics；
- 不用 payload equality 替代 request identity；
- 不把 warm recovery 误称 bitwise exact learner continuation。
