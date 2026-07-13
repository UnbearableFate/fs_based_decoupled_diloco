# FS DiLoCo / DuraLoCo on Miyabi

这是一个面向 Miyabi-G 的 filesystem-backed Decoupled DiLoCo 研究实现。当前经过完整
验证的主路径是 **DuraLoCo Protocol v2**：8 个独立单 GPU learner、每个 learner 主机上的
CPU fragment executor（LFE），以及在 learner 主机间浮动的 fenced committer。系统不需要
专用、持久有状态的 syncer 节点。

全局参数、分片 outer-optimizer state、proposal 消费状态和恢复边界只有一个持久权威：

```text
authority/runs/<run-id>/generations/<8-digit-generation>/control/head.json
```

所有 optimizer transition 先写不可变对象，再通过一次 head compare-and-swap 提交。
`latest.json`、checkpoint/materialized weights、heartbeat、telemetry、CSV/JSONL/W&B 和进程内
缓存都只是可重建视图或观测数据，不能参与恢复裁决。活跃实现不使用嵌入式数据库保存权威
状态。

## 当前状态

- M00–P08 已完成；P08 runtime commit 为
  `8492eb4163b406baf67d6d56f100b693dd6aa781`，独立 Checker PBS
  `2371170.opbs` 为 PASS。当前工作是 pre-P10 的 P08R 性能恢复门。
- 历史 H0 的 9-node allocation / 8-node runtime GPT-2 + WikiText-2 实验完成
  50 local × 10 global，总耗时 752 秒，最大故障到下一次提交恢复时间 89.44 秒。
  当前及后续生产/资格实验统一为严格 8-node allocation，不再申请第九节点。
- 当前分支上的精确状态和原始证据入口见 [docs/status.md](docs/status.md) 与
  [plans/duraloco/STATE.yaml](plans/duraloco/STATE.yaml)。

89.44 秒包含安全 lease 失效等待、takeover 后 empty-cache strict replay、proposal 重选和下一次
transition 的执行/提交；其中 lease 参数 `TTL=45s`、`renew=10s`、`clock skew=2s` 决定了约
37–47 秒的安全接管窗口。这是当前可接受的正确性基线，不是最终性能目标；P08R/P11 仍应优化
恢复路径和扫描/I/O 放大，但不能缩短 fencing 安全边界。

## 从这里开始

- [文档索引与有效性规则](docs/README.md)
- [用户快速开始](docs/user-guide/quickstart.md)
- [Miyabi 运行与故障处理](docs/user-guide/operations.md)
- [配置参考](docs/user-guide/configuration.md)
- [当前架构](docs/duraloco/architecture.md)
- [研究主张、保证和非主张](docs/duraloco/research_contract.md)
- [持久化事务日志](docs/duraloco/transaction_log.md)
- [生命周期、snapshot、capsule 与 GC](docs/duraloco/lifecycle.md)

## 仓库结构

```text
fs_diloco/                 Python 实现
configs/                   已使用或保留的运行配置
scripts/miyabi/            PBS 验证、实验和检查脚本
scripts/local/             仅适用于安全 runtime 环境的本地 smoke helper
scripts/agent/             登录节点可运行的静态契约检查
tests/                     协议、日志、协调、生命周期与 runtime 回归测试
docs/                      当前用户与设计文档
plans/duraloco/            阶段计划、决策、失败记录与验收证据
artifacts/duraloco/        PBS 运行产物（环境中存在时）
```

## Miyabi 安全边界

登录节点只用于查看、编辑、静态检查、提交 PBS 和读取日志。不得在登录节点执行训练、模型
加载、CUDA/torch/transformers import、数据预处理、`torchrun`、`mpirun` 或 pytest runtime
测试。运行时验证必须在 PBS compute allocation 内按 1-node → 2-node → 8-node 顺序进行。

登录节点可执行：

```bash
bash -n scripts/miyabi/*.pbs scripts/miyabi/*.sh scripts/local/*.sh
.venv/bin/ruff check fs_diloco tests scripts/agent
.venv/bin/python scripts/agent/check_research_contract.py --root "$PWD"
.venv/bin/python scripts/agent/check_docs.py --root "$PWD"
.venv/bin/python scripts/agent/check_no_embedded_database.py --root "$PWD"
```

PBS 脚本提交前必须绑定干净 commit，并显式设置脚本要求的 `EXPECTED_COMMIT`、`RUN_ID`、
`ARTIFACT_ROOT`、`STORAGE_ROOT` 等变量。不要把旧的 central-syncer 或九节点 allocation
脚本当作当前 DuraLoCo 分布式资格证明；当前性能恢复入口以 P08R 计划及严格 8-node 的
`run_duraloco_p08_d8.pbs`、`run_duraloco_p08_d8_r2.pbs` 为准。

## 通信与兼容范围

当前 milestone 的 optimizer 数据面由共享文件系统和不可变内容对象承载，不使用
`torch.distributed`、NCCL、RPC、Ray、DeepSpeed、FSDP 或 PCCL。仓库仍保留
`fs_diloco.syncer` 及早期 PBS 脚本用于 reference/legacy smoke；它们不是 P07/H0 验证过的
8-learner DuraLoCo 生产拓扑，也不应产生新的恢复或性能主张。
