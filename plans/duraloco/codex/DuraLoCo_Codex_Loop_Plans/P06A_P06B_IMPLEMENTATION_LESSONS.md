# P06A/P06B 实施经验与 P06C 强制约束

本文件是 P06C 及后续阶段的执行约束，不是事后总结。每一项必须映射到
acceptance、测试和持久化 artifact。

## 1. 已验证基线

- P06A runtime：`5a7150220bf3cc6a4a46d2a563466335163d21ad`；
- P06A Checker：PBS `2362185.opbs`，`PASS`；
- P06B runtime：`d5e2901b75ef504a31a365790b7b9518c329dbe7`；
- P06B D1/D2/D8：PBS `2362549/2362562/2362567.opbs`，均 `PASS`；
- P06B D8：8 个 learner node、零 dedicated syncer、50×10、470 秒；
- P06B C9/D8 comparison：PBS `2362603.opbs`，`PASS`。

这些是 observed baseline。P06C 不得把 P06B pass 直接复用为 factor-2 pass；必须保留
factor-1 regression cell，并对 factor-2 的 correctness、成本和负面结果分别下结论。

## 2. 已发生错误：现象、原因、修复与后续约束

### E-P06A-01：terminal cleanup 与 marker-last publication 竞争

- 现象：第一次 final C2 中，新 tensor 已 rename，但 metadata marker 尚未发布时被 terminal
  cleanup 删除；后续验证看到缺失 payload。
- 原因：cleanup 把“当前 listing 中没有配对 marker”等价成“对象已 orphan”，没有考虑
  writer 的 marker-last 临界区。
- 解决：为新鲜未配对对象增加有界 grace；显式 zero-grace 仅用于针对性测试。
- P06C 约束：winner/loser PFT 都不得在 P07 reachability/retention contract 前 destructive
  cleanup；kill-before-marker 必须保留 expected orphan evidence。

### E-P06B-01：POSIX storage envelope 被误当作 raw JSON

- 现象：comparison 在读取 `*.json` 时抛出 `UnicodeDecodeError`，文件开头为
  `FSDILOCO-STORAGE-V1`。
- 原因：分析脚本绕过 `PosixStorageBackend.get`，把物理 envelope 当成 logical payload。
- 解决：所有 authority object 通过 storage backend 解包并做 canonical validation。
- P06C 约束：analysis/checker 禁止直接 `Path.read_text()` 读取 authority payload；必须从
  backend 或 committed replay API 取 logical bytes。

### E-P06B-02：listing 中的 immutable commit 被误当作 committed ancestry

- 现象：comparison 报告 distributed control sequence 为
  `epoch_bump, stop, epoch_bump`；其中最后一个是同序号 CAS-loser orphan，不在 head ancestry。
- 原因：脚本扫描 `immutable/commits/*.json`，没有从 single global head 反向 fold。
- 解决：comparison 改为 `ProductionTransactionalLog.replay(force_full=True).commits`。
- P06C 约束：winner、duplicate、epoch、stop 和 inclusion 结论只来自 committed head prefix；
  listing 只用于发现候选/orphan/telemetry，绝不证明 commit。

### E-P06B-03：normal stop 与 standby fence 的末端竞争

- 现象：active 已完成第十个 transition；standby 获得 observational lease 后准备 epoch bump，
  与 authoritative stop 竞争。安全层拒绝了 bump，但 standby 进程曾以 traceback 退出。
- 原因：post-lease strict replay 与 `activate_owner` 之间仍存在不可消除的 TOCTOU 窗口；只做
  一次“stop 检查”不能证明下一条 CAS 前 stop 不会提交。
- 解决：保留 post-lease empty-cache strict replay，并将 `activate_owner` 的 stop-specific
  `CommitConflict` 通过新 committed head 解析为正常 terminal race；非 stop conflict 继续失败。
- P06C 约束：任何 check-then-CAS 都必须在 CAS conflict 后按 committed ancestry 分类；不得
  靠扩大锁或忽略异常修复。false suspicion 与 normal stop 都要有显式 terminal event。

### E-P06B-04：comparison RunSpec 路径与 envelope 层级假设错误

- 现象：先找不到 `run_spec.json`，改找 `run-manifest.json` 后又出现 `KeyError: run_id`。
- 原因：RunSpec 位于 storage-wrapped RunManifest 的 `spec` 字段，而非独立文件/root 字段。
- 解决：从 `control/run-manifest.json` 解包后读取严格 `spec`，并分别记录 CUDA CRS 与 CPU
  LFE backend identity。
- P06C 约束：先用 schema/typed API 定位对象，再写分析；禁止靠文件名猜测 schema root。

## 3. 执行优化

1. 先完成纯 schema/identity/property gate，再接入进程和 PBS；
2. 将 duplicate validation 做成 dependency-free kernel，committer 只负责发现与裁决；
3. P06C 先用 tiny tensor D1-R2 穷举 arrival/crash permutation，再运行真实 GPT-2 D1；
4. D2-R2 将 failure tape 分成 primary kill、backup kill、committer kill、whole-node kill、
   combined kill，单个 tape 未通过时不进入 D8-R2；
5. D8-R2 只在同一 clean commit 的 unit→D1-R2→D2-R2 完整通过后提交；
6. strict replay、large-object compare 和 report fold 作为独立 stage 计时，避免把 terminal
   evidence generation 误判为训练 hang；
7. 每个预期失败注入必须使用 `expected_blocked`/`expected_rejection` 独立分类，不能通过
   shell `|| true` 抹掉意外异常。

## 4. 错误即时报告协议

执行中一旦出现非预期错误，必须在继续修复前形成一条 error record，并及时向用户报告：

```yaml
error_id: E-P06C-YYYYMMDD-NN
phase_and_gate: P06C/<unit|D1-R2|D2-R2|D8-R2|checker>
time_and_job: <UTC/JST time, PBS job id, hosts, commit>
phenomenon: <实际报错、exit code、terminal state、关键日志位置>
expected: <预期行为>
impact: <影响的 acceptance/invariant；已提交 prefix 是否仍安全>
cause:
  confirmed: [<已有直接证据>]
  unknown: [<尚未证明的部分>]
repair: <代码/配置/流程修复>
verification: <最小复现、随后 unit/D1/D2 资格验证>
retry_decision: <是否允许重提及依据>
artifacts: [<manifest/log/review paths>]
```

报告必须区分 confirmed 与 hypothesis，不得用“可能是”替代根因验证。若是 non-transient
D8-R2 terminal failure，严格执行 workflow review→最小 benchmark→同 commit D1-R2→D2-R2→
一次 D8-R2 retry，不得立即重提同 shape。
