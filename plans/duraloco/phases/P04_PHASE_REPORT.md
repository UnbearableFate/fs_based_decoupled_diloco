# P04 Milestone Report

## English

### Status

- Phase: P04 — transactional fragment log and prefix recovery
- Branch: `codex/duraloco-p04-transaction-log`
- Base: completed P03 commit `a93633d8d41bdb0e184711c4efaa132f211aa5e9`
- Checked persistence commit: `883511f36b0a298bbacae1ead3bb787fa4cf9bf2`
- Verified implementation: `a655413cea6ebe9bc368b5827318efd766683b5a`
- State: `completed`; final Checker authorized `checking -> completed`
- Completed targets: P04-A01 through P04-A09
- Open target: none
- Parent-linked Maker PBS: `2358166.opbs` (1 node), `2358168.opbs` (2 nodes),
  and `2358179.opbs` (terminal 9 nodes)
- Final Checker: PBS `2358203.opbs`; `Verdict: PASS`,
  `required_gate_followups: none`

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
| P04-A09 | PASS | independent Checker one-CAS proof and five novel counterexamples |

### Terminal real-training gate

- qsub job `2358179.opbs` used 9 distinct hosts: `mg0003`, `mg0004`,
  `mg0007`, `mg0008`, `mg0010`, `mg0011`, `mg0012`, `mg0013`, `mg0014`.
- PBS walltime was hard-limited to 15 minutes; observed `qstat` elapsed time was
  47 seconds at final validation, so the slow-run failure signal did not fire.
- The first regular-queue submission, `2358174.opbs`, showed an estimated start
  over one hour later due to resource pressure and was canceled before
  allocation. The final batch was immediately resubmitted to `debug-g`; this
  queue change did not relax the 15-minute limit or any training assertion.
- The run used real `gpt2` and WikiText-2 with one syncer and eight learners,
  `inner_steps=50`, and exactly 10 committed outer optimizer transitions.
- This is the required real-training **50×10** milestone marker.
- Learner local-step range was 600–721. All 109 observed losses were finite,
  from 3.5127114105 to 4.5559995317.
- Eleven checkpoints (`v000000` through `v000010`) were retained and SHA-256
  bound to a ten-transition P04 projection. Its final committed digest was
  `3ec49951ad933a01a8691f4ada366d3b2f865e0b0faa0b840552f2737e24ba4d`.
- All twelve terminal assertions passed and the terminal P04 test slice passed
  26 tests. The cumulative 1-node suite passed 272 tests with one explicit
  pre-existing nightly skip.

### Verification failure history

#### Independent Checker `2db8a73` / PBS `2358154` — blocked, resolved

- Phenomenon: all five new transactional counterexamples passed, but the
  persisted `tests/log` slice passed 24 and failed 2. The milestone-state test
  still expected `in_progress`/`not_run`, while persisted state correctly said
  `checking`/`miyabi_9node_pass`; the report test could not find its exact
  `50×10` marker. The final 1-node manifest also had `parent_run_id: null`
  despite the documented failed f6 attempt.
- Reason: persistence-sensitive tests/report text were not transitioned with
  state, and Maker reruns did not bind retry lineage into manifests.
- Impact: P04-A09 persistence/reproducibility gate; no transactional safety
  defect was found.
- Evidence: `artifacts/duraloco/P04/20260711_checker_p04_79373ec_1node/checker_report.md`.
- Resolution: `a655413` made the state test lifecycle-aware and added the exact
  bilingual marker. Parent-linked PBS `2358166`, `2358168`, and `2358179`
  then passed at that clean commit; their manifests bind the failed f6 attempt
  or the previous corresponding successful run. Independent PBS `2358203`
  passed 26 persisted log tests, reran all five counterexamples, validated the
  lineage, and authorized completion with no follow-up.

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

Start P05 syncer lease fencing and failover from this completed P04
feature-branch tip; do not merge `main` automatically.

## 中文

### 状态

- 阶段：P04 — transactional fragment log 与 prefix recovery
- 分支：`codex/duraloco-p04-transaction-log`
- 基线：已完成的 P03 提交 `a93633d8d41bdb0e184711c4efaa132f211aa5e9`
- 已复核持久化提交：`883511f36b0a298bbacae1ead3bb787fa4cf9bf2`
- 已验证实现：`a655413cea6ebe9bc368b5827318efd766683b5a`
- 状态：`completed`；最终 Checker 已授权 `checking -> completed`
- 已完成 targets：P04-A01 至 P04-A09
- 未完成 target：无
- 带 parent lineage 的 Maker PBS：`2358166.opbs`（单节点）、
  `2358168.opbs`（双节点）、`2358179.opbs`（最终九节点）
- 最终 Checker：PBS `2358203.opbs`；`Verdict: PASS`，
  `required_gate_followups: none`

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
| P04-A09 | PASS | 独立 Checker one-CAS proof 与五个新反例 |

### 最终真实训练 gate

- qsub 作业 `2358179.opbs` 使用 9 个不同 hosts：`mg0003`、`mg0004`、
  `mg0007`、`mg0008`、`mg0010`、`mg0011`、`mg0012`、`mg0013`、`mg0014`。
- PBS walltime 硬限制为 15 分钟；最终校验时 `qstat` observed elapsed 为
  47 秒，因此没有触发 slow-run 失败信号。
- 首次 regular queue 提交 `2358174.opbs` 因资源压力预估要一小时后才
  启动，因此在分配节点前取消；最终 batch 立即改投 `debug-g`，仍保持
  15 分钟硬限制与全部训练断言。
- 训练使用真实 `gpt2` 与 WikiText-2，1 个 syncer、8 个 learners，
  `inner_steps=50`，并恰好提交 10 次 outer optimizer transition。
- 这是规定的真实训练 **50×10** milestone marker。
- learners local-step 范围为 600–721；109 个 loss 全部有限，范围
  3.5127114105–4.5559995317。
- 保留并 SHA-256 绑定了 `v000000` 至 `v000010` 共 11 个 checkpoints；
  十次 P04 projection 的最终 committed digest 为
  `3ec49951ad933a01a8691f4ada366d3b2f865e0b0faa0b840552f2737e24ba4d`。
- 十二项 terminal assertions 全部通过，最终 P04 test slice 通过 26 项；
  累计单节点 suite 通过 272 项，仅有一个既有 nightly skip。

### 验证失败历史

#### 独立 Checker `2db8a73` / PBS `2358154` — 阻塞，已解决

- 现象：五个新增 transactional 反例全部通过，但 persisted `tests/log` slice
  24 项通过、2 项失败。milestone state test 仍期待 `in_progress`/`not_run`，
  而持久化 state 已正确变为 `checking`/`miyabi_9node_pass`；report test 也找不到
  精确的 `50×10` marker。最终单节点 manifest 的 `parent_run_id` 仍为 `null`，
  没有绑定已记录的 f6 失败尝试。
- 原因：persistence-sensitive tests/report text 没有随 state 一起转换，Maker
  rerun 也没有把 retry lineage 写入 manifests。
- 影响：P04-A09 persistence/reproducibility gate；未发现 transactional safety 缺陷。
- 证据：`artifacts/duraloco/P04/20260711_checker_p04_79373ec_1node/checker_report.md`。
- 解决：`a655413` 让 state test 识别生命周期并加入精确双语 marker；
  带 parent lineage 的 PBS `2358166`、`2358168`、`2358179` 随后在该 clean
  commit 上全部通过，manifest 已绑定 f6 失败尝试或上一个对应的成功作业。
  独立 PBS `2358203` 随后通过 26 项 persisted log tests，重跑全部五个
  反例，验证 lineage，并在无 follow-up 的情况下授权完成。

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

从已完成的 P04 feature branch tip 启动 P05 syncer lease fencing 与 failover；
不自动合并 `main`。
