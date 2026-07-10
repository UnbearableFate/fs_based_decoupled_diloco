# M00 Milestone Report

## English

### Status

- Phase: M00 — SQLite-free runtime rebase and P00–P04 requalification
- Branch: `codex/duraloco-m00-sqlite-free-rebase`
- Base: user design commit `f32b9ddf3fd6443947c178aee667029df1c7f86d`
- State: `in_progress`
- Completed acceptance targets: none yet
- Pending acceptance targets: M00-A01 through M00-A12
- Checker verdict: not run

The first implementation commit removes the legacy persistence surface, adds
the production safetensors transaction path, replay-derived `RuntimeView`,
re-entrant proposal catalog, file-native analysis, explicit warm-start
generation metadata, and M00 static/runtime harnesses. Static source/config/
script/test scanning passes. Compute qualification remains in progress.

### Checker and qualification failure history

#### Maker attempt 1 — `20260711_m00_6e615e1_1node`

- Time/identity: PBS `2359070.opbs`, host `mg0025`, implementation
  `6e615e1421ccbc23eb303c9e9f8a3e3d61b6fddf`.
- Phenomenon: the forbidden-surface gate passed, then the dependency-complete
  suite reported 7 failures (`263 passed, 1 skipped`) before the process
  smokes started.
- Expected/actual: the suite must be green. Production outer-state decoding
  rejected the integer step tensor in six new production/catalog cases; two
  historical tests still asserted the pre-M00 runtime/default selection.
- Reason: confirmed. The dependency-free safetensors header parser recognized
  only floating dtypes even though production outer state legitimately includes
  one `I64` step tensor. Historical compatibility tests were not remapped to
  the M00 production-backend and oldest-first contracts.
- Impact: M00-A02 through M00-A06 and the P00/P02 remapping gate.
- Evidence: `artifacts/duraloco/M00/20260711_m00_6e615e1_1node/manifest.json`,
  `stdout.log`, and `junit.xml`.
- Repair: admit `I64` structurally for outer-state parsing, keep proposal dtype
  schemas floating-only, and remap the two stale tests. Retry will use a new
  run ID with this attempt as `parent_run_id`.

#### Maker attempt 2 — `20260711_m00_74b5cbe_1node`

- Time/identity: PBS `2359078.opbs`, host `mg0027`, implementation
  `74b5cbee242b877c86ba2f3293d855f3f9c8571c`.
- Phenomenon: the static gate passed and the suite improved to one failure
  (`269 passed, 1 skipped`). The listing omission/reorder catalog case found
  zero valid candidates instead of two; process smokes did not start.
- Expected/actual: both valid markers must survive deduplication and the older
  sequence must be selected. Both were quarantined during identity parsing.
- Reason: confirmed. Catalog construction included the optional
  `previous_interval_proposal_id` key with a null value when computing the
  proposal ID. Schema serialization correctly omitted the absent optional
  field, so identity recomputation detected a mismatch.
- Impact: M00-A03, M00-A04, and the P01 identity remapping gate.
- Evidence: `artifacts/duraloco/M00/20260711_m00_74b5cbe_1node/manifest.json`,
  `stdout.log`, and `junit.xml`.
- Repair: omit the optional identity field entirely unless a predecessor ID is
  present. The next retry remains parent-linked.

### Limitations and next action

M00 still assumes one active syncer. Lease/fencing begins in P05; learner exact
restart and authoritative GC remain later work. Next action is a parent-linked
clean one-node retry, followed only on PASS by the two-node and nine-node gates.

## 中文

### 状态

- 阶段：M00 — 无 SQLite 运行时重构与 P00–P04 再验收
- 分支：`codex/duraloco-m00-sqlite-free-rebase`
- 基线：用户设计提交 `f32b9ddf3fd6443947c178aee667029df1c7f86d`
- 状态：`in_progress`
- 已完成验收项：暂无
- 待完成验收项：M00-A01 至 M00-A12
- Checker 结论：尚未运行

首个实现提交删除旧持久化表面，加入 production safetensors transaction、由 replay
派生的 `RuntimeView`、可重入 proposal catalog、文件原生 analysis、显式 warm-start
generation metadata 与 M00 静态/运行 harness。源码、配置、脚本与测试的静态禁止项
扫描已通过；compute 再验收仍在进行。

### Checker 与资格验证失败历史

#### Maker 第 1 次尝试 — `20260711_m00_6e615e1_1node`

- 时间/身份：PBS `2359070.opbs`，节点 `mg0025`，实现提交
  `6e615e1421ccbc23eb303c9e9f8a3e3d61b6fddf`。
- 现象：forbidden-surface gate 通过；dependency-complete suite 随后出现 7 个失败
  （`263 passed, 1 skipped`），尚未进入 process smoke。
- 预期/实际：完整套件应为绿色。production outer-state decode 在 6 个新
  production/catalog case 中拒绝整数 step tensor；两个历史测试仍断言 M00 之前的
  runtime default 与 selection。
- 原因：已证实。无依赖 safetensors header parser 只识别浮点 dtype，但 production
  outer state 合法包含一个 `I64` step tensor；两个 compatibility tests 未重映射到
  M00 production backend 和 oldest-first contract。
- 影响：M00-A02 至 M00-A06，以及 P00/P02 重映射 gate。
- 证据：`artifacts/duraloco/M00/20260711_m00_6e615e1_1node/manifest.json`、
  `stdout.log` 与 `junit.xml`。
- 修复：outer-state 结构解析允许 `I64`，proposal dtype schema 仍仅允许浮点；同步
  更新两个过期测试。重试使用新 run ID，并通过 `parent_run_id` 指向本次尝试。

#### Maker 第 2 次尝试 — `20260711_m00_74b5cbe_1node`

- 时间/身份：PBS `2359078.opbs`，节点 `mg0027`，实现提交
  `74b5cbee242b877c86ba2f3293d855f3f9c8571c`。
- 现象：静态 gate 通过，完整套件缩小为一个失败（`269 passed, 1 skipped`）。listing
  omission/reorder catalog case 应得到两个候选，实际为零；尚未进入 process smoke。
- 预期/实际：两个合法 marker 都应通过去重，并选择较旧 sequence；实际在 identity
  parsing 中均进入 quarantine。
- 原因：已证实。catalog 在计算 proposal ID 时把可选
  `previous_interval_proposal_id` 以 null key 放入 body；schema 序列化会正确省略缺失
  可选字段，因此 identity 重算发现不一致。
- 影响：M00-A03、M00-A04 与 P01 identity 重映射 gate。
- 证据：`artifacts/duraloco/M00/20260711_m00_74b5cbe_1node/manifest.json`、
  `stdout.log` 与 `junit.xml`。
- 修复：只有确实存在 predecessor ID 时才加入该可选 identity 字段；下一次重试继续
  parent-linked。

### 限制与下一动作

M00 仍假设只有一个 active syncer；lease/fencing 属于 P05，learner exact restart 与
权威 GC 属于后续阶段。下一动作是 parent-linked 干净单节点重试；只有通过后才进入
双节点与九节点 gate。
