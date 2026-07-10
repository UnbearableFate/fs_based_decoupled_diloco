# P04 Milestone Report

## English

### Status

- Phase: P04 — transactional fragment log and prefix recovery
- Branch: `codex/duraloco-p04-transaction-log`
- Base: completed P03 commit `a93633d8d41bdb0e184711c4efaa132f211aa5e9`
- Verified implementation: `79373ecab4e051b4c9ff2ba128250d8612b9ab8b`
- State: `checking`; Maker gates P04-A01 through P04-A08 passed
- Open target: P04-A09 independent one-CAS proof audit
- Maker PBS: `2358087.opbs` (1 node), `2358090.opbs` (2 nodes), and
  `2358093.opbs` (terminal 9 nodes)

### Acceptance summary

| Target | Result | Primary evidence |
|---|---|---|
| P04-A01 | PASS | one mutable head and one `conditional_replace` transition path |
| P04-A02 | PASS | ten before/after crash points recover to old/new complete prefix |
| P04-A03–A04 | PASS | delayed response-loss recovery, 20 two-node races, zero double inclusion |
| P04-A05 | PASS | params/outer-state pair verified together in every successor frontier |
| P04-A06 | PASS | deleted and corrupt SQLite cache rebuilt exactly from replay |
| P04-A07 | PASS | memory and POSIX prefix/state digests match |
| P04-A08 | PASS | inspect CLI passed and corruption test localizes commit sequence |
| P04-A09 | CHECKING | independent Checker one-CAS proof and counterexample audit |

### Terminal real-training gate

- qsub job `2358093.opbs` used 9 distinct hosts: `mg0231`, `mg0293`,
  `mg0294`, `mg0295`, `mg0296`, `mg0339`, `mg0352`, `mg0360`, `mg0393`.
- PBS walltime was hard-limited to 15 minutes; observed `qstat` elapsed time was
  47 seconds at final validation, so the slow-run failure signal did not fire.
- The run used real `gpt2` and WikiText-2 with one syncer and eight learners,
  `inner_steps=50`, and exactly 10 committed outer optimizer transitions.
- Learner local-step range was 554–567. All 96 observed losses were finite,
  from 3.1660020141 to 4.5559995317.
- Eleven checkpoints (`v000000` through `v000010`) were retained and SHA-256
  bound to a ten-transition P04 projection. Its final committed digest was
  `530fdc067b09dd77b98b488fe1d393138b6aa32c42ac93b264966b46b53e14e0`.
- All twelve terminal assertions passed and the terminal P04 test slice passed
  26 tests. The cumulative 1-node suite passed 272 tests with one explicit
  pre-existing nightly skip.

### Verification failure history

#### 1-node `f6d6e93` / PBS `2358012` — resolved

- Phenomenon: 269 tests passed and one skipped, but a second identical retry
  after lost CAS-success response returned `committed`, not
  `already_committed`.
- Reason: `commit_prepared` mapped an idempotent backend return to a fresh
  commit without first resolving the current head.
- Impact: P04-A03 outcome observability; safety still had one commit/inclusion.
- Resolution: `b5cb206` pre-resolves exact head success. Final PBS `2358087`
  passed the regression and full suite.

#### Queued terminal job `2358075` — canceled before allocation, resolved

- Phenomenon: maker review found that a much-delayed retry could miss its
  success after a successor commit advanced head.
- Reason: recovery checked only exact current-head equality, not committed
  ancestry.
- Impact: P04-A03 response-loss resolution under subsequent progress.
- Resolution: the queued run was canceled before consuming nodes;
  `79373ec` verifies the prepared commit/frontier in authoritative ancestry and
  adds the counterexample. Final 1/2/9-node jobs passed at that commit.

### Limits

P04 does not yet make the transactional log the production syncer authority;
that integration belongs to P05. The terminal probe binds deterministic P04
projections to real checkpoint hashes and does not claim full-tensor v2 syncer
integration.

### Next action

Persist this Maker evidence, obtain the independent Checker verdict for
P04-A09, then archive the bilingual completed report and milestone commit.

## 中文

### 状态

- 阶段：P04 — transactional fragment log 与 prefix recovery
- 分支：`codex/duraloco-p04-transaction-log`
- 基线：已完成的 P03 提交 `a93633d8d41bdb0e184711c4efaa132f211aa5e9`
- 已验证实现：`79373ecab4e051b4c9ff2ba128250d8612b9ab8b`
- 状态：`checking`；Maker gates P04-A01 至 P04-A08 已通过
- 未完成 target：P04-A09 独立 one-CAS proof 审查
- Maker PBS：`2358087.opbs`（单节点）、`2358090.opbs`（双节点）、
  `2358093.opbs`（最终九节点）

### 验收摘要

| Target | 结果 | 主要证据 |
|---|---|---|
| P04-A01 | PASS | 唯一可变 head 与唯一 `conditional_replace` transition path |
| P04-A02 | PASS | 十个前后 crash points 均恢复到旧/新完整 prefix |
| P04-A03–A04 | PASS | delayed response-loss、20 轮双节点 race、零 double inclusion |
| P04-A05 | PASS | 每个 successor frontier 同时校验 params/outer-state pair |
| P04-A06 | PASS | 删除或损坏的 SQLite cache 均从 replay 精确重建 |
| P04-A07 | PASS | memory 与 POSIX prefix/state digests 一致 |
| P04-A08 | PASS | inspect CLI 通过，corruption test 能定位 commit sequence |
| P04-A09 | CHECKING | 独立 Checker one-CAS proof 与反例审查 |

### 最终真实训练 gate

- qsub 作业 `2358093.opbs` 使用 9 个不同 hosts：`mg0231`、`mg0293`、
  `mg0294`、`mg0295`、`mg0296`、`mg0339`、`mg0352`、`mg0360`、`mg0393`。
- PBS walltime 硬限制为 15 分钟；最终校验时 `qstat` observed elapsed 为
  47 秒，因此没有触发 slow-run 失败信号。
- 训练使用真实 `gpt2` 与 WikiText-2，1 个 syncer、8 个 learners，
  `inner_steps=50`，并恰好提交 10 次 outer optimizer transition。
- learners local-step 范围为 554–567；96 个 loss 全部有限，范围
  3.1660020141–4.5559995317。
- 保留并 SHA-256 绑定了 `v000000` 至 `v000010` 共 11 个 checkpoints；
  十次 P04 projection 的最终 committed digest 为
  `530fdc067b09dd77b98b488fe1d393138b6aa32c42ac93b264966b46b53e14e0`。
- 十二项 terminal assertions 全部通过，最终 P04 test slice 通过 26 项；
  累计单节点 suite 通过 272 项，仅有一个既有 nightly skip。

### 验证失败历史

#### 单节点 `f6d6e93` / PBS `2358012` — 已解决

- 现象：269 项通过、1 项跳过，但 CAS 成功响应丢失后的第二次相同 retry 返回
  `committed`，而不是 `already_committed`。
- 原因：`commit_prepared` 未先解析当前 head，就把 backend 幂等返回映射为新提交。
- 影响：P04-A03 outcome 可观测语义；安全性仍只有一次 commit/inclusion。
- 解决：`b5cb206` 增加 exact-head pre-resolution；最终 PBS `2358087`
  已通过该回归和完整 suite。

#### 已排队 terminal 作业 `2358075` — 分配前取消，已解决

- 现象：Maker 审查发现，successor commit 推进 head 后，很晚到达的 retry 可能
  无法识别自己已经成功。
- 原因：恢复只检查当前 head 是否完全相等，没有检查 authoritative ancestry。
- 影响：P04-A03 在后续进展下的 response-loss resolution。
- 解决：作业在占用节点前取消；`79373ec` 在权威 ancestry 中校验 prepared
  commit/frontier 并增加反例。该提交的最终 1/2/9-node 作业全部通过。

### 限制

P04 尚未让 transactional log 成为 production syncer authority；该集成属于
P05。最终 probe 把确定性 P04 projection 与真实 checkpoint hashes 绑定，
不声称已经完成 full-tensor v2 syncer 集成。

### 下一动作

持久化 Maker evidence，取得 P04-A09 独立 Checker 结论，然后归档双语 completed
report 和 milestone commit。
