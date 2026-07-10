# 概览 / Overview

## 中文

本项目在 Miyabi-G 上运行一个独立 syncer 与若干独立 learner。learner 在本地执行
多步训练，向共享存储写入 safetensors payload 和 JSON discovery marker。syncer
从头重扫 marker，执行 Protocol v2 完整验证，用 P02 冻结的 oldest-first 语义选择
候选，并在 GPU 上做 merge 与 outer optimizer step。

每次 transition 先写不可变 proposal、params、outer state、commit 和 frontier，
最后只通过一次 head CAS 提交。head 指向的 committed prefix 是全局优化器唯一持久
权威。`latest.json`、stop、heartbeats、JSONL、CSV 和 W&B 只是导出或观测。

full-vector 与 fragment 模式共用同一 transaction API。它们只在 fragment layout、
proposal tensor key 和 learner adoption 行为上不同。

M00 支持全局 committed-prefix 精确恢复，但尚不声明 fenced 多 syncer failover、exact
learner restart 或安全权威对象 GC；这些分别属于 P05、P07。

## English

The project runs one independent syncer and multiple independent learners on
Miyabi-G. Learners perform local training and publish a safetensors payload plus
a JSON discovery marker. The syncer performs repeatable full scans, strict
Protocol v2 validation, frozen oldest-first selection, GPU reduction, and an
outer-optimizer step.

A transition prepares immutable proposal, parameter, outer-state, commit, and
frontier objects, then commits them with exactly one head CAS. The prefix
reachable from head is the sole persistent global-optimizer authority.
`latest.json`, stop files, heartbeats, JSONL, CSV, and W&B are exports or
observations.

Full-vector and fragment modes share the same transaction API. M00 provides
exact committed-prefix recovery, but does not yet claim fenced multi-syncer
failover, exact learner restart, or authoritative-object GC.
