# P00–P04 实施经验与后续阶段强化约束

本文从 `plans/duraloco/phases/P00_PHASE_REPORT.md`至
`P04_PHASE_REPORT.md`、`P04_DRIFT_REPORT.md`、阶段状态、独立 Checker
报告以及 `artifacts/duraloco/P00`至`P04` 的 manifests/运行记录中
提取已由实际失败和修复验证的经验。M00 及后续阶段必须把
这些经验当作必需 gate，而不是可选建议。

## 1. 幂等性必须绑定请求身份

P03 曾把“相同 expected version + 相同 bytes”的独立调用错误归类为
丢响应重试，导致多个 CAS winner。修复后，只有持久化的相同
`request_id` 才可识别为 after-effect retry。因此：

- lease acquire/renew/release、proposal publication、head CAS、delete、multipart
  complete/abort 等每个可重试 mutation 都必须有稳定 request identity；
- 必须同时测试“同 ID 同内容”、“不同 ID 同内容”和“同 ID 不同内容”；
- 不允许用 payload equality、当前可见状态或调用者推测替代 request identity。

## 2. 恢复必须检查权威历史，不只检查当前 head

P04 曾在 successor 已推进 head 后无法识别很晚到达的 CAS 成功
丢响应重试。修复通过验证 prepared commit/frontier 是否已在权威
ancestry 中解决。因此后续 reconciliation 必须：

- 区分当前 head equality、已提交 ancestry、未提交 orphan 和真正 conflict；
- 覆盖“响应丢失 → 后续成功推进 → 原请求延迟重试”的反例；
- 重启、takeover、stop、adoption 和 lifecycle 操作都不得只从可变 cache
  或最新指针推断结果。

## 3. 一种语义只能有一个可执行实现路径

P02 曾出现 `select_quorum` 遵守 oldest-first，而 trace replay 使用另一套
lexical-first 逻辑的偏差。后续阶段必须：

- simulator、runtime、replay、recovery 和 Checker 共用同一 policy kernel，或用
  双向 equivalence/mutant tests 证明两个实现一致；
- 新增 fairness、adoption、GC roots 或 controller policy 时，必须保留一个
  可最小化的确定性反例和稳定 replay digest；
- 不得用“正常顺序下结果一致”替代 adversarial ordering/interleaving。

## 4. fail-closed 边界必须包围整个操作

P01 在 deep JSON/header、host-language container/type、nested mutability 和 byte
snapshot 上曾出现缺口；P03 的 temp/parent/lock setup 与 cleanup 曾泄漏原始
`OSError`。因此：

- typed error/retryability 翻译必须覆盖 validation、setup、publication、lock、
  cleanup 和 inspect/recovery，不只是 happy-path 核心调用；
- 做决策时使用一个 immutable byte/state snapshot，防止验证与使用之间变化；
- 每个外部边界都要注入 retryable/non-retryable infrastructure errors、
  malformed/deep input 和 cleanup failure。

## 5. 证据生命周期是 correctness gate 的一部分

P04 的首次独立 Checker 虽未发现事务安全缺陷，仍因当前测试/
状态/双语报告不同步和 retry lineage 缺失而 `BLOCKED`。P00 也曾修复
stale evidence references、bundle checksum 和 missing retry parent。因此：

- 每次已提交的 PBS/本地尝试，包括 fail、inconclusive、排队后取消和
  未分配节点的尝试，都必须有不可变 manifest 和结果/取消原因；
- 同一 validation shape 的重试使用新 `run_id`，并用 `parent_run_id`
  指向前一尝试；不得仅在报告散文中提到失败前任；
- 实现、回归测试、`STATE.yaml`、双语 report、acceptance mapping 和
  checksums 必须在同一个最终目标提交上同步为绿；
- 机器可读的 manifest/state 字段是主验证面；双语报告保留人类可审计
  摘要，不应使用只存在于自由文本的脆弱标记替代结构化证据。

## 6. 最终 Checker 必须针对最终干净提交重放当前套件

早期的通过证据不能替代最终 target 的验证。每个后续 phase 必须：

- Maker 在最终干净 commit 上重跑受影响的最小套件和必需 1/2/9-node
  shape，不得把旧 commit 的成功结果直接冒充新 commit 证据；
- Checker 必须从最终 commit 运行当前持久化套件，重跑至少一个
  历史失败的精确反例和一个新反例；
- 仅当 Checker 的结构化 verdict 无 required-gate follow-up，且最终
  report/state/manifest 已持久化时才允许 `checking -> completed`。

## 7. 真实 backend 证据必须同时记录 capability 和 non-claim

P03 验证了 Lustre 上的 directory fsync、advisory lock、atomic replace 和
两节点 race，但明确不将结论扩大到 permanent provider loss、所有 MDS/
controller failure 或物理介质保证。后续阶段必须：

- 记录 mount/filesystem/stripe/module/capability probe 与 fail-closed downgrade；
- 把 mock、memory、POSIX/Lustre、MinIO 和 public cloud 证据分层；
- 在 checker report 和论文 evidence 中同时写明 supported claim 和 non-claim。

## 8. PBS 排队与取消也是可复现执行记录

P04 的首个 9-node regular-queue 作业因预计等待超过一小时而在分配前
取消，随后在不放宽 commit/config/walltime/assertions 的前提下切换到
`debug-g` 完成。后续计划必须：

- 保存 submission host、queue、job ID、请求资源、观测的排队状态、
  取消原因与是否获得 allocation；
- 切换 queue 或重提交时保持相同 verified commit/config/gates，并建立
  `parent_run_id` lineage；
- 资源等待不得被写成 runtime failure，runtime failure 也不得被排队切换
  掩盖。

## 9. 与后续阶段的对应

| 经验 | 必须落地的阶段 |
|---|---|
| request identity 与 response-loss 辨识 | M00、P05、P06、P07、可选 P09 |
| ancestry-aware reconciliation | M00、P05、P06、P07、P11 |
| 单 policy kernel/replay equivalence | P06、P08、P10、P12 |
| 全边界 typed failure 与 immutable snapshot | P05–P08、P10–P12、可选 P09 |
| manifest retry lineage、state/report 同步、最终 commit Checker | M00 及所有后续阶段 |
| backend capability/non-claim | P05、P07、P08、P11、P12、可选 P09 |
| queue/cancel/resubmit provenance | 所有 Miyabi runtime 阶段 |
