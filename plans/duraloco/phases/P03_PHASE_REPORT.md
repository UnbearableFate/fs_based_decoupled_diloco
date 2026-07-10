# P03 Milestone Report

## English

### Status

- Phase: P03 — semantic storage API and POSIX/Lustre contract
- Branch: `codex/duraloco-p03-posix-storage`
- Base: `codex/duraloco-p02-reference-model` at
  `5f03afae833712706814a9c295970a5800a8f04e`
- Checked persistence commit: `d60ad26dfcf00a060caeadea8cc468977d8c2272`
- State: `completed`; final Checker authorized `checking -> completed`
- Verified implementation: `952b39b5fef0fc06e4d28d75bbded24baa5f655f`
- Maker evidence: PBS `2357905.opbs` (1 node) and `2357912.opbs` (2 nodes)
- Completed targets: P03-A01 through P03-A08
- Open target: none
- Checker verdict: `PASS`; `required_gate_followups: none`

### Acceptance summary

| Target | Result | Evidence summary |
|---|---|---|
| P03-A01–A02 | PASS | shared memory/POSIX conformance and immutable conflict evidence |
| P03-A03 | PASS | 100 two-node races; zero double winners and visibility failures |
| P03-A04 | PASS | listing omission did not affect direct head/CAS/get |
| P03-A05 | PASS | Lustre mount/stripe and `directory_fsync=true` capability report |
| P03-A06 | PASS | stable seeded fault schedule/replay digest |
| P03-A07 | PASS | legacy learner/syncer default remained unchanged |
| P03-A08 | PASS | independent publication/error-window audit |

### Checker failure history

#### Attempts at `bfe2fb5` / `6dc7392` — resolved

- Phenomenon: distinct clients using the same expected version and identical
  replacement bytes could all receive success after the first CAS. The backend
  treated every stale same-data call as a lost-response retry.
- Expected/actual: P03-A03 permits at most one winner; actual retry detection
  could not distinguish an independent caller from the original caller.
- Reason: after-effect idempotency was keyed only by expected version and new
  bytes; no request identity was committed with the mutation.
- Impact: P03-A03 and P03-A08.
- Evidence: independent Checker analysis and compute regression retained under
  `artifacts/duraloco/P03/20260711_checker_p03_0a4896e_1node`.
- Resolution: `0a4896e38748cbe33aaefe0d51451df1496b0db7` persists an explicit
  request ID in the atomic envelope. Only the same request ID may identify a
  retry; eight identical-data contenders with distinct IDs produced one
  success in independent PBS `2357892.opbs`.

#### Attempt at `0a4896e` — resolved

- Phenomenon: independent PBS `2357895.opbs` injected EIO, ESTALE, EACCES,
  ENOSPC, and EDQUOT at temp-file and lock setup. Those paths returned raw
  `OSError`/`PermissionError` instead of the storage error taxonomy.
- Expected/actual: D-0305 requires backend-neutral typed errors and retryability
  classification; setup errors escaped before the translation boundary.
- Reason: `_ensure_parent`/`tempfile.mkstemp` ran outside `_publish`'s OSError
  handler, while non-contention `flock` errors were not caught.
- Impact: D-0305, the mandatory P03 fault matrix, and P03-A08.
- Evidence: `artifacts/duraloco/P03/20260711_checker_p03_0a4896e_1node/error_paths_results.json`.
- Resolution: `952b39b5fef0fc06e4d28d75bbded24baa5f655f` translates
  root/parent/temp/lock setup and cleanup failures. Exact independent PBS
  `2357909.opbs` and full independent PBS `2357913.opbs` passed; clean maker
  PBS `2357905.opbs` passed 246 tests with one explicit nightly skip.

### Lustre evidence and limitations

- One-node host `mg0003`: real `/work` Lustre probe passed; directory fsync,
  advisory lock, atomic replace, verified reads, and operation tracing were
  observed.
- Two-node hosts `mg0025` and `mg0026`: 100 races, winner counts 93/7, zero
  double winners, zero visibility failures, and stale-lock takeover passed.
- The evidence does not claim survival of permanent provider loss, every
  controller/MDS failure, or physical durability beyond the documented
  process/OS crash sequence.

### Next action

Start P04 from the completed P03 feature-branch tip; do not merge `main`
automatically.

## 中文

### 状态

- 阶段：P03 — 语义化存储 API 与 POSIX/Lustre contract
- 分支：`codex/duraloco-p03-posix-storage`
- 基线：`codex/duraloco-p02-reference-model`，提交
  `5f03afae833712706814a9c295970a5800a8f04e`
- 已复核持久化提交：`d60ad26dfcf00a060caeadea8cc468977d8c2272`
- 状态：`completed`；最终 Checker 已授权 `checking -> completed`
- 已验证实现：`952b39b5fef0fc06e4d28d75bbded24baa5f655f`
- Maker 证据：PBS `2357905.opbs`（单节点）和 `2357912.opbs`（双节点）
- 已完成 targets：P03-A01 至 P03-A08
- 未完成 target：无
- Checker 结论：`PASS`；`required_gate_followups: none`

### 验收摘要

| Target | 结果 | 证据摘要 |
|---|---|---|
| P03-A01–A02 | PASS | memory/POSIX 共用 conformance 与 immutable conflict 证据 |
| P03-A03 | PASS | 100 轮双节点 race；无 double winner 和 visibility failure |
| P03-A04 | PASS | listing omission 不影响直接 head/CAS/get |
| P03-A05 | PASS | Lustre mount/stripe 与 `directory_fsync=true` capability report |
| P03-A06 | PASS | 稳定的 seeded fault schedule/replay digest |
| P03-A07 | PASS | legacy learner/syncer 默认路径未改变 |
| P03-A08 | PASS | 独立 publication/error-window 审查 |

### Checker 失败历史

#### `bfe2fb5` / `6dc7392` 尝试 — 已解决

- 现象：不同 client 使用同一 expected version 和相同 replacement bytes
  时，第一次 CAS 后的其他调用也可能返回成功。backend 把所有 stale
  same-data 调用都当成丢失响应后的重试。
- 预期/实际：P03-A03 要求最多一个 winner；实际 retry detection 无法区分
  独立 caller 和原 caller。
- 原因：after-effect 幂等性只绑定 expected version 和新 bytes，没有把
  request identity 与 mutation 一起提交。
- 影响：P03-A03 和 P03-A08。
- 证据：独立 Checker 分析和 compute 回归保存在
  `artifacts/duraloco/P03/20260711_checker_p03_0a4896e_1node`。
- 解决：`0a4896e38748cbe33aaefe0d51451df1496b0db7` 在原子 envelope 中持久化
  显式 request ID。只有同一 request ID 可被识别为重试；独立 PBS
  `2357892.opbs` 中八个相同数据、不同 ID 的 contender 只有一个成功。

#### `0a4896e` 尝试 — 已解决

- 现象：独立 PBS `2357895.opbs` 在 temp-file 和 lock setup 注入 EIO、
  ESTALE、EACCES、ENOSPC、EDQUOT；这些路径返回了原始 `OSError`/
  `PermissionError`，没有进入 storage error taxonomy。
- 预期/实际：D-0305 要求 backend-neutral typed error 和 retryability
  分类；实际 setup error 在转换边界之前逸出。
- 原因：`_ensure_parent`/`tempfile.mkstemp` 位于 `_publish` 的 OSError handler
  之外，非 contention 的 `flock` error 也未捕获。
- 影响：D-0305、P03 必需 fault matrix 和 P03-A08。
- 证据：`artifacts/duraloco/P03/20260711_checker_p03_0a4896e_1node/error_paths_results.json`。
- 解决：`952b39b5fef0fc06e4d28d75bbded24baa5f655f` 转换
  root/parent/temp/lock setup 与 cleanup failure。精确独立 PBS `2357909.opbs`
  和完整独立 PBS `2357913.opbs` 均通过；clean Maker PBS `2357905.opbs`
  通过 246 项测试，仅有一个显式 nightly skip。

### Lustre 证据与限制

- 单节点 `mg0003`：真实 `/work` Lustre probe 通过；观测到 directory fsync、
  advisory lock、atomic replace、verified read 和 operation trace。
- 双节点 `mg0025`、`mg0026`：100 轮 race，winner 数 93/7，无 double
  winner、无 visibility failure，stale-lock takeover 通过。
- 该证据不声称可承受永久 provider loss、所有 controller/MDS failure，
  也不把物理 durability 扩展到文档所述 process/OS crash sequence 之外。

### 下一动作

从已完成的 P03 feature-branch tip 开始 P04；不得自动合并 `main`。
