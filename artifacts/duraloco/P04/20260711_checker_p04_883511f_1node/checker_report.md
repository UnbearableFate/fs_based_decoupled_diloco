# P04 Final Independent Checker Report

Verdict: PASS
required_gate_followups: none
P04-A09: PASS
checking_to_completed: AUTHORIZED

## English

### Review identity

- Persistence commit: `883511f36b0a298bbacae1ead3bb787fa4cf9bf2`
- Verified implementation: `a655413cea6ebe9bc368b5827318efd766683b5a`
- Branch: `codex/duraloco-p04-transaction-log`
- Independent compute check: PBS `2358203.opbs`, host `mg0004`, exit 0
- Previous blocked checker attempt: PBS `2358154.opbs`

### Final result

All required P04 gates pass. The current persisted `tests/log` suite passed
26 tests, including the lifecycle-aware terminal-state check and the bilingual
`50×10` report marker. The prior persistence drift is resolved.

The new clean Maker lineage is internally consistent:

- PBS `2358166.opbs`, one node: clean `a655413`, 272 passed and one explicit
  nightly skip, ten-transition POSIX/replay/crash/cache/orphan contract passed;
  `parent_run_id=20260711_p04_f6d6e93_1node`.
- PBS `2358168.opbs`, two nodes: clean `a655413`, 20 same-parent races, zero
  double winners and zero double inclusions, response loss recovered, second
  node takeover passed; parent is the prior 79373ec two-node run.
- PBS `2358179.opbs`, nine nodes: clean `a655413`, parent is the prior 79373ec
  terminal run. It used nine distinct hosts, a hard `00:15:00` PBS walltime,
  and had an observed qstat elapsed time of `00:00:47`.

The terminal run used real GPT-2 and WikiText-2 with one syncer, eight
learners, `inner_steps=50`, and exactly ten global outer transitions. All 109
recorded losses were finite, eleven checkpoints were retained and hashed, the
26-test P04 slice passed, and all twelve terminal assertions were true.

### P04-A09 one-CAS audit

The five independent counterexamples were rerun and passed:

1. A lost CAS-success response retried after successor progress returned
   `already_committed` without another CAS.
2. Identical writers produced one logical commit, one inclusion, and one CAS.
3. A distinct losing writer remained rejected and unconsumed after successor
   progress.
4. Corruption of the middle POSIX commit localized to `commit_seq=2`.
5. A corrupt SQLite cache was rejected and rebuilt exactly from the
   authoritative log.

Static review continues to find a single transition mutation path:
`TransactionalLog.commit_prepared` conditionally replaces the one head.
Immutable prepared objects are not authority. Replay verifies head/frontier
reachability, the commit chain, proposal identities, deterministic optimizer
outputs, cumulative consumption, and the paired params/outer-state references.

### Transition authorization

The two P04 state files agree, all P04-A01 through P04-A09 mappings are PASS,
the required 1/2/9-node checks are PASS, no blocker is open, the plan checksum
and PBS syntax checks pass, and the final Checker verdict has no required-gate
follow-up. The `checking -> completed` transition is authorized. P05 may begin
only after this report/evidence is persisted and the completed P04 state is
committed; this does not authorize merging `main`.

## 中文

### 复核身份

- 持久化提交：`883511f36b0a298bbacae1ead3bb787fa4cf9bf2`
- 已验证实现：`a655413cea6ebe9bc368b5827318efd766683b5a`
- 分支：`codex/duraloco-p04-transaction-log`
- 独立计算节点检查：PBS `2358203.opbs`，节点 `mg0004`，退出码 0
- 上一次被阻塞的 Checker 尝试：PBS `2358154.opbs`

### 最终结果

P04 全部必需 gate 均通过。当前持久化的 `tests/log` 套件通过 26 项测试，
其中包括可识别生命周期的 terminal-state 检查和双语报告中的 `50×10`
精确标记。此前的持久化漂移已解决。

新的干净 Maker lineage 内部一致：

- PBS `2358166.opbs`，单节点：干净的 `a655413`，272 项通过、一个显式
  nightly skip；十次 transition 的 POSIX/replay/crash/cache/orphan contract
  通过；`parent_run_id=20260711_p04_f6d6e93_1node`。
- PBS `2358168.opbs`，双节点：干净的 `a655413`，20 轮同 parent race，
  double winner 和 double inclusion 均为零，response loss 恢复与第二节点
  takeover 均通过；parent 指向之前的 79373ec 双节点 run。
- PBS `2358179.opbs`，九节点：干净的 `a655413`，parent 指向之前的
  79373ec terminal run。使用九个不同节点、PBS 硬限制 `00:15:00`，
  qstat 观测 elapsed 为 `00:00:47`。

最终训练使用真实 GPT-2 与 WikiText-2，包含一个 syncer、八个 learner、
`inner_steps=50`，并恰好完成十次 global outer transition。109 个记录 loss
全部有限；保留并哈希了 11 个 checkpoint；P04 的 26 项测试和全部 12 个
terminal assertion 均通过。

### P04-A09 单 CAS 审查

五个独立反例重新运行并全部通过：

1. CAS 成功响应丢失后，即使 successor 已推进，重试仍返回
   `already_committed`，且不会再次执行 CAS。
2. 相同 writer 输入只产生一次逻辑 commit、一次 inclusion 和一次 CAS。
3. 不同的失败 writer 在 successor 推进后仍被拒绝且未被消费。
4. 三次提交中的中间 POSIX commit 损坏被定位到 `commit_seq=2`。
5. 损坏的 SQLite cache 被拒绝，并从权威 log 精确重建。

静态审查仍确认只有一个 transition mutation path：
`TransactionalLog.commit_prepared` 对唯一 head 执行条件替换。不可变 prepared
objects 不是权威。Replay 校验 head/frontier 可达性、commit chain、proposal
identity、确定性 optimizer 输出、累计 consumption，以及配对的 params/
outer-state 引用。

### 状态转换授权

两个 P04 state 文件一致，P04-A01 至 P04-A09 映射全部为 PASS，所需的
1/2/9 节点检查全部通过，没有 open blocker，plan checksum 与 PBS 语法检查
通过，最终 Checker 也没有 required-gate follow-up。因此授权
`checking -> completed`。只有在本报告和证据被持久化、P04 completed 状态已
提交后才能开始 P05；该授权不包含合并 `main`。
