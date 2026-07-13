# 文档索引与有效性规则

本目录只描述当前代码与已经取得的证据。阶段过程、失败日志和历史计划保存在
`plans/duraloco/`，不会为了让当前说明更简洁而改写历史证据。

## 权威顺序

发生冲突时按以下顺序判断：

1. 活跃源代码、配置校验和测试；
2. `plans/duraloco/STATE.yaml`、`DECISIONS.md`、`BLOCKERS.md` 和当前阶段报告；
3. 本目录的当前说明；
4. 明确标为 historical 的 baseline 文档与旧阶段计划。

“计划实现”“测试 fixture 存在”和“在 Miyabi 上验证通过”是三个不同状态。只有阶段验收证据
和独立 Checker 才能支持完成性主张；未运行的 PBS 检查不能被推断为通过。

## 当前文档

| 主题 | 文档 | 内容 |
|---|---|---|
| 进度与实测 | [status.md](status.md) | 当前阶段、H0 证据、89.44 秒恢复解释、已知限制 |
| 快速开始 | [user-guide/quickstart.md](user-guide/quickstart.md) | 环境边界、配置选择、静态检查、PBS 入口 |
| 配置 | [user-guide/configuration.md](user-guide/configuration.md) | 所有配置 section、冻结约束和不应误解的选项 |
| 运维 | [user-guide/operations.md](user-guide/operations.md) | 作业阶梯、日志检查、恢复、失败持久化 |
| 架构 | [duraloco/architecture.md](duraloco/architecture.md) | learner/LFE/committer、数据流和 authority |
| 研究契约 | [duraloco/research_contract.md](duraloco/research_contract.md) | 精确定义、保证、非主张与证据纪律 |
| 协议 | [duraloco/protocol_v2.md](duraloco/protocol_v2.md) | schema、identity、validation、RunSpec |
| 事务日志 | [duraloco/transaction_log.md](duraloco/transaction_log.md) | prepare、CAS、strict replay 与冲突处理 |
| 存储 | [duraloco/storage_contract.md](duraloco/storage_contract.md) | POSIX envelope、锁、完整性和能力探测 |
| 生命周期 | [duraloco/lifecycle.md](duraloco/lifecycle.md) | snapshot、reachability、capsule、GC |
| 故障 | [duraloco/failure_model.md](duraloco/failure_model.md) | 故障窗口、恢复级别、fencing 和边界 |
| 数值 | [duraloco/numeric_contract.md](duraloco/numeric_contract.md) | canonical weight、dtype、outer optimizer |
| 不变量 | [duraloco/invariants.md](duraloco/invariants.md) | I-001–I-012 与测试 owner |
| Reference | [duraloco/reference_model.md](duraloco/reference_model.md) | 小状态机、crash matrix 和 production 对照 |
| 迁移状态 | [duraloco/migration_map.md](duraloco/migration_map.md) | 已完成、当前与后续工作 |
| H0 review | [reviews/20260712_code_review.md](reviews/20260712_code_review.md) | 原 review 项目的解决/延期归属 |

`duraloco/baseline_inventory.md` 与 `baseline_limitations.md` 只保留为 P00 历史基线证据，
不描述当前 runtime。

## 已退休文档

本次重写删除了会把早期 central-syncer/本地数据库原型误写成当前系统的文档：旧单文件双语
指南、旧 design/experiments/Miyabi runbook、编号 00–07 的重复 user guide，以及 P00/P03
临时 drift report。对应信息已并入本索引、`user-guide/` 和 `duraloco/` 的主题文档。

历史 phase report 中指向旧文件的文字是当时的审计记录，不代表旧文件仍是当前文档；P00
baseline 文件因被 traceability 引用而保留，并在文件首部明确标注 historical。

## 维护规则

- 新的当前行为必须能指向代码、配置校验、测试或 PBS 证据；不要把 roadmap 写成已实现。
- authority、derived/observational 对象和历史兼容路径必须明确区分。
- 故障和 superseded run 必须写入 `plans/duraloco/phases/` 下的当前 ledger/report。
- 修改本目录后运行 `scripts/agent/check_docs.py` 和 `check_research_contract.py`。
- 若改动运行表面，仍需遵守 Miyabi 的 1-node → 2-node → 8-node 验证阶梯；
  当前及后续实验禁止申请第九节点。
