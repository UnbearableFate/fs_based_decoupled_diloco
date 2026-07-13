# 2026-07-12 Code Review：当前处置状态

原 review 在 P07 后识别了 23 个正确性、恢复、存储和性能问题。H0 已完成必须在 P08 前解决的
correctness/hardening 项，并通过完整 1→2→9 qualification 与独立 checker。本文件不再重复已失效的
“当前 bug”描述，而保存每项的解决状态和后续 owner。

权威证据：

- [H0 phase report](../../plans/duraloco/phases/H0_PHASE_REPORT.md)
- [H0 run/failure ledger](../../plans/duraloco/phases/H0_RUN_LEDGER.md)
- [H0 checker report](../../plans/duraloco/phases/H0_CHECKER_REPORT.md)
- [P08 plan](../../plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/10_P08_DIRECT_FRAGMENT_IO_STREAMING_REDUCER_AND_TELEMETRY.md)

## 已在 H0 解决并验证

| 原 ID | 问题 | 当前处置 |
|---|---|---|
| H1 | fragment learner 内层变量覆盖 `fragment_id` | 删除 shadowing；functional multi-fragment round-robin 回归绑定 interval metadata |
| H2 | committer crash 写成虚假的 `completed` stop | 异常路径提交 `error`，保留并重新抛出 primary exception |
| H3 | `finally` 可遮蔽异常/解引用空状态 | finalization 不再盖住 primary failure，derived stop 仅在 committed terminal 后写 |
| M4 | head conflict 没有完整 replay path | CAS ambiguity/conflict 强制 empty-cache strict replay、tensor reload、revalidate/reselect |
| M5 | 等待 executor 时 lease 不续租 | result wait 进入 long-substage renewal guard；D8 观察到 9 次 wait heartbeat |
| M6 | `resolve_mutation` 把 commit sequence 当 list index | 改为显式 sequence lookup 并加入 sparse/control-transition 回归 |
| M7 | heartbeat 未按 generation 隔离 | heartbeat 读取与 identity 改为 generation-scoped |
| M9 | 首次 lease acquisition race 使 loser 崩溃 | loser 变为幂等 return 或 typed coordination conflict |
| M11 | 假设 Lustre cross-node `flock` | capability contract + 2-node distinct-host exclusion/takeover probe，authority fail closed |
| L12 | 不可达的 `loss is None` 分支 | 删除 dead check，并由 lint/typed path 覆盖 |
| L13 | unsupported dtype quarantine 分类错误 | 使用 typed validation/quarantine reason |
| L14 | capsule cadence 环境变量在 hot loop 重复解析 | cadence/config 在 runtime setup 固化，不再作为每轮隐式环境变化 |
| H15 | `list_prefix` 全树扫描并读取 payload | prefix-scoped traversal + bounded checksummed header；inventory payload read 为 0 |
| H16 | `head()` 读取完整 payload | header-only head，完整 `get` 仍校验 payload |
| L23 | immutable idempotency 比较完整 bytes | idempotency 先使用 header identity；corrupt/unknown 行为仍 fail closed |

上述 runtime 在 `f167a07c49339ba42d14f8a5873fe2c8781884d4` 上通过 468 tests、D1、2-node
lock、D2-R2 和 D8-R2；checker `2369726.opbs` 对 16 项 counterexample 执行 RED-on-P07 / GREEN-on-H0，
并验证 deterministic tape 的 committed identity 未改变。

## 已部分处理，但后续仍有明确工作

| 原 ID | 当前事实 | 后续 owner |
|---|---|---|
| M8 | 异常现在提交 authoritative `error`，不会伪装完成；但“operator 是否/如何 unstop 同一 generation”仍未冻结 | P08 D-0800 |
| M10 | capability probe 能记录/要求 directory fsync；但全部 derived/legacy write surface 的 durability 统一仍未完成 | P08/P11 |
| L22 | lifecycle substage 现在由 worker 执行且 control thread 安持续租；每 substage 创建执行资源的工程开销仍可优化 | P11 |

## 正确性未阻塞、但必须继续优化

| 原 ID | 当前代码事实 | 目标 |
|---|---|---|
| M17 | POSIX `range_get` 调完整 `get` 后切片 | P08 true range/header I/O |
| M18 | catalog 重扫重复 read/SHA/finite validation，并持有多 payload | P08 typed validation reuse、cheap reject、bounded prefetch/streaming |
| M19 | transition/materialized export 有全 fragment/full model 重写与 cadence 放大 | P08 direct fragment + bounded materialization |
| M20 | learner publication 存在 duplicate copy/read-back 路径 | P08 single-copy content-addressed publication |
| M21 | lineage validation 可能随 history × selected 增长 | P08 O(selected) indexed evidence |

这些项不能因 H0 的 752 秒 terminal PASS 被视为解决。D8 lifecycle 时间仍从 34.33 秒增长到
68.42 秒，最大 fault-to-next-commit 为 89.44 秒；这正是 P08 profile-first 的输入。性能改动必须
保持 single head authority、ObjectRef validation、fencing、strict replay 和 transition identity，或在
显式新 schema/generation 中处理不兼容变化。
