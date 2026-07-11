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

The implementation removes the legacy persistence surface, adds
the production safetensors transaction path, replay-derived `RuntimeView`,
re-entrant proposal catalog, file-native analysis, explicit warm-start
generation metadata, and M00 static/runtime harnesses. Static source/config/
script/test scanning passes. The clean one-node qualification now passes;
two-node and nine-node compute qualification remain in progress.

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

#### Maker attempt 3 — `20260711_m00_04da7ee_1node`

- Time/identity: PBS `2359079.opbs`, host `mg0027`, implementation
  `04da7ee01b69f66cac60a7e2d9173b3738b82ef4`.
- Phenomenon: forbidden scanning, all 270 tests, and the one-node P04
  crash/replay contract passed. The full-process smoke then committed its first
  transition but replay rejected transition two as a duplicate same-base
  learner interval.
- Expected/actual: only one proposal from each learner/session/fragment/base
  interval may be logically included. Production preparation admitted another
  proposal from an already consumed interval, so replay correctly failed
  closed.
- Reason: confirmed. The reference path enforced same-base overlap during
  prepare, while the initial production adapter only checked proposal ID,
  ancestry, and staleness. The fast full learner also polled latest once and
  could finish several overlapping intervals before seeing the committed
  successor.

#### Maker attempt 4 — `20260711_m00_97a6876_1node` — PASS

- Time/identity: PBS `2359082.opbs`, host `mg0027`, implementation
  `97a687698c4b8964bbf4891d0d2e070358b831dd`.
- Result: forbidden scanning passed; the dependency-complete suite passed with
  `270 passed, 1 skipped`; the reference POSIX crash/replay contract passed at
  10 commits; both production full and fragment paths completed; deleting all
  derived latest/stop/weights/outer-state/fragment exports and starting a new
  syncer process reconstructed the same committed-state digest.
- Exact evidence: full path committed 2 transitions and consumed 4 proposals;
  fragment path committed 4 transitions and consumed 8 proposals. The before
  and after recovery digests were respectively identical for both paths.
- Evidence: `artifacts/duraloco/M00/20260711_m00_97a6876_1node/manifest.json`,
  `one_node_contract.json`, and the full/fragment `*_before_recovery.json` and
  `*_after_recovery.json` reports.

#### Two-node qualification — `20260711_m00_81b442c_2node` — PASS

- Time/identity: PBS `2359105.opbs`, hosts `mg0030` and `mg0033`, implementation
  `81b442c80c60f222555d5aeb773fcafa69672ae8`.
- Backend result: 100 same-version POSIX/Lustre races produced exactly one
  winner per round, zero visibility failures, and successful stale-lock
  takeover.
- Transaction result: 20 same-parent races produced exactly 20 committed
  transitions, zero double winners, zero double inclusions, identical replay
  digests on both nodes, recovered response loss, and second-node continuation.
- Production takeover result: the first production process committed sequence
  1 and exited; a fresh process on the second node recovered the identical
  `RuntimeView` digest and appended sequence 2 through the production head CAS.
  No local database file was created.
- Evidence: `artifacts/duraloco/M00/20260711_m00_81b442c_2node/manifest.json`,
  `two_node_summary.json`, rank reports, and operation traces.

#### Nine-node attempt 1 — `20260711_m00_dec182e_gpt2_9n_50x10`

- Time/identity: PBS `2359108.opbs`, nine compute hosts led by `mg0888`,
  implementation `dec182eaefd20c02a6eea79fb0493cd0d41d9bd2`.
- Phenomenon: all real GPT-2/WikiText-2 processes initialized and each learner
  published its first 50-step proposal, but no transition completed before the
  learners resumed from the unchanged committed base. At operator termination,
  64 same-base metadata/payload pairs occupied about 32 GB.
- Expected/actual: after publishing an interval, a learner must wait for a
  committed successor before opening another interval. The bounded one-scan
  adoption wait expired while the syncer was validating multi-gigabyte payloads,
  so learners repeatedly produced proposals from commit sequence 0.
- Reason: confirmed. The small synthetic gate hid the payload-validation
  latency. The catalog also read already-consumed payloads before applying its
  cheap committed-interval rejection, which would scale poorly after recovery.
- Impact: M00-A11 only; no head CAS occurred and no committed prefix was
  corrupted. The operator terminated the job deliberately (`Exit_status=271`).
- Evidence: `artifacts/duraloco/M00/20260711_m00_dec182e_gpt2_9n_50x10/manifest.json`,
  `training.log`, and `qstat_final.log`.
- Repair: make post-upload adoption wait through the no-progress budget or a
  stop marker, and reject known consumed interval bases before payload reads.

#### Nine-node attempt 2 — `20260711_m00_342e975_gpt2_9n_50x10`

- Time/identity: PBS `2359122.opbs`, nine compute hosts led by `mg1078`,
  implementation `342e97514ef43643e5f447da79afd3e067c91522`.
- Phenomenon: committed-successor backpressure worked: exactly eight initial
  proposals remained and no same-base flood occurred. However, the first
  transition still did not complete before deliberate operator termination.
- Expected/actual: strict finite-value validation must scale to a GPT-2 flat
  tensor. The dependency-free validator iterated roughly 124 million scalar
  float values in Python for each proposal, so eight payloads could not clear
  the first scan within the terminal budget.
- Reason: confirmed by the stable eight-proposal count, zero successor, and the
  validator's scalar `struct.iter_unpack` loop. This path is appropriate for
  dependency-free protocol fixtures, not large production tensors.
- Impact: M00-A11 only; no head CAS occurred and the operator terminated the
  job deliberately (`Exit_status=271`).
- Evidence: `artifacts/duraloco/M00/20260711_m00_342e975_gpt2_9n_50x10/manifest.json`,
  `training.log`, and `qstat_final.log`.
- Repair: keep the strict structural parser and SHA checks, but perform the
  production finite-value pass with safetensors/Torch vectorized validation.

#### Nine-node attempt 3 — `20260711_m00_2d572d4_gpt2_9n_50x10`

- Time/identity: PBS `2359156.opbs`, nine compute hosts led by `mg1078`,
  implementation `2d572d47319627353850b0ce044fc77152098b92`. The same clean commit
  first passed requalification jobs `2359153.opbs` (one node) and
  `2359155.opbs` (two nodes).
- Phenomenon: vectorized validation allowed the first eight-proposal production
  transition to commit exactly once, and all learners adopted sequence 1. The
  first transition nevertheless took about 105 seconds after proposal publish,
  making ten transitions incompatible with the 15-minute hard gate.
- Expected/actual: each payload should be validated once per scan. Instead the
  scanner validated it, `load_payload` reread/revalidated it, and
  `publish_proposal` performed a third validation before immutable publication.
- Reason: confirmed from the three call sites and the first-transition timing.
- Impact: M00-A11 only; the committed sequence-1 prefix is valid. The operator
  terminated the job deliberately (`Exit_status=271`).
- Evidence: `artifacts/duraloco/M00/20260711_m00_2d572d4_gpt2_9n_50x10/manifest.json`,
  `training.log`, plus the same-commit one/two-node requalification manifests.
- Repair: retain the immutable validated bytes in `CatalogEntry` and pass a
  typed validation result into production publication, eliminating rereads and
  redundant finite-value scans without weakening structural/SHA validation.

#### Nine-node attempt 4 — `20260711_m00_c1c2404_gpt2_9n_50x10`

- Time/identity: PBS `2359165.opbs`, nine compute hosts led by `mg1078`,
  implementation `c1c2404afdd6a228a47a09c83b703c9ba53f2f6d`. The same clean commit
  passed jobs `2359162.opbs` (one node) and `2359164.opbs` (two nodes).
- Phenomenon: cached validated bytes removed the scan/load/publish rereads, but
  the first transition still took roughly 100 seconds. It committed exactly
  once and all learners adopted it before deliberate termination.
- Expected/actual: a vectorized finite check was expected to remove the scalar
  bottleneck. It ran on the Grace CPU, where checking eight 124-million-element
  tensors remained dominant even without redundant calls.
- Reason: confirmed by unchanged first-transition timing after eliminating the
  duplicate call sites and by the validation tensor remaining on CPU.
- Impact: M00-A11 only; the committed sequence-1 prefix is valid. The operator
  terminated the job deliberately (`Exit_status=271`).
- Evidence: `artifacts/duraloco/M00/20260711_m00_c1c2404_gpt2_9n_50x10/manifest.json`,
  `training.log`, and same-commit one/two-node manifests.
- Repair: pass the syncer's selected compute device into the production catalog
  and execute large vectorized finite checks on GPU; CPU remains the default for
  small fixtures and non-accelerated paths.

#### Nine-node attempt 5 — `20260711_m00_d3a7dce_gpt2_9n_50x10`

- Time/identity: PBS `2359172.opbs`, nine compute hosts led by `mg1078`,
  implementation `d3a7dce861fdb564b4904b7801588e129bdceb06`. The same clean commit
  passed jobs `2359170.opbs` (one node) and `2359171.opbs` (two nodes).
- Phenomenon: GPU finite checks preserved correctness but did not materially
  reduce the approximately 100-second first-transition latency. Sequence 1
  committed exactly once before deliberate termination.
- Expected/actual: after moving finite checks to GPU, the remaining eight
  500 MB payload reads and SHA calculations were still serialized by the
  catalog scan.
- Reason: confirmed by the unchanged transition timing and sequential scan
  implementation; validation is independent across learner proposals.
- Impact: M00-A11 only; the committed sequence-1 prefix is valid. The operator
  terminated the job deliberately (`Exit_status=271`).
- Evidence: `artifacts/duraloco/M00/20260711_m00_d3a7dce_gpt2_9n_50x10/manifest.json`,
  `training.log`, and same-commit one/two-node manifests.
- Repair: perform independent catalog candidate read, SHA, structural, and
  finite validation concurrently while preserving deterministic result order
  and serializing quarantine registry writes.
- Impact: M00-A03, M00-A04, M00-A09, P02-A04, and P04 replay requalification.
- Evidence: `artifacts/duraloco/M00/20260711_m00_04da7ee_1node/manifest.json`,
  `one_node_contract.json`, full syncer/learner logs, and `stdout.log`.
- Repair: carry consumed interval bases in `RuntimeView`, filter them in the
  catalog, enforce them again at production prepare, and let learners configured
  for post-upload adoption wait through one scan/grace window for a successor.

### Limitations and next action

M00 still assumes one active syncer. Lease/fencing begins in P05; learner exact
restart and authoritative GC remain later work. Next action is the clean
nine-node GPT-2/WikiText-2 50×10 terminal gate.

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
扫描已通过；干净单节点资格验证也已通过，双节点与九节点 compute 再验收仍在进行。

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

#### Maker 第 3 次尝试 — `20260711_m00_04da7ee_1node`

- 时间/身份：PBS `2359079.opbs`，节点 `mg0027`，实现提交
  `04da7ee01b69f66cac60a7e2d9173b3738b82ef4`。
- 现象：forbidden scan、270 个 tests 与单节点 P04 crash/replay contract 均通过；
  full process smoke 提交第一个 transition 后，replay 将第二个 transition 判为重复
  same-base learner interval 并 fail closed。
- 预期/实际：每个 learner/session/fragment/base interval 最多逻辑包含一个 proposal；
  production prepare 实际允许了已消费 interval 的另一个 proposal，replay 正确拒绝。
- 原因：已证实。reference prepare 已检查 same-base overlap，初版 production adapter
  只检查 proposal ID、ancestry 与 staleness。快速 full learner 只轮询 latest 一次，
  也可能在看到 committed successor 前完成多个重叠 interval。
- 影响：M00-A03、M00-A04、M00-A09、P02-A04 与 P04 replay 再验收。
- 证据：`artifacts/duraloco/M00/20260711_m00_04da7ee_1node/manifest.json`、
  `one_node_contract.json`、full syncer/learner logs 与 `stdout.log`。
- 修复：`RuntimeView` 携带 consumed interval bases，catalog 过滤，production prepare
  再次强制；配置 post-upload adoption 的 learner 在一个 scan/grace window 内等待
  successor。

#### Maker 第 4 次尝试 — `20260711_m00_97a6876_1node` — PASS

- 时间/身份：PBS `2359082.opbs`，节点 `mg0027`，实现提交
  `97a687698c4b8964bbf4891d0d2e070358b831dd`。
- 结果：forbidden scan 通过；dependency-complete suite 为 `270 passed, 1 skipped`；
  reference POSIX crash/replay contract 在 10 个 commits 上通过；production full 与
  fragment 两条路径均完成。删除全部派生 latest/stop/weights/outer-state/fragment exports
  后启动新 syncer 进程，重建的 committed-state digest 保持一致。
- 精确证据：full 路径提交 2 个 transitions、消费 4 个 proposals；fragment 路径提交
  4 个 transitions、消费 8 个 proposals；两条路径的恢复前后 digest 均分别一致。
- 证据：`artifacts/duraloco/M00/20260711_m00_97a6876_1node/manifest.json`、
  `one_node_contract.json`，以及 full/fragment 的 `*_before_recovery.json` 与
  `*_after_recovery.json` 报告。

#### 双节点资格验证 — `20260711_m00_81b442c_2node` — PASS

- 时间/身份：PBS `2359105.opbs`，节点 `mg0030` 与 `mg0033`，实现提交
  `81b442c80c60f222555d5aeb773fcafa69672ae8`。
- Backend 结果：100 轮同 version POSIX/Lustre race 每轮恰好一个 winner，跨节点可见性
  失败为零，stale-lock takeover 成功。
- Transaction 结果：20 轮同 parent race 恰好产生 20 个 committed transitions，
  double winner 与 double inclusion 均为零；两节点 replay digest 一致，并验证了
  response-loss recovery 与第二节点 continuation。
- Production takeover 结果：首个 production 进程提交 sequence 1 后退出；第二节点上
  的新进程恢复完全一致的 `RuntimeView` digest，并经 production head CAS 追加 sequence 2；
  未产生任何本地数据库文件。
- 证据：`artifacts/duraloco/M00/20260711_m00_81b442c_2node/manifest.json`、
  `two_node_summary.json`、各 rank 报告与 operation traces。

#### 九节点第 1 次尝试 — `20260711_m00_dec182e_gpt2_9n_50x10`

- 时间/身份：PBS `2359108.opbs`，以 `mg0888` 为首的九个 compute nodes，实现提交
  `dec182eaefd20c02a6eea79fb0493cd0d41d9bd2`。
- 现象：真实 GPT-2/WikiText-2 的全部进程均完成初始化，每个 learner 也发布了首个
  50-step proposal；但在 transition 完成前，learner 已从未改变的 committed base
  继续训练。人工终止时共有 64 组 same-base metadata/payload，约占 32 GB。
- 预期/实际：learner 发布一个 interval 后必须等到 committed successor 才能开启下个
  interval。实际 bounded one-scan adoption wait 在 syncer 校验多 GB payload 时超时，
  learner 因而反复从 commit sequence 0 产生 proposal。
- 原因：已证实。小型 synthetic gate 未暴露 payload-validation latency；catalog 也在
  进行廉价的 committed-interval rejection 前读取已消费 payload，恢复后的扩展性不足。
- 影响：仅 M00-A11；未发生 head CAS，也未损坏 committed prefix。该 job 由 operator
  主动终止（`Exit_status=271`）。
- 证据：`artifacts/duraloco/M00/20260711_m00_dec182e_gpt2_9n_50x10/manifest.json`、
  `training.log` 与 `qstat_final.log`。
- 修复：post-upload adoption 等待延长至 no-progress budget 或 stop marker；并在读取
  payload 前拒绝已知 consumed interval base。

#### 九节点第 2 次尝试 — `20260711_m00_342e975_gpt2_9n_50x10`

- 时间/身份：PBS `2359122.opbs`，以 `mg1078` 为首的九个 compute nodes，实现提交
  `342e97514ef43643e5f447da79afd3e067c91522`。
- 现象：committed-successor backpressure 生效，始终只有最初 8 个 proposals，没有
  same-base flood；但在人工终止前首个 transition 仍未完成。
- 预期/实际：严格 finite-value validation 必须可扩展到 GPT-2 flat tensor。实际
  dependency-free validator 对每个 proposal 以 Python 循环遍历约 1.24 亿个 float，
  8 个 payload 无法在 terminal budget 内完成首次 scan。
- 原因：由稳定的 8-proposal 数、零 successor 与 validator 中标量
  `struct.iter_unpack` 循环共同证实。该路径适用于无依赖 protocol fixture，不适合大型
  production tensor。
- 影响：仅 M00-A11；未发生 head CAS，operator 主动终止 job（`Exit_status=271`）。
- 证据：`artifacts/duraloco/M00/20260711_m00_342e975_gpt2_9n_50x10/manifest.json`、
  `training.log` 与 `qstat_final.log`。
- 修复：保留严格结构 parser 与 SHA 校验，但 production finite-value pass 改用
  safetensors/Torch 向量化验证。

#### 九节点第 3 次尝试 — `20260711_m00_2d572d4_gpt2_9n_50x10`

- 时间/身份：PBS `2359156.opbs`，以 `mg1078` 为首的九个 compute nodes，实现提交
  `2d572d47319627353850b0ce044fc77152098b92`。同一干净提交先通过了
  `2359153.opbs`（单节点）与 `2359155.opbs`（双节点）再验收。
- 现象：向量化验证使首个含 8 proposals 的 production transition 恰好提交一次，
  全部 learner 也采用了 sequence 1；但从 proposal publish 到首个 transition 仍约需
  105 秒，无法在 15 分钟 hard gate 内完成 10 个 transitions。
- 预期/实际：每个 payload 每轮只应验证一次。实际 scanner 验证一次，`load_payload`
  再次读取/验证，`publish_proposal` 在 immutable publication 前第三次验证。
- 原因：由三个调用点与首个 transition timing 共同证实。
- 影响：仅 M00-A11；已提交 sequence-1 prefix 合法。operator 主动终止 job
  （`Exit_status=271`）。
- 证据：`artifacts/duraloco/M00/20260711_m00_2d572d4_gpt2_9n_50x10/manifest.json`、
  `training.log`，以及同 commit 单/双节点再验收 manifests。
- 修复：在 `CatalogEntry` 保留 immutable validated bytes，并将 typed validation result
  直接交给 production publication；在不削弱结构/SHA 验证的前提下消除重复读取与
  finite-value scan。

#### 九节点第 4 次尝试 — `20260711_m00_c1c2404_gpt2_9n_50x10`

- 时间/身份：PBS `2359165.opbs`，以 `mg1078` 为首的九个 compute nodes，实现提交
  `c1c2404afdd6a228a47a09c83b703c9ba53f2f6d`。同一干净提交通过了
  `2359162.opbs`（单节点）与 `2359164.opbs`（双节点）。
- 现象：缓存 validated bytes 已消除 scan/load/publish 重读，但首个 transition 仍约需
  100 秒；该 transition 恰好提交一次，全部 learner 采用后才被人工终止。
- 预期/实际：向量化 finite check 原应消除标量瓶颈；实际它运行于 Grace CPU，对 8 个
  各约 1.24 亿元素 tensor 的检查即使不重复仍是主要耗时。
- 原因：消除重复调用后首个 transition timing 基本不变，且 validation tensor 保持在
  CPU，共同证实该原因。
- 影响：仅 M00-A11；已提交 sequence-1 prefix 合法。operator 主动终止 job
  （`Exit_status=271`）。
- 证据：`artifacts/duraloco/M00/20260711_m00_c1c2404_gpt2_9n_50x10/manifest.json`、
  `training.log` 与同 commit 单/双节点 manifests。
- 修复：将 syncer 选定 compute device 传入 production catalog，大 tensor 的向量化
  finite check 在 GPU 执行；小 fixture 与无 accelerator 路径仍默认 CPU。

#### 九节点第 5 次尝试 — `20260711_m00_d3a7dce_gpt2_9n_50x10`

- 时间/身份：PBS `2359172.opbs`，以 `mg1078` 为首的九个 compute nodes，实现提交
  `d3a7dce861fdb564b4904b7801588e129bdceb06`。同一干净提交通过了
  `2359170.opbs`（单节点）与 `2359171.opbs`（双节点）。
- 现象：GPU finite check 保持正确性，但未显著降低首个 transition 约 100 秒的延迟；
  sequence 1 恰好提交一次后被人工终止。
- 预期/实际：finite check 移到 GPU 后，剩余 8 个约 500 MB payload 的读取与 SHA 计算
  仍由 catalog scan 串行执行。
- 原因：transition timing 基本不变且 scan 实现为串行；不同 learner proposal 的验证
  实际相互独立。
- 影响：仅 M00-A11；已提交 sequence-1 prefix 合法。operator 主动终止 job
  （`Exit_status=271`）。
- 证据：`artifacts/duraloco/M00/20260711_m00_d3a7dce_gpt2_9n_50x10/manifest.json`、
  `training.log` 与同 commit 单/双节点 manifests。
- 修复：并行执行独立 catalog candidate 的 read、SHA、结构与 finite validation，同时
  保持结果顺序确定性并串行化 quarantine registry 写入。

### 限制与下一动作

M00 仍假设只有一个 active syncer；lease/fencing 属于 P05，learner exact restart 与
权威 GC 属于后续阶段。下一动作是干净九节点 GPT-2/WikiText-2 50×10 terminal gate。
