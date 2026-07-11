# P05 Final Independent Checker Report

Verdict: PASS
required_gate_followups: none
P05-A09: PASS
P05-A13: PASS
checking_to_completed: AUTHORIZED

## English

Independent PBS `2360301.opbs` on `mg0029`
checked persistence commit `fe41f80067d2ee30b271524e110dcbd50f98f102` and verified Maker
implementation `82dbec10e1a738cfaa88212698e7e8cf5a0f7ae1`. The complete 20-ID P05
map, clean schema-v2 1/2/9-node lineage, derived-state reconstruction, real
two-node old-owner rejection, terminal GPT-2/WikiText-2 50×10 active/standby
takeover, single-head-CAS audit, clock-safety boundary, 10,000 reference traces,
and D-M0010–D-M0012 evidence attribution pass.

The Checker-only counterexample corrupted the observational lease after epoch 1.
Lease parsing failed closed without changing committed authority; after restoring
the lease bytes, epoch 2 takeover succeeded and the old owner's stop mutation was
rejected. P05-A01 through P05-A20 are authorized complete with no required-gate
follow-up. This does not authorize merging `main`.

## 中文

独立 PBS `2360301.opbs` 在 `mg0029` 上复核了
持久化提交 `fe41f80067d2ee30b271524e110dcbd50f98f102`，并验证 Maker implementation
`82dbec10e1a738cfaa88212698e7e8cf5a0f7ae1`。完整 20 项 P05 映射、干净 schema-v2
单/双/九节点 lineage、派生状态重建、真实双节点旧 owner 拒绝、GPT-2/WikiText-2
50×10 active/standby terminal takeover、唯一 head-CAS 审计、时钟安全边界、
10,000 条参考 trace，以及 D-M0010–D-M0012 证据归属均通过。

Checker 专属反例在 epoch 1 后损坏观测性 lease。lease 解析 fail closed，且 committed
authority 不变；恢复 lease bytes 后 epoch 2 takeover 成功，旧 owner 的 stop mutation
被拒。Checker 授权 P05-A01 至 P05-A20 全部完成，且没有 required-gate follow-up；
这不授权合并 `main`。
