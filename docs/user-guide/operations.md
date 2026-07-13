# Miyabi 运行、恢复与故障处理

## 节点职责

| 环境 | 允许 | 禁止 |
|---|---|---|
| Login node | 编辑、`rg/git`、`bash -n`、静态 Python checker、`qsub/qstat`、日志读取 | 训练、模型/数据加载、torch/CUDA/transformers import、pytest runtime、MPI/torchrun |
| 1-node compute | unit/integration、真实 D1、targeted benchmark | 直接替代 2-node 锁/可见性证据 |
| 2-node compute | Lustre lock、CAS race、D2-R2 failover | 推断 8-node 性能/故障结果 |
| 8-node allocation | 8 learner/runtime host 的 D8/D8-R2 terminal experiment | 绕过前两级 qualification、增加第九节点 |

PBS 中 MPI 只负责在 host 上启动进程。环境通过 `/usr/bin/env` 显式传递，不依赖 MPI `-x`；训练
数据面本身不是 MPI collective。

## 当前分布式拓扑

D8-R2 的 allocation 严格为 8 个节点，全部承载 learner runtime：每个节点一张 learner
GPU、一个 CPU LFE；其中两个 learner host 还启动 eligible committer candidate。不存在专用
syncer、control/audit host、spare 或闲置第九节点；manifest 中 allocated/active host 集合必须相同。

committer CLI：

```bash
python -m fs_diloco.distributed_syncer.cli committer \
  --config <yaml> --run-id <id> --shared-root <root> --num-learners <n> \
  --node-ids <comma-separated-hosts> --member-id <member> \
  --owner-session-id <session> --replication-factor 2 \
  --execution-mode hedged --hedge-delay-ms 6000 \
  --lifecycle-cadence <n>
```

executor CLI：

```bash
python -m fs_diloco.distributed_syncer.cli executor \
  --config <yaml> --run-id <id> --shared-root <root> --num-learners <n> \
  --member-id <member> --executor-id <executor> \
  --executor-session-id <session> --threads <n> --max-rss-bytes <bytes>
```

实际实验优先使用 phase PBS wrapper；手工命令容易遗漏 topology manifest、commit cleanliness、
artifact checksum、failure schedule 和 acceptance gate。

## 提交与监控

提交前：

```bash
bash -n scripts/miyabi/*.pbs scripts/miyabi/*.sh
git status --short
git rev-parse HEAD
```

运行时只做非侵入观察：

```bash
qstat <job-id>
tail -n 100 <artifact-root>/pbs.stdout
tail -n 100 <artifact-root>/pbs.stderr
```

artifact 的确切文件名由 PBS wrapper 决定。不要在作业仍持有 authority 时手改 head、lease、
membership、work order、prepared result 或 lifecycle object。

## 验证与检查

完整 authority 检查：

```bash
python -m fs_diloco.log.inspect_cli replay \
  --root <shared-root>/authority --run-id <run-id> --generation 0
python -m fs_diloco.log.inspect_cli orphans \
  --root <shared-root>/authority --run-id <run-id> --generation 0
```

生命周期检查（全局参数必须放在 subcommand 前）：

```bash
python -m fs_diloco.lifecycle_cli \
  --storage-root <shared-root>/authority --run-id <run-id> --run-generation 0 \
  reachability --explain <object-key>

python -m fs_diloco.lifecycle_cli \
  --storage-root <shared-root>/authority --run-id <run-id> --run-generation 0 \
  gc-mark --output <mark.json>
```

`gc-mark` 是 dry-run。`gc-apply` 仅接受 `--namespace synthetic`，并要求 approval token 与
request ID；real namespace 不提供 destructive apply 入口。

## 恢复规则

- fresh open、takeover、显式 verify、CAS ambiguity、head jump 或 corruption suspicion 必须从空缓存
  strict replay。
- 只有一次完整 strict replay 成功后，当前 owner/session 才能建立 process-local verified-object
  memoization；memoization 不得序列化，也不得跨 ownership boundary。
- CAS conflict 后丢弃 tentative selection/result 视图，reload tensors、replay、revalidate、reselect。
- snapshot 只有被 committed snapshot pin 引用且 snapshot+suffix 等于 strict replay 时才能作为
  加速基；缺失、损坏或过期 snapshot 必须回退 strict replay。
- `latest.json`、stop file、heartbeat 和 telemetry 不能用于决定恢复 prefix。终止权威是 committed
  stop/error control transition。

## 非瞬态 8-node 失败

不要原样立即重投。必须：

1. 保存 failure manifest、PBS/qstat、stage timings、authority status 和 checksum；
2. 在 `plans/duraloco/phases/` 的当前 report/ledger 记录失败，在 `plans/duraloco/reviews/` 写 workflow
   或 root-cause review；
3. 用最小 targeted compute benchmark 证明修复；
4. 在同一个干净 commit 上重新通过 1-node 与 2-node qualification；
5. 只允许一次新的 8-node attempt，并把 superseded PASS/FAIL 都保留。

queue delay、未运行或日志暂不可见不是 PASS。只有 terminal PBS、artifact audit 和 independent
checker 共同满足 acceptance 时才能更新 phase 为 completed。

## 89.44 秒恢复的运维含义

H0 最大值发生在硬故障注入，包含安全 lease expiry 和下一次 commit 的全部工作。TTL 45 秒使
takeover 不可能像普通进程重启那样在数秒内完成。当前值对 50-local-step 的低频同步基线可接受，
但应持续记录 `fault → lease acquisition → replay complete → work order → prepare → CAS` 的分段时间。
优化目标是减少 lease 之外的 replay/scan/I/O 与计算等待，而不是降低 fencing 正确性。
