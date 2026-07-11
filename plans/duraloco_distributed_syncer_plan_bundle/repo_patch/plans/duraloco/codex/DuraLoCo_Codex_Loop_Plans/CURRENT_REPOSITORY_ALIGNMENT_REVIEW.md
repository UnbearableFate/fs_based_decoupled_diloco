---
title: "DuraLoCo Distributed-Syncer Plans — Current Repository Alignment Review"
version: "1.0"
date: "2026-07-11"
repository_head_at_review: "06e3ca2299d5eb1a720c1d8f9107af5223095525"
review_scope: "08A and every required/optional successor plan"
status: "normative correction record"
---

# 当前仓库适配审查与修订结论

## 1. 审查基线

本次审查以当前仓库而不是计划包生成时的假设为准：

- 当前 `main`/`origin/main`：`06e3ca2299d5eb1a720c1d8f9107af5223095525`（P06 archive commit）；
- P06 verified Maker implementation：`2581a4d6286c7d0666f76aa3cc9d8122e66f6d25`；
- P06 Checker/persistence commit：`030129e045c4e5a2abb80eb100a0e28fb78d384d`；
- `plans/duraloco/STATE.yaml`：P06 `completed`，实际验收 ID 为 `P06-A01`–`P06-A20`；
- 当前生产入口仍为 `fs_diloco.syncer` 和 `fs_diloco.learner`；
- 已有可复用边界包括 `ProposalCatalog`、`RuntimeView`、
  `ProductionTransactionalLog`、`outer_optim`、`optimizer.reference_adapter`、
  `fragment_codec`、`fragment_index`、`param_index` 与 storage contract；
- 当前 head/frontier/control schema 只实现 P05/P06 的 fenced owner、optimizer commit 和 stop；
  尚无 membership、FWO、PFT、snapshot 或 capsule authority schema。

P06 的已归档报告和 Checker 只证明 A01–A20。原计划包把尚未实现的 CRS trace
要求追加入 P06-A21–A25，并把它们当作 P06A 前置条件；这会把已完成阶段变成无法满足的
历史重验门，和当前 `STATE.yaml`、phase report、Checker verdict 冲突。修订后，这些工作
成为 P06A Loop 1 的 bootstrap/characterization gate，不追溯修改 P06 verdict。

## 2. 发现的问题与处理

| 问题 | 对渐进实现的影响 | 修订 |
|---|---|---|
| P06A 依赖不存在的 P06-A21–A25 和 oracle bundle | P06A 无合法起点 | 只依赖已通过的 A01–A20；P06A 从 archive commit 建立 characterization bundle |
| P06A 计划新建一套 selection/optimizer/log adapter，忽略现有模块 | 容易复制语义并产生 drift | 先复用现有 `ProposalCatalog`、`ProductionTransactionalLog`、`outer_optim` 等，只抽取 `syncer.py` 中仍重复的 orchestration/numeric glue |
| P06A 允许用旧 P06 terminal run 替代新代码 C9 | 重构后的 production path 未被真实验证 | P06A 改动 production orchestration 后必须在同一 clean implementation commit 走 C1→C2→C9；旧 P06 只作 baseline |
| P06B 试图在当前 generation 原地加入 membership/FWO/PFT | 当前 Protocol-v2/P05 frontier/control schema无法表达，且冻结 identity 会被破坏 | P06A 冻结 inactive schema；P06B 以新的 run generation/coordination protocol bootstrap，不原地续写 P06 generation |
| CPU LFE 与当前 GPU CRS 被要求 tensor/content digest 完全相同 | 跨 CPU/GPU 浮点结果通常无法保证 bitwise 相同 | 区分 exact identity equivalence 与 tolerance-based numeric equivalence；FWO 冻结 execution backend，same-FWO duplicates 必须同 backend 且 exact |
| PFT identity混入executor/attempt/telemetry，final transition又引用winner PFT | 不同完成顺序会改变 authoritative transition identity | 分离 canonical prepared-result digest 与 attempt envelope；final transition identity绑定 work order + canonical result，不绑定winner到达顺序或telemetry |
| P07/P08从P06C并行修改log/schema/codec | 当前代码边界尚未冻结，合并风险高且不利于单步验收 | required route改为 P06C→P07→P08→P10；P07先冻结lifecycle接口，P08再优化 |
| P07把snapshot、destructive GC、exact capsule和D8-R2 soak作为一个不可分割实现 | 失败定位和回滚困难 | 明确 P07.1 replay/snapshot、P07.2 reachability/dry-run、P07.3 synthetic apply、P07.4 capsule、P07.5 D8 集成子门 |
| P08 bundle gates看似必需，但bundle只应由profile触发 | 可能为未出现的瓶颈引入新commit语义 | 未触发时必须以 evidence-qualified `not_applicable` 关闭；触发时需新 schema/ADR 和独立 serial-equivalence gate |
| P10同时强制系统调优和算法语义调优 | local interval/quorum/fairness会改变proposal与trajectory，不能仅靠telemetry本地决定 | 先完成 shadow + system-only actions；算法影响 actions 需 committed policy、新 generation 和质量证据，可形成受限/negative结论 |
| 包内README仍称“P05完成、P06待完成” | 应用到当前仓库后执行指令错误 | 更新为P06已完成，P06A为下一阶段，并记录三个P06 commit角色 |

## 3. 可执行的渐进路线

修订后的 required route 为：

```text
P06 archive (06e3ca2)
  → P06A characterization + decomposition on unchanged C topology
  → P06B new-generation factor-1 D1 → D2 → D8
  → P06C exact duplicate identity + R2 D1 → D2 → D8
  → P07 replay/reachability/GC/capsule subgates
  → P08 measured performance work; bundle only if triggered
  → P10 shadow first, system-only enforcement first
  → P11 acceptance
  → P12 preregistered evaluation
```

每个阶段继续遵守 current project 的 `ORIENT → SPECIFY/RED → IMPLEMENT/GREEN →
HARDEN → CHECK → PERSIST`，并从1节点开始，再到2节点，最后才运行主拓扑。任何修改
production orchestration、protocol generation、numeric backend或PBS launcher的阶段，
不得复用旧 runtime pass 作为新实现 pass。

## 4. 当前可直接开始的 P06A 最小切片

1. 从 `06e3ca2` archive tip 建立新 feature branch，同时记录 verified implementation
   `2581a4d` 和 Checker evidence `030129e`；
2. 只读 characterise 当前 `fs_diloco.syncer`，把 selected IDs、hex weights、aggregate
   bytes/digest、parameter/outer-state refs、prepared transition和committed view写入测试
   trace；
3. 先复用现有 `ProposalCatalog.select`、`normalized_weights`、`outer_optimizer_step`、
   `ProductionTransactionalLog.prepare_transition/commit_prepared`，不新建第二套policy；
4. 抽取一个 transaction-attempt kernel/input-output边界，再让现有 `run_syncer` 调用；
5. local/static与dependency-complete tests通过后，在Miyabi按C1→C2→C9验证同一clean
   implementation commit；
6. 只有P06A Checker PASS后才冻结distributed generation schema并进入P06B。

应用计划包时还必须做一次非运行时的route reconciliation：当前`STATE.yaml.next_action`
仍写着“start P07 and P08 independently”。保留P06 `completed`、A01–A20、checks、artifacts和
Checker report不变，只把`current_goal`/`next_action`更新为从`06e3ca2`启动P06A，并明确
这是plan-route handoff，不是新的P06 pass。

该切片不需要提前实现membership、LFE、FWO/PFT publication、redundancy、GC或controller，
因此可以在当前代码基础上安全渐进，而不是一次重写整个syncer。
