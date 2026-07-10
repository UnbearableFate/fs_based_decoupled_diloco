# P03 Milestone Report

## English

### Status

- Phase: P03 — semantic storage API and POSIX/Lustre contract
- Branch: `codex/duraloco-p03-posix-storage`
- Base: `codex/duraloco-p02-reference-model` at
  `5f03afae833712706814a9c295970a5800a8f04e`
- State: `in_progress`
- Current implementation: `0a4896e38748cbe33aaefe0d51451df1496b0db7`
- Maker evidence: PBS `2357882.opbs` (1 node) and `2357886.opbs` (2 nodes)
- Completed targets: maker evidence for P03-A01 through P03-A08
- Open target: final independent Checker verdict and persistence audit
- Checker verdict: pending; independent PBS `2357892.opbs` passed its counterexamples

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

#### Attempt at `0a4896e` — open

- Phenomenon: independent PBS `2357895.opbs` injected EIO, ESTALE, EACCES,
  ENOSPC, and EDQUOT at temp-file and lock setup. Those paths returned raw
  `OSError`/`PermissionError` instead of the storage error taxonomy.
- Expected/actual: D-0305 requires backend-neutral typed errors and retryability
  classification; setup errors escaped before the translation boundary.
- Reason: `_ensure_parent`/`tempfile.mkstemp` ran outside `_publish`'s OSError
  handler, while non-contention `flock` errors were not caught.
- Impact: D-0305, the mandatory P03 fault matrix, and P03-A08.
- Evidence: `artifacts/duraloco/P03/20260711_checker_p03_0a4896e_1node/error_paths_results.json`.
- Required resolution: translate root/parent/temp/lock setup and cleanup errors,
  add regressions for infrastructure errno classes, then rerun clean maker and
  independent Checker evidence.

### Next action

Obtain the structured independent Checker verdict, persist the bilingual
acceptance report and clean artifacts, then complete the P03 archival commit.

## 中文

### 状态

- 阶段：P03 — 语义化存储 API 与 POSIX/Lustre contract
- 分支：`codex/duraloco-p03-posix-storage`
- 基线：`codex/duraloco-p02-reference-model`，提交
  `5f03afae833712706814a9c295970a5800a8f04e`
- 状态：`in_progress`
- 当前实现：`0a4896e38748cbe33aaefe0d51451df1496b0db7`
- Maker 证据：PBS `2357882.opbs`（单节点）和 `2357886.opbs`（双节点）
- 已完成 targets：P03-A01 至 P03-A08 的 Maker 证据
- 未完成 target：独立 Checker 最终结论与持久化复核
- Checker 结论：待定；独立 PBS `2357892.opbs` 已通过其反例

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

#### `0a4896e` 尝试 — 未解决

- 现象：独立 PBS `2357895.opbs` 在 temp-file 和 lock setup 注入 EIO、
  ESTALE、EACCES、ENOSPC、EDQUOT；这些路径返回了原始 `OSError`/
  `PermissionError`，没有进入 storage error taxonomy。
- 预期/实际：D-0305 要求 backend-neutral typed error 和 retryability
  分类；实际 setup error 在转换边界之前逸出。
- 原因：`_ensure_parent`/`tempfile.mkstemp` 位于 `_publish` 的 OSError handler
  之外，非 contention 的 `flock` error 也未捕获。
- 影响：D-0305、P03 必需 fault matrix 和 P03-A08。
- 证据：`artifacts/duraloco/P03/20260711_checker_p03_0a4896e_1node/error_paths_results.json`。
- 必需修复：转换 root/parent/temp/lock setup 与 cleanup error，增加
  infrastructure errno 回归测试，然后重新运行 clean Maker 和独立 Checker。

### 下一动作

取得结构化独立 Checker 结论，持久化双语验收报告和 clean artifacts，
然后完成 P03 archival commit。
