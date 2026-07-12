# P00 Baseline Limitations（Historical Evidence Only）

P00 在 Miyabi compute node `mg0032`、PBS `2357333.opbs`、clean commit
`32e84da63c5a0a31842fbcca46a5bc2876398dad` 上保留了一个重要失败：tiny full-vector smoke 的 learner
在目标第二次 outer transition 前耗尽 `max_local_steps=8`，最终因 30 秒 no-progress timeout 在 global
version 1 终止；同作业的 fragment smoke 达到了配置的 4 次 transition。

这是旧 prototype 的 configuration/liveness 失败，不是 Protocol v2/DuraLoCo correctness 结果。P00
harness 仅为保存该已知失败，显式允许了 `no_progress_timeout`；没有通过改变训练语义把基线伪装成
PASS。原始命令、loss、stop reason、PBS stdout 和 artifact evidence 保留在 P00 artifact/phase record。

该问题不能推断当前 H0 runtime 仍会以同样方式失败。当前状态与已知限制见
[../status.md](../status.md)，当前失败/superseded run 见
[../../plans/duraloco/phases/H0_RUN_LEDGER.md](../../plans/duraloco/phases/H0_RUN_LEDGER.md)。
