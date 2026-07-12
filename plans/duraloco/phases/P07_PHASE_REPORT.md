# P07 Milestone Report

## English

### Final status

- Phase: P07 — distributed lifecycle, compaction, reachability GC, acknowledgements, and exact learner capsules
- Branch: `codex/duraloco-p07-distributed-lifecycle`
- P06C basis: `6a528cbe26a9209720325ce031937c30d970b977`
- Verified P06C runtime dependency: `cba9f487dcc697a6df7930b22280e4f0d512377b`
- Qualified P07 lifecycle runtime: `2295467fd25ae7969eb2b993ef4b193141239286`
- Verified P07 implementation/Checker commit: `c099adc3c3a99127569a7d9bf38a58547022173c`
- Acceptance: P07-A01 through P07-A24 pass
- Checker: PBS `2369002.opbs`, `PASS`, no required-gate follow-up
- Current status: `completed`

P07 completes the lifecycle layer for the dedicated-syncer-free D8-R2 topology.
The committed transition log plus its single global head CAS remains the only
persistent optimizer authority. Snapshots, capsules, acknowledgements, GC marks,
telemetry, and reports are immutable derived or observational objects; none can
advance the optimizer trajectory independently.

### Implemented lifecycle contract

Snapshots are immutable side objects. A snapshot becomes replay-eligible only
when a fenced `snapshot_pin` control transition binds it into committed ancestry.
Replay validates the snapshot identity, covered commit, covered state digest,
and suffix. Missing, corrupt, stale, unpinned, or non-ancestral snapshots are
ignored and recovery starts with empty-cache strict replay. The active retention
window keeps two independently validated snapshot bases so corruption of the
newest compacted base does not destroy the recovery path.

Reachability is a typed `ObjectRef` graph with explicit root and edge reasons.
It accounts for the committed head/prefix, fencing epoch, membership and
ownership, active FWO, committed PFR, equivalent loser grace, divergent blocker
evidence, response-loss records, exact capsules, snapshot pins, acknowledgements,
quarantine, and experiment/restore pins. Directory listing is discovery only;
unknown future-schema objects fail closed into quarantine.

GC is an immutable mark followed by a separately authorized, revalidated apply.
The real D8 namespace remains dry-run. Apply is exposed only for guarded
`synthetic-*` namespaces, binds the approval token to the mark and namespace,
strict-replays current authority, rebuilds reachability, and rejects head,
epoch, identity, or liveness changes. Delete request identity makes response
loss and partial batches idempotently recoverable. Payloads and envelopes are
removed before their publication markers.

Exact learner capsules publish complete model/frontier, inner optimizer,
scheduler/scaler, CPU/CUDA/Python RNG, restorable data-source cursor, and
interval state, with the marker last. Exact restore requires every component
and a matching backend/device/RNG topology, then starts a new learner session.
Missing private, RNG, data, scheduler, or scaler state fails the exact claim;
warm recovery remains a separate explicitly labelled path.

### Qualification ladder

Focused one-node evidence established each subgate: snapshot fallback and
pinning (`2365797`, `2365809`), reachability and unknown-object protection
(`2365820`), guarded GC and response-loss reconciliation (`2365833`), exact
capsules (`2365848`), and the separate default-dry-run lifecycle CLI (`2365856`).
Real GPT-2 D1-R2 PBS `2366149.opbs` passed snapshot, capsule, reachability, and
GC dry-run integration.

After the long-substage lease repair, targeted PBS `2368753.opbs`, full one-node
PBS `2368758.opbs` (75 tests), and D2-R2 PBS `2368760.opbs` passed in order on
commit `2295467`. D2 covered executor loss, committer takeover, whole-host loss,
snapshot/capsule integration, owner reassignment, and GC dry-run without a
dedicated syncer.

The D8-R2 authority from PBS `2368771.opbs` used eight learner nodes, eight
learners, eight LFEs, two learner-hosted committer candidates, replication
factor two, and zero dedicated syncer nodes. It completed GPT-2/WikiText-2
50×10, ten optimizer transitions, five snapshot/GC lifecycle cycles, five
ancestry snapshot pins, one exact capsule for each learner, an executor-process
fault, a whole learner-host fault, membership revision one, and authoritative
stop. The longest fault recovery was 91.602 seconds.

The job wrapper reported failure only after the valid authority completed,
because its inherited report envelope was fixed at 900 seconds while the
lifecycle-enabled run took 1100 seconds. The authority and raw telemetry were
preserved. Report-recovery PBS `2368976.opbs` applied an explicit runtime
envelope, validated the factor-one evidence schema, and produced PASS runtime
and P07 lifecycle reports. This is a reporting-workflow failure followed by a
successful evidence recovery, not a failed optimizer run.

### Bounded-growth and lifecycle results

The five lifecycle samples were:

| Head seq | Inventory objects | Candidates | Effective live | Lifecycle seconds |
|---:|---:|---:|---:|---:|
| 4 | 150 | 0 | 150 | 45.58 |
| 9 | 262 | 66 | 196 | 69.09 |
| 12 | 348 | 128 | 220 | 93.34 |
| 15 | 434 | 186 | 248 | 118.57 |
| 18 | 520 | 244 | 276 | 141.89 |

Because real-namespace GC is intentionally dry-run, raw inventory grows while
reclaimable candidates accumulate. The preregistered claim concerns the
effective live window after eligible collection. Its last-three-sample delta is
`276 - 220 = 56`, below the limit of 64. At terminal state the report records
245 candidates, eight retained capsule markers, eight protected unknown objects,
snapshot-plus-suffix equality with strict replay, and zero destructive applies.

P07 therefore establishes a bounded, explainable active lifecycle window; it
does not claim that a real dry-run-only namespace physically stops growing.
Lifecycle latency itself grows with the current Python prototype's graph and
snapshot audit work (45.58 to 141.89 seconds), which is an explicit performance
input to P08 rather than a hidden success condition.

### Failure history and resolution

Earlier D8 attempts `2366037`, `2366101`, `2366167`, and `2366236` exposed that
increasing replay/reachability substages could cross the lease TTL. Each failure
preserved a safe committed prefix and was reviewed before the next qualification
cycle. The final repair runs each long substage in a worker while the owner
control thread renews the lease. Renewal failure, expiry, ownership change, or
substage failure prevents the result from being used. This resolved
`B-P07-20260712-01`; it did not weaken fencing or add a second authority.

The independent Checker then passed all 24 acceptance IDs and four private
counterexamples. P07 may hand P08 the frozen `ObjectRef` reachability extension,
two-snapshot retention, exact-capsule, immutable mark/apply, marker-last deletion,
and owner-heartbeat interfaces. P08 must preserve all P07 regressions. P07
completion does not authorize merging `main`.

## 中文

### 最终状态

- 阶段：P07 — distributed lifecycle、compaction、reachability GC、ack 与 exact learner capsule
- 分支：`codex/duraloco-p07-distributed-lifecycle`
- P06C 基线：`6a528cbe26a9209720325ce031937c30d970b977`
- 已验证 P06C runtime dependency：`cba9f487dcc697a6df7930b22280e4f0d512377b`
- 通过 qualification 的 P07 lifecycle runtime：`2295467fd25ae7969eb2b993ef4b193141239286`
- 已验证 P07 implementation/Checker commit：`c099adc3c3a99127569a7d9bf38a58547022173c`
- 验收：P07-A01 至 P07-A24 全部通过
- Checker：PBS `2369002.opbs`，`PASS`，无 required-gate follow-up
- 当前状态：`completed`

P07 为没有 dedicated syncer 的 D8-R2 拓扑补齐 lifecycle 层。committed transition log 与
唯一 global head CAS 仍是唯一持久 optimizer authority。snapshot、capsule、ack、GC mark、
telemetry 与报告均为 immutable derived/observational object，不能独立推进 optimizer trajectory。

### 已实现 lifecycle 合同

snapshot 是 immutable side object。只有 fenced `snapshot_pin` control transition 把它绑定
到 committed ancestry 后，它才可用于 replay。replay 会验证 snapshot identity、covered
commit、covered state digest 与 suffix。snapshot 缺失、损坏、过期、未 pin 或不在 ancestry
时，系统忽略它并从 empty-cache strict replay 开始。active retention window 保留两个独立
验证的 snapshot base，因此最新 compacted base 损坏不会破坏恢复路径。

reachability 是带明确 root/edge reason 的 typed `ObjectRef` graph，覆盖 committed head/prefix、
fencing epoch、membership/ownership、active FWO、committed PFR、equivalent loser grace、
divergent blocker evidence、response-loss record、exact capsule、snapshot pin、ack、quarantine 与
experiment/restore pin。目录 listing 只用于 discovery；未知 future-schema object 默认 fail
closed 并进入 quarantine。

GC 由 immutable mark 与单独授权、重新验证的 apply 组成。真实 D8 namespace 始终 dry-run。
apply 只对受 guard 的 `synthetic-*` namespace 开放，把 approval token 与 mark/namespace 绑定，
strict replay 当前 authority，重建 reachability，并在 head、epoch、identity 或 liveness 改变时
拒绝执行。delete request identity 使 response loss 与 partial batch 可幂等恢复。删除顺序为先
payload/envelope，最后 publication marker。

exact learner capsule 以 marker-last 顺序发布完整 model/frontier、inner optimizer、
scheduler/scaler、CPU/CUDA/Python RNG、可恢复 data-source cursor 与 interval state。exact restore
要求所有 component 以及匹配的 backend/device/RNG topology，并建立新 learner session。缺少
private、RNG、data、scheduler 或 scaler state 时 exact claim 必须失败；warm recovery 是单独且
明确标记的路径。

### Qualification 阶梯

focused 单节点证据依次完成各子门：snapshot fallback/pin（`2365797`、`2365809`）、
reachability 与 unknown-object protection（`2365820`）、guarded GC 与 response-loss
reconciliation（`2365833`）、exact capsule（`2365848`），以及独立、默认 dry-run 的 lifecycle
CLI（`2365856`）。真实 GPT-2 D1-R2 PBS `2366149.opbs` 通过 snapshot、capsule、reachability
与 GC dry-run 集成。

修复 long-substage lease 后，targeted PBS `2368753.opbs`、完整单节点 PBS `2368758.opbs`
（75 项测试）与 D2-R2 PBS `2368760.opbs` 在同一 `2295467` commit 上依次通过。D2 覆盖
executor loss、committer takeover、whole-host loss、snapshot/capsule 集成、owner reassignment
与 GC dry-run，且没有 dedicated syncer。

D8-R2 权威运行 PBS `2368771.opbs` 使用八个 learner node、八个 learner、八个 LFE、两个
learner-hosted committer candidate、replication factor 2 与零 dedicated syncer node。它完成
GPT-2/WikiText-2 50×10、十次 optimizer transition、五个 snapshot/GC lifecycle cycle、五个
ancestry snapshot pin、每个 learner 一个 exact capsule、一次 executor-process fault、一次完整
learner-host fault、membership revision 1 与 authoritative stop。最大 fault recovery 为 91.602 秒。

有效 authority 完成后，job wrapper 才因旧 report envelope 固定为 900 秒而报告失败；带 lifecycle
的运行实际耗时 1100 秒。authority 与 raw telemetry 均已保留。report-recovery PBS
`2368976.opbs` 使用显式 runtime envelope，验证 factor-one evidence schema，并生成 PASS 的
runtime/P07 lifecycle 报告。因此这是 reporting workflow failure 后成功恢复证据，不是 optimizer
运行失败。

### Bounded-growth 与 lifecycle 结果

五个 lifecycle sample 为：

| Head seq | Inventory object | Candidate | Effective live | Lifecycle 秒 |
|---:|---:|---:|---:|---:|
| 4 | 150 | 0 | 150 | 45.58 |
| 9 | 262 | 66 | 196 | 69.09 |
| 12 | 348 | 128 | 220 | 93.34 |
| 15 | 434 | 186 | 248 | 118.57 |
| 18 | 520 | 244 | 276 | 141.89 |

真实 namespace 的 GC 按设计仅 dry-run，因此 raw inventory 会在积累可回收 candidate 时继续增长。
预注册主张针对 eligible collection 后的 effective-live window；最后三个 sample 的增量为
`276 - 220 = 56`，小于上限 64。terminal report 记录 245 个 candidate、八个保留 capsule
marker、八个 protected unknown object、snapshot+suffix 与 strict replay 相等，以及零次
destructive apply。

因此 P07 证明的是有界且可解释的 active lifecycle window，而不是声称真实 dry-run-only
namespace 的物理容量停止增长。当前 Python prototype 的 lifecycle latency 会随 graph/snapshot
audit 工作增长（45.58 秒至 141.89 秒）；这是交给 P08 的明确 performance input，不是被隐藏的
成功条件。

### 失败历史与解决

早期 D8 attempt `2366037`、`2366101`、`2366167` 与 `2366236` 暴露不断增长的
replay/reachability substage 可能跨越 lease TTL。每次失败都保留安全 committed prefix，并在
下一轮 qualification 前完成 review。最终修复把 long substage 放入 worker，同时由 owner control
thread 续租；续租失败、过期、ownership 改变或 substage 失败都会阻止结果被使用。该修复解决
`B-P07-20260712-01`，没有削弱 fencing，也没有增加第二 authority。

独立 Checker 随后通过全部 24 项验收与四个私有反例。P07 交给 P08 的冻结接口包括 typed
`ObjectRef` reachability extension、two-snapshot retention、exact capsule、immutable mark/apply、
marker-last deletion 与 owner-heartbeat。P08 必须保留全部 P07 regression。P07 完成不授权合并
`main`。
