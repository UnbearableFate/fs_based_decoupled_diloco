# Data Flow / 数据流

## Storage namespace / 存储命名空间

**EN** — Everything lives under one shared root. The authoritative namespace (simplified):

```text
<shared-root>/
  authority/runs/<run-id>/generations/<gen>/
    control/head.json                 ← the ONLY mutable authority (CAS)
    control/lease.json                ← coordination hint (conditional replace)
    manifest.json                     ← immutable RunSpec / run manifest
    commits/<seq>-<commit-id>.json    ← immutable commit manifests
    frontiers/<seq>-<digest>.json     ← immutable frontier manifests
    params/<fragment>/<digest>.safetensors
    outer/<fragment>/<digest>.safetensors
    proposals/<proposal-id>.json      ← proposal manifests
    payloads/<sha256>.safetensors     ← proposal payloads (content-addressed)
    membership/<rev>-<digest>.json
    snapshots/<snapshot-id>.json
    distributed/                      ← FWO, input bundles, PFR markers+payloads
    .duraloco-locks/                  ← reserved advisory-lock inodes
  latest.json, stop.json, heartbeats/, updates_pending/, logs/, metrics/   ← derived
```

Every file in `authority/` is a checksummed envelope; keys are canonical relative POSIX paths
validated before any I/O. Directory listing is used only for discovery and GC inventory, never
to decide committed state.

**中文** — 所有数据位于同一共享根之下。权威命名空间（简化）见上图。`authority/` 下每个文件
都是带校验和的 envelope；key 是在任何 I/O 前经过校验的 canonical 相对 POSIX 路径。目录列举
只用于发现与 GC 盘点，绝不用于裁定已提交状态。

## One optimizer transition, end to end / 一次 optimizer transition 的完整旅程

**EN**

```text
 (1) Learner: adopt committed fragments from derived views (latest.json → weight files)
 (2) Learner: train inner_steps locally  →  ContributionInterval closes
 (3) Learner: publish proposal            payload (bf16 safetensors) first,
                                          manifest (canonical JSON) last
 (4) Committer: catalog scan              cheap metadata rejection → full validation
                                          (schema, lineage, causal base, staleness,
                                           ObjectRef, safetensors, finite values)
 (5) Committer: freeze selection          frozen policy oldest_pending, ≤1 proposal
                                          per learner, canonical token/staleness weights
 (6) Committer: publish FWO + input bundle  (binds parent commit, frontier digest,
                                          selection, weights, membership revision,
                                          ownership, fencing epoch, backend digest)
 (7) LFE: verified reads of params/outer/proposal payloads
          ordered streaming weighted reduction  →  outer optimizer step
 (8) LFE: publish PFR                     new params/outer payloads first,
                                          result manifest + attempt envelope,
                                          marker last
 (9) Committer: wait for required attempts, decide duplicates (identity-equal or block)
(10) Committer: re-validate winner        aggregate digest, backend digest,
                                          decode + size checks of params/outer bytes
(11) Committer: prepare                   put params, outer, commit, frontier
                                          as immutable authority objects
(12) Committer: HEAD CAS                  expected version + unique request ID
(13) Committer: post-CAS replay           rebuild RuntimeView from authority
(14) Committer: materialize derived views fragment weight files + latest.json
 (…) Learners poll latest.json and adopt at their next interval boundary
```

Steps 1–3 run concurrently on all 8 learners; steps 4–14 are serialized in the single active
committer. If the CAS fails (conflict/ambiguity), the committer discards its tentative state,
force-full replays, and re-enters at step 4 — a prepared transition is never retargeted to a
new parent.

**中文** — 步骤如上图：(1) learner 从派生视图采用已提交 fragment；(2) 本地训练
`inner_steps` 步，关闭 ContributionInterval；(3) 发布 proposal（payload 先、manifest 后）；
(4) committer 扫描 catalog（先廉价元数据过滤，再全量验证：schema、lineage、因果 base、
staleness、ObjectRef、safetensors、有限值）；(5) 按冻结策略 `oldest_pending` 定格 selection
（每 learner 至多一条），计算 canonical token/staleness 权重；(6) 发布 FWO 与 input bundle
（绑定 parent commit、frontier digest、selection、权重、membership revision、ownership、
fencing epoch、backend digest）；(7) LFE 校验读取 params/outer/proposal payload，做有序流式
加权归约与 outer optimizer 步骤；(8) 发布 PFR（payload 先、marker 最后）；(9) committer 等待
所需 attempt 数并做重复裁决（identity 相等或阻断）；(10) 重新验证获胜结果；(11) 把
params/outer/commit/frontier 作为不可变权威对象写入；(12) 执行 head CAS（期望版本 + 唯一
request ID）；(13) CAS 后从权威重建 RuntimeView；(14) 物化派生视图。1–3 在 8 个 learner 上
并发；4–14 在唯一 active committer 内串行。CAS 失败时丢弃暂态、强制全量 replay、回到第 4 步
—— prepared transition 绝不改挂到新 parent 上。

## What each committed object contains / 每个已提交对象包含什么

**EN**

| Object | Key contents | Identity binds |
|---|---|---|
| Commit | selected proposals + weights, staleness, aggregate digest, optimizer impl digest, new params/outer ObjectRefs, parent commit id + logical parent-head token, fencing epoch, owner/request identity, work-order/prepared-result ids | the full decision |
| Frontier | per-fragment `(version, params_ref, outer_ref, producing_commit)`, scheduler cursor, consumed-proposal set, coordination projection (owner, transition count, stop), membership projection | the full resulting state |
| Head | run identity, fencing epoch, commit seq/id, frontier ObjectRef | the current tip |
| Control commit | epoch_bump / stop / resume / membership / snapshot_pin request + digest | authority changes that are not optimizer steps |

Params fragments and outer-optimizer state are always produced by the same commit and paired in
the frontier (invariant I-005), so recovery can never mix a parameter version with a foreign
optimizer state.

**中文** — Commit 记录完整决策（选中的 proposal 与权重、staleness、聚合 digest、优化器实现
digest、新 params/outer ObjectRef、parent commit 与逻辑 parent-head token、fencing epoch、
owner/request identity、work-order/prepared-result id）；Frontier 记录完整结果状态（每
fragment 的版本与引用、调度游标、已消费 proposal 集、协调投影、membership 投影）；Head 只记
当前尖端；Control commit 承载非 optimizer 的权威变更。params 与 outer state 必须由同一
commit 产生并在 frontier 中配对（不变量 I-005），恢复不可能把参数版本和别的优化器状态混配。

## Recovery data flow / 恢复数据流

**EN**

```text
verified head ──► frontier chain walk (head → genesis, parent digests)
              ──► per-commit checks: sequence contiguity, parent-head token,
                  selection canonicality, causal base + staleness, lineage
                  monotonicity, weight recomputation, consumption-set equality,
                  scheduler-cursor recurrence, fencing/coordination projection
              ──► verified payload reads (proposals, params, outer) with
                  finite-value validation; process-local memoization allowed
                  only after a complete successful replay in the same
                  process/owner scope
              ──► ReplayResult { frontiers, commits, proposals, consumption,
                  lineage watermarks, reachable keys, committed state digest }
```

Boundaries that force an empty-cache full replay: fresh open, owner takeover, explicit verify,
CAS ambiguity, an externally observed head jump, and any corruption suspicion. Snapshot+suffix
replay loads the newest committed-and-pinned snapshot, verifies it, replays only the suffix, and
must equal strict replay exactly.

**中文** — 从校验过的 head 沿 parent digest 链走到 genesis；对每个 commit 检查序列连续性、
parent-head token、selection 规范性、因果 base 与 staleness、lineage 单调性、权重重算、消费
集相等、调度游标递推、fencing/协调投影；对 proposal/params/outer 做校验读取与有限值验证
（进程内记忆化只允许在同进程、同 owner 范围内一次完整成功 replay 之后使用）；产出
`ReplayResult`。以下边界强制空缓存全量 replay：fresh open、owner 接管、显式 verify、CAS
歧义、外部 head 跳变、任何腐坏怀疑。snapshot+suffix replay 加载最新已提交并 pin 的
snapshot、验证后只重放后缀，结果必须与 strict replay 完全相等。

## Derived-view data flow / 派生视图数据流

**EN** — After each committed transition the committer writes per-fragment weight/optimizer
files and rewrites `latest.json` (atomic temp+rename). Learners poll `latest.json`, adopt only
at interval boundaries, and apply the configured inner-optimizer adoption policy. `stop.json` is
generated only after a committed stop/error control transition is observed. Heartbeats flow the
other way: learners write per-learner JSON heartbeats that the committer uses only for liveness
decisions (terminal drain, no-progress timeout) — never for authority.

**中文** — 每次提交后，committer 写每 fragment 的权重/优化器文件并重写 `latest.json`
（临时文件 + 原子 rename）。learner 轮询 `latest.json`，只在 interval 边界采用，并应用配置的
inner-optimizer 采用策略。`stop.json` 只在观察到已提交的 stop/error 控制事务后生成。
heartbeat 反向流动：learner 写各自的 JSON 心跳，committer 只将其用于活性决策（终局排空、
无进展超时）—— 绝不用于权威。
