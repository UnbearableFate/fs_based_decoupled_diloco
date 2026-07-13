# Operational Workflows / 运行工作流

## 1. Run initialization / 运行初始化

**EN**

1. A PBS launcher (e.g. `scripts/miyabi/run_duraloco_p08_d8.pbs`) binds a clean commit
   (`EXPECTED_COMMIT`), a `RUN_ID`, and the storage roots.
2. The first committer candidate calls `initialize_generation`: build the model on CPU, flatten
   trainable parameters, build param/fragment indexes, write derived index files, encode initial
   per-fragment params + outer state, and call `ProductionTransactionalLog.initialize`.
3. Genesis is published as immutable objects (params, outer, frontier, run manifest) and the
   head is created with `create-if-absent`. Racing initializers converge or fail closed on
   `ImmutableConflict`.
4. Learners wait for `param_index.json` / `fragment_index.json` / `latest.json`, then start
   training.

**中文** — PBS 启动脚本绑定干净 commit（`EXPECTED_COMMIT`）、`RUN_ID` 与存储根；第一个
committer 候选执行 `initialize_generation`（CPU 上构建模型、平铺可训练参数、构建参数/
fragment 索引、写派生索引文件、编码初始 params + outer state，调用
`ProductionTransactionalLog.initialize`）；genesis 以不可变对象发布，head 用 create-if-absent
建立，竞争的初始化者要么收敛要么在 `ImmutableConflict` 上失败关闭；learner 等到
`param_index.json` / `fragment_index.json` / `latest.json` 就绪后开始训练。

## 2. Becoming the active committer / 成为 active committer

**EN**

1. Load head, read its fencing epoch.
2. Acquire the lease (`observed_fencing_epoch` = head epoch; proposed epoch = observed + 1).
   A fresh lease can only be bootstrapped when no committed epoch exists yet.
3. Force-full strict replay (an authoritative stop observed here ends the candidate).
4. Commit the `epoch_bump` control transition through the normal prepare + head CAS path, then
   replay again and verify the committed coordination projection names this owner.
5. Only now is the owner token activated; every subsequent authoritative stage renews the lease
   first (`_renew_for_authoritative_stage`), and long substages run in a worker thread while the
   control thread heartbeat-renews.

**中文** — 读 head 取 fencing epoch → 获取 lease（观察 epoch，提议 epoch=观察值+1；只有尚无
已提交 epoch 时才允许自举创建 lease）→ 强制全量 strict replay（此时观察到权威 stop 则候选
结束）→ 通过常规 prepare + head CAS 提交 `epoch_bump` 控制事务，再次 replay 并确认已提交的
协调投影指向本 owner → 至此 owner token 才被激活；此后每个权威阶段先续租
（`_renew_for_authoritative_stage`），长子阶段在 worker 线程中运行、控制线程按节拍续租。

## 3. Steady-state loop / 稳态循环

**EN** — Per transition the active committer: checks `stop_after_outer_steps`; renews the lease
on schedule; consumes any membership-reconfiguration request; picks the fragment from the
committed scheduler cursor; scans/validates/selects proposals (grace window up to quorum);
publishes FWO + input bundle + the derived `active_work_order.json` dispatch record; waits for
the required prepared attempts; decides duplicates; validates the winner; prepares and CASes the
successor; post-CAS replays; optionally runs a lifecycle cycle (`--lifecycle-cadence N`); and
materializes derived views. Meanwhile each learner loops: train interval → publish proposal →
adopt newest committed fragments at the boundary.

**中文** — 每次 transition，active committer 依次：检查 `stop_after_outer_steps`；按节拍续租；
消费 membership 重构请求；按已提交调度游标选 fragment；扫描/验证/选择 proposal（grace 窗口内
凑 quorum）；发布 FWO + input bundle + 派生 `active_work_order.json` 派发记录；等待所需
prepared attempt；重复裁决；验证胜者；prepare 并 CAS 后继；CAS 后 replay；按
`--lifecycle-cadence N` 可选执行 lifecycle 周期；物化派生视图。与此同时每个 learner 循环：
训练 interval → 发布 proposal → 在边界采用最新已提交 fragment。

## 4. Failure & takeover / 故障与接管

**EN**

- **Committer crash.** The standby polls; it may acquire only after
  `lease.expires_at + max_clock_skew`. With TTL=45 s / renew=10 s / skew=2 s the safe wait is
  ≈37–47 s depending on renewal phase. It then epoch-bumps and empty-cache strict-replays.
  H0 measured worst-case failure→next-commit of 89.44 s end to end.
- **Executor loss.** Failure evidence (observational) marks the member failed in the dispatch
  record; surviving owners of the FWO carry on; with factor 2 the backup path
  (warm_standby / active_active / hedged) provides the second attempt.
- **Whole learner-host loss.** A reconfiguration request (derived, verified against committed
  membership) makes the committer commit membership revision N+1; ownership is re-derived;
  the lost learner's un-consumed proposals simply stop being selected.
- **Learner process restart.** Warm recovery: re-derive session, adopt the newest frontier,
  optionally resolve uncommitted-interval backpressure; or exact recovery from a capsule
  (bitwise continuation, validated on synthetic fixtures).
- **CAS ambiguity / response loss.** `resolve_prepared` re-reads the head; if the exact
  prepared head or its commit at the same sequence is committed, report `already_committed`;
  otherwise strict replay decides. Never guessed from local state.

**中文**

- **committer 崩溃。** standby 轮询，只有过了 `lease.expires_at + max_clock_skew` 才能获取
  lease（TTL=45s / renew=10s / skew=2s 时安全等待约 37–47 秒，取决于续租相位），随后
  epoch-bump 并空缓存 strict replay。H0 端到端最坏"故障→下一次提交"为 89.44 秒。
- **executor 丢失。** 观测性故障证据在派发记录中标记失败成员；FWO 的存活 owner 继续；因子 2
  时 backup 路径（warm_standby / active_active / hedged）提供第二次尝试。
- **整机 learner 主机丢失。** 派生的重构请求（对照已提交 membership 验证）促使 committer 提交
  membership revision N+1；所有权重新推导；丢失 learner 的未消费 proposal 自然不再被选中。
- **learner 进程重启。** warm 恢复：重建 session、采用最新 frontier、必要时先解决未提交
  interval 的背压；或从 capsule 做 exact 恢复（逐位延续，已在合成夹具上验证）。
- **CAS 歧义/响应丢失。** `resolve_prepared` 重读 head；若准备好的 head 或同序号的该 commit
  已提交则返回 `already_committed`；否则由 strict replay 裁决。绝不凭本地状态猜测。

## 5. Lifecycle: snapshot, reachability, GC / 生命周期：快照、可达性、GC

**EN** — Every N transitions (`--lifecycle-cadence`) the owner commits an ancestry-pinned
snapshot, runs snapshot+suffix replay, audits it against strict replay (or defers the strict
audit to the terminal one under `--defer-lifecycle-strict-audit`), builds explainable
reachability, and produces a dry-run GC mark. Apply is guarded: reachability is recomputed, and
any head advance, new pin, or mark mismatch invalidates the apply. For real authority
namespaces the CLI intentionally only supports reachability + dry-run marks; destructive apply
is restricted to `--namespace synthetic` plus an approval token. The system keeps two
independent valid restore bases before allowing older prefix objects to become candidates.

**中文** — 每 N 次 transition（`--lifecycle-cadence`）owner 提交一个 ancestry-pinned
snapshot，执行 snapshot+suffix replay 并对照 strict replay 审计（或用
`--defer-lifecycle-strict-audit` 推迟到终局审计），构建可解释可达性，产出 dry-run GC mark。
apply 受保护：重新计算可达性，head 前进、新 pin 或 mark 不一致都会使 apply 失效。对真实权威
命名空间，CLI 有意只支持可达性与 dry-run mark；破坏性 apply 仅限 `--namespace synthetic` 加
审批 token。系统保留两个独立有效恢复基点后，更老的前缀对象才可能成为回收候选。

## 6. Stop, error, resume / 停止、错误、恢复

**EN** — Normal completion (`stop_after_outer_steps`, terminal drain, or no-progress timeout)
commits an optional terminal snapshot, then a `stop` control transition, then optionally runs
the terminal strict audit (fresh strict replay vs snapshot replay) and writes derived
`stop.json`. On error, the owner (if still fenced) commits `stop(reason=error)`; under the
error-resume protocol a later candidate may commit a `resume` under a higher epoch instead of
treating the run as terminal. Lease-authority loss skips stop publication entirely — a fenced
successor will decide.

**中文** — 正常完成（`stop_after_outer_steps`、终局排空或无进展超时）时：可选提交终局
snapshot → 提交 `stop` 控制事务 → 可选执行终局 strict 审计（新鲜 strict replay 与 snapshot
replay 对照）→ 写派生 `stop.json`。出错时，仍持有围栏的 owner 提交 `stop(reason=error)`；在
error-resume 协议下，后来的候选可以在更高 epoch 下提交 `resume` 而不是把运行当作终局。丢失
lease 权威时完全跳过 stop 发布 —— 由持围栏的继任者裁决。

## 7. Verification workflow / 验证工作流

**EN** — Login nodes may only run static checks: `bash -n` on PBS scripts, `ruff`, and the
`scripts/agent/` contract checkers (research contract, docs, no-embedded-database). Runtime
validation escalates 1-node → 2-node → 8-node inside PBS allocations, and a phase is complete
only when an independent checker reports PASS on the required acceptance IDs. Offline, the
committed log can always be re-verified with:

```bash
python -m fs_diloco.log.inspect_cli verify --root <shared>/authority --run-id <run> --generation 0
python -m fs_diloco.log.inspect_cli replay --root <shared>/authority --run-id <run> --generation 0
python -m fs_diloco.log.inspect_cli orphans --root <shared>/authority --run-id <run> --generation 0
```

**中文** — 登录节点只允许静态检查：对 PBS 脚本 `bash -n`、`ruff`、以及 `scripts/agent/` 契约
检查（research contract、docs、无嵌入式数据库）。运行时验证在 PBS 分配内按 1 节点 → 2 节点 →
8 节点递进；只有独立 checker 对全部必需验收 ID 报告 PASS，阶段才算完成。离线时可用上述
inspect CLI 随时重新校验已提交日志。
