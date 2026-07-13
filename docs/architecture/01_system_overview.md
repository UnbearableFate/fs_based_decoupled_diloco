# System Overview / 系统概览

## What this system is / 系统是什么

**EN** — This repository implements **DuraLoCo**: a filesystem-backed, decoupled variant of
DiLoCo (Distributed Low-Communication training). Multiple independent single-GPU *learners*
train a language model locally and periodically publish parameter *proposals*. A protocol built
entirely on a shared POSIX/Lustre filesystem — with no `torch.distributed`, NCCL, RPC, Ray, or
any message-passing runtime — validates those proposals, aggregates them with a deterministic
outer optimizer, and commits each global update as one durable, crash-recoverable transaction.

The defining idea: **one fragment merge + one outer-optimizer update + one recovery point are
the same persistent transaction**, and the only mutable authority in the whole system is a
single file updated by compare-and-swap:

```text
authority/runs/<run-id>/generations/<8-digit-generation>/control/head.json
```

Everything else — proposals, parameters, optimizer state, commits, frontiers, snapshots,
work orders, prepared results — is an immutable, content-verified object. Derived files
(`latest.json`, checkpoints, heartbeats, telemetry) are rebuildable views that can never change
what recovery computes.

**中文** — 本仓库实现 **DuraLoCo**：DiLoCo（低通信分布式训练）的文件系统解耦变体。多个独立的
单 GPU *learner* 在本地训练语言模型，并周期性发布参数 *proposal*。一个完全构建在共享
POSIX/Lustre 文件系统之上的协议（不使用 `torch.distributed`、NCCL、RPC、Ray 等任何消息传递
运行时）负责验证这些 proposal，用确定性 outer optimizer 聚合它们，并把每次全局更新作为一次
持久、可崩溃恢复的事务提交。

核心思想是：**一次 fragment 合并 + 一次 outer-optimizer 更新 + 一个恢复点是同一个持久事务**，
而整个系统唯一可变的权威只有一个通过 compare-and-swap 更新的文件（见上方路径）。其余一切 ——
proposal、参数、优化器状态、commit、frontier、snapshot、work order、prepared result —— 都是
不可变、内容可校验的对象。派生文件（`latest.json`、checkpoint、heartbeat、telemetry）只是可
重建的视图，永远不能改变恢复计算的结果。

## Why it is built this way / 为什么这样设计

**EN**

- **Environment fit.** The target is the Miyabi-G HPC cluster: PBS batch allocations, a shared
  Lustre filesystem, no long-lived services, and login nodes restricted to control-plane work.
  A filesystem is the only communication substrate that survives node churn there.
- **Failure model first.** Learner hosts, executors, and the committer may crash at any point;
  storage responses may be lost; listings may be delayed or reordered. The protocol therefore
  derives *exactly-once logical inclusion* of each proposal from canonical identity, marker-last
  publication, request IDs, strict replay, fencing epochs, and the single head CAS — it never
  assumes exactly-once delivery.
- **Auditability.** Every transition is deterministic given its committed inputs; an
  independent checker can re-derive the whole optimizer trajectory from the log alone.

**中文**

- **环境匹配。** 目标环境是 Miyabi-G 超算：PBS 批处理分配、共享 Lustre 文件系统、没有常驻
  服务、登录节点只允许控制面操作。在这种环境里，文件系统是唯一能跨节点存活的通信介质。
- **故障模型优先。** learner 主机、executor、committer 可能在任何时刻崩溃；存储响应可能丢失；
  目录列举可能延迟或乱序。协议通过 canonical identity、marker-last 发布、request ID、strict
  replay、fencing epoch 与唯一 head CAS 推导出每个 proposal 的"逻辑上恰好一次"纳入 —— 从不
  假设"恰好一次"投递。
- **可审计性。** 给定已提交输入，每个 transition 都是确定性的；独立 checker 仅凭日志即可重新
  推导完整的优化轨迹。

## Design principles / 设计原则

**EN**

1. **Single linearization point.** Only the head CAS commits state; anything written before a
   successful CAS is "prepare" or orphan.
2. **Immutability + content addressing.** Objects are identified by `(key, sha256, size)`;
   one identity maps to exactly one canonical body (invariant I-011).
3. **Fencing over trust.** A lease is only a coordination hint; ownership becomes real only
   when an epoch-bump control transition is committed into the head chain.
4. **Fail closed.** Ambiguity (CAS response loss, digest mismatch, divergent duplicate results,
   unknown objects) stops progress rather than guessing.
5. **Derived data is disposable.** Deleting `latest.json`, checkpoints, or telemetry can never
   change replay results.

**中文**

1. **唯一线性化点。** 只有 head CAS 才能提交状态；CAS 成功前写入的一切都只是 prepare 或孤儿
   对象。
2. **不可变 + 内容寻址。** 对象由 `(key, sha256, size)` 标识；一个 identity 只对应一个
   canonical body（不变量 I-011）。
3. **围栏而非信任。** lease 只是协调提示；只有当 epoch-bump 控制事务被提交进 head 链，所有权
   才真正生效。
4. **失败即关闭。** 任何歧义（CAS 响应丢失、digest 不符、重复结果分歧、未知对象）都会停止
   前进而不是猜测。
5. **派生数据可丢弃。** 删除 `latest.json`、checkpoint 或 telemetry 永远不会改变 replay 结果。

## Current status (at review time) / 当前状态（评审时）

**EN** — Phases M00–P08 are complete. The validated production topology is strict 8-node
D8/D8-R2: 8 GPU learners, 8 CPU learner-hosted fragment executors (LFE), two floating-committer
candidates, replication factor 1 or 2, no dedicated syncer node. The historical H0 experiment
(GPT-2 + WikiText-2, 50 local × 10 global steps) measured a worst-case
failure-to-next-commit recovery of 89.44 s under lease parameters TTL=45 s / renew=10 s /
skew=2 s. Current work (P08R) is a performance-recovery gate before P10; the accepted matched
comparison is factor-one 337.6 s vs R2 527.0 s for the full 8-node qualification experiment.

**中文** — M00–P08 阶段已完成。经验证的生产拓扑是严格 8 节点 D8/D8-R2：8 个 GPU learner、
8 个宿主在 learner 节点上的 CPU fragment executor（LFE）、两个 floating committer 候选，
复制因子 1 或 2，无专用 syncer 节点。历史 H0 实验（GPT-2 + WikiText-2，50 local × 10 global）
在 lease 参数 TTL=45s / renew=10s / skew=2s 下测得最坏"故障到下一次提交"恢复时间 89.44 秒。
当前工作（P08R）是 P10 之前的性能恢复门；被接受的匹配对比为 factor-one 337.6 秒 vs R2
527.0 秒（完整 8 节点资格实验）。

## What the system does NOT claim / 系统不承诺什么

**EN** — No Byzantine tolerance; no protection against malicious shared storage or operators
editing authority objects; no availability guarantee under arbitrary network partitions; no
bitwise numeric identity across different PyTorch/CUDA/CPU backends; no automatic exact
reintegration of a failed learner host (the committed response to whole-host loss is membership
removal). See `review/02_design_findings.md` for gaps that are *not* deliberate.

**中文** — 不承诺拜占庭容错；不防御恶意共享存储或手改权威对象的运维操作；不保证任意网络分区
下的可用性；不承诺跨不同 PyTorch/CUDA/CPU 后端的逐位数值一致；不承诺故障 learner 主机的自动
精确重入（对整机丢失的既定处置是 membership 移除）。非刻意留下的缺口见
`review/02_design_findings.md`。
