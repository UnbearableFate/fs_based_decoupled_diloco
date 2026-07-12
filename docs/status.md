# 当前实现与验证状态

更新基准：2026-07-13；文档重写所检查的代码基线为
`97777a5b6a5599889fdb75cf713f5f7424064210`。
本页是阅读入口，不替代 [DuraLoCo 状态文件](../plans/duraloco/STATE.yaml) 或原始报告。

## 已完成范围

M00–P07 已完成，H0 pre-P08 hardening 也已完成。当前可继承的 runtime commit 是
`f167a07c49339ba42d14f8a5873fe2c8781884d4`，独立 checker commit 是
`04e0a8634b0e9d7c4cd55c5593081a0ca969a060`。详细验收与失败记录见：

- [H0 phase report](../plans/duraloco/phases/H0_PHASE_REPORT.md)
- [H0 run/failure ledger](../plans/duraloco/phases/H0_RUN_LEDGER.md)
- [H0 checker report](../plans/duraloco/phases/H0_CHECKER_REPORT.md)
- [P07 phase report](../plans/duraloco/phases/P07_PHASE_REPORT.md)

当前实现已经覆盖：单 head-CAS 事务日志、严格 replay、fenced floating committer、learner-hosted
冗余 fragment execution、membership revision、snapshot+suffix 恢复、可解释 reachability、
默认 dry-run GC、exact learner capsule、Lustre 跨节点排他锁能力探测，以及错误终止事实的
authoritative commit。

## 最终 H0 资格阶梯

| PBS | 形状 | 结果 |
|---|---|---|
| `2369617.opbs` | 1 node；ruff、禁用数据库扫描、116 focused、全套测试 | 468 passed，1 skipped |
| `2369625.opbs` | 1 node；真实 GPT-2 D1 | 1 transition、2 capsules、snapshot strict equality |
| `2369628.opbs` | 2 node；Lustre `flock` | 持锁时排他、释放后 takeover |
| `2369629.opbs` | D2-R2 | executor/committer/host failover，4 transitions |
| `2369634.opbs` | 9-node allocation / D8-R2 runtime | GPT-2/WikiText-2 50 local × 10 global，PASS |
| `2369726.opbs` | 1 node independent checker | 16/16 RED 与 16/16 GREEN，PASS |

D8-R2 使用 8 个 learner GPU、8 个 learner-hosted CPU executor、2 个 eligible floating
committer candidate、replication factor 2，且专用 syncer 节点数为 0。作业完成 10 次 optimizer
transition、5 次 lifecycle cycle、8 个 exact capsule、executor process loss、whole learner-host
loss 和 authoritative stop，总耗时 752 秒。五次 inventory 的 payload bytes read 均为 0；
strict replay 对实际读取对象仍执行完整校验。

## 为什么最大故障恢复是 89.44 秒

该指标测量“故障发生到下一次 committed transition”，不是单纯的进程重启时间。它包含：

1. 旧 owner 停止续租后等待 lease 安全失效；
2. 新 owner 获取更高 fencing epoch；
3. ownership boundary 后从空缓存执行完整 strict replay 和对象校验；
4. 重建 membership/eligibility，重新选择 proposal；
5. 冗余 executor 计算结果并由新 owner 完成 head CAS。

当前参数为 `lease_ttl_seconds=45`、`renew_interval_seconds=10`、
`max_clock_skew_seconds=2`。根据故障落在续租周期中的位置，仅安全接管等待通常约 37–47 秒；
余下时间来自 replay、proposal/data I/O、prepare 和下一次 commit。因此 89.44 秒不是常态延迟，
而是注入硬故障路径中的最大端到端样本。

结论是：对低频（50 local step 才做一次 global transition）的研究基线，这个结果可接受，
而且安全性优先于缩短 takeover；但它不能被称为“无需优化”。P08 应先 profile，优化 prefix/range
I/O、验证复用、single-copy publication、materialization 和 proposal catalog；P11 再处理长期
运行与工程卫生。任何优化都不能绕过 TTL/fencing、strict replay 或 head CAS。

## 尚未完成或不能声称的内容

- P08 尚未完成：POSIX `range_get` 仍通过完整 `get` 后切片；proposal catalog 仍有重复扫描、
  payload 再验证、全量 materialization/copy 和潜在 O(N²) lineage 路径。
- `data.streaming` 是配置字段，但当前训练/性能基线不能据此声称真正端到端 streaming。
- exact capsule schema、发布、恢复和 synthetic bitwise continuation 已验证；D8 chaos 中 whole-member
  loss 采用 membership removal，不等于自动恢复失败 learner 并无缝重入。
- real authority namespace 的 GC 只 dry-run；destructive apply 仅允许 `synthetic` namespace，
  且必须 approval token + apply-time revalidation。
- 不保证 Byzantine 容错、永久存储丢失后的恢复、exactly-once transport、全训练 bitwise replay，
  也不声称在所有模型/故障率/后端上优于 collective communication。
- 早期 central `fs_diloco.syncer` 路径仍在仓库中用于 reference/legacy smoke，但不是当前 D8-R2
  分布式资格证明。

## 失败记录

H0 的失败没有被最终 PASS 覆盖：`2369364`、`2369366` 是 stale acceptance fixture；首次
checker `2369715` 暴露 RED 用例不够强和 manifest purpose 错误。它们及所有 superseded
passing run 均保存在 [H0 run/failure ledger](../plans/duraloco/phases/H0_RUN_LEDGER.md)。
