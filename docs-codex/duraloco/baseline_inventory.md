# P00 Baseline Inventory（Historical Evidence Only）

本文件保留 P00 的迁移起点，供历史 traceability 使用，不描述当前 runtime。P00 观测基准为
`afc50a1e179c64321645b278b2497ea3ab3fe24d`；完整 manifest、tree、test/PBS evidence 位于
`plans/duraloco/phases/` 和对应 artifact。

## 当时的 prototype

P00 之前的系统是 central learner/syncer prototype：learner 通过共享目录发布 safetensors + JSON
marker，单 syncer 做 candidate selection、merge、outer update 和 materialized latest/checkpoint。full-vector
和 balanced-tensor fragment 已存在，但 authority、recovery、fencing、transaction log 和 lifecycle 语义
尚未统一。

该基线的核心迁移问题是：进程本地选择状态、共享文件、latest/checkpoint 与本地持久状态之间有多种
可能的“真相”，无法支持 prefix-consistent recovery 或 fenced failover。P00 的作用是冻结现状和失败，
不是认证旧实现。

## 可复用资产

后续阶段保留并演进了以下结构：

- Hugging Face model/data 和 synthetic-tiny runtime；
- parameter index、balanced whole-tensor fragment index 和 round-robin scheduler；
- safetensors codec、token/staleness merge 与显式 outer optimizers；
- learner local training、adoption、metrics/analysis 与 PBS launch envelope；
- 1/2/9-node Miyabi 验证梯度。

## 已替换的结构

当前 DuraLoCo 已用 Protocol v2 immutable Proposal/Commit/Frontier、POSIX semantic storage、single head
CAS、strict replay、fenced floating committer、distributed FWO/PFR 和 lifecycle object graph 替换早期的
多权威恢复模型。`latest.json`、checkpoint、heartbeat 与 telemetry 只保留为 derived/observational。

早期 central entry point 和部分 debug PBS 仍用于 reference/legacy smoke，但不能恢复 P00 authority，也
不能替代当前 D8-R2 资格证明。当前差异见 [migration_map.md](migration_map.md)，当前架构见
[architecture.md](architecture.md)。
