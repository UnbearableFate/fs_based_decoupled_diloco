# 训练与恢复 / Training and Recovery

## 中文

登录节点只做编辑、静态检查、提交作业和查看日志。训练、模型加载、pytest、Torch
导入、MPI 与 CUDA 检查必须在 PBS compute node。

单节点调试：

```bash
qsub scripts/miyabi/run_1node_debug.pbs
```

两节点或九节点脚本同样位于 `scripts/miyabi/`。作业内部重新记录 module、Python、
commit、host、mount 与 stripe 信息。

成功 run 至少满足：analysis 能验证 committed prefix；`transition_committed` 数量符合
目标；loss 有限；每个 commit 的选择数满足 quorum；最终 materialized checkpoint 与
head 一致。

精确 syncer 恢复使用相同 run ID/generation，并设置：

```yaml
init:
  resume: true
  resume_version: latest
  run_generation: 0
```

恢复直接打开 authority head、完整 replay，并从 head-reachable params/outer-state
objects 重建 `RuntimeView`。它不读取 derived latest 或本地持久状态来决定正确性。

历史 checkpoint 只能通过 `bootstrap-new-generation` 语义进入新 generation，并明确
标记 warm start；它不是 exact continuation。

## English

Login nodes are control-plane only. Training, model loading, pytest, Torch
imports, MPI, and CUDA checks run inside PBS compute allocations.

Submit the one-node debug path with:

```bash
qsub scripts/miyabi/run_1node_debug.pbs
```

A successful run has a verified committed prefix, the expected number of
`transition_committed` events, finite losses, quorum-sized committed
selections, and a materialized checkpoint matching head.

Exact syncer recovery keeps the run identity/generation and sets `resume: true`
with `resume_version: latest`. Recovery opens head, replays the complete prefix,
and reconstructs `RuntimeView` plus paired parameter/outer-state tensors.
Historical checkpoint bootstrap always creates a new generation and is a warm
start, not exact continuation.
