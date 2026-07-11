# P06 Milestone Report

## English

### Status and implementation

- Phase: P06 — learner contribution intervals, boundary adoption, and warm recovery
- Branch: `codex/duraloco-p06-learner-protocol`
- P05 archival base: `419577899a64a12cc602870d059a092f9319bed1`
- Verified Maker implementation: `2581a4d6286c7d0666f76aa3cc9d8122e66f6d25`
- Current status: `completed`
- Acceptance: P06-A01 through P06-A20 pass at the Maker gate
- Checker verdict: `PASS`, with no required-gate follow-up

P06 keeps the single public `fs_diloco.learner` runtime and adds one
dependency-free learner-protocol kernel. Each proposal now binds an immutable
learner session, monotonic per-session sequence, frozen committed frontier and
fragment-version vector, non-overlapping local-step/data cursor interval,
actual token count, RNG hook, numeric contract, and deterministic publication
request identity. Publication is session record, payload, request evidence,
then immutable marker; response-loss retry is keyed by request identity, and
the learner has no head-CAS surface.

The runtime observes a new head during local work but adopts only after marker
publication at the interval boundary. `reset_all` is the conservative default
inner-optimizer policy; `reset_updated_fragment` and `preserve` remain explicit
tested ablations. Restart creates a new session, reconciles immutable markers
against committed interval identities, and either adopts that successor or
waits for a committed successor/authoritative stop/no-progress outcome before
starting new work. Recovery is explicitly warm, not bitwise exact.

### Maker evidence

- Targeted repair: `20260711_p06_repair_2581a4d_targeted1` proves that the
  terminal wrapper resolves its delegated script from an arbitrary PBS jobdir.
- Final one-node: `20260711_p06_repair_2581a4d_1node` runs the full suite plus a
  real GPT-2/WikiText-2 path. Losses are finite, four local steps are within the
  ten-step gate, two immutable intervals publish, and two boundary adoptions
  are recorded.
- Final two-node: `20260711_p06_repair_2581a4d_2node` separates syncer and
  learner across hosts, SIGKILLs the learner after publication, restarts with a
  distinct session, reconciles the prior publication before new work, commits
  two optimizer transitions, and observes authoritative stop.
- Final nine-node: `20260711_p06_repair_2581a4d_gpt2_9n_50x10_retry1` uses one
  active/standby syncer node plus eight learner nodes, real GPT-2/WikiText-2,
  50 inner steps and 10 optimizer transitions. The terminal report is the
  authority for exact timings, session counts, marker count, finite losses,
  checkpoints, fencing, split-brain, and inclusion assertions.

The terminal retry completed in 9m51s. It retained 11 checkpoints, recorded 96
finite losses and 96 immutable publication markers, consumed 80 protocol
proposals exactly once, committed 10 optimizer transitions plus three control
transitions, and reported zero split brain/double inclusion. Learner 000 was
SIGKILLed after publication, restarted under a second session, waited for a
committed successor, and finished 550 local steps; the other seven learners
finished 600. Active-syncer takeover RTO was 68.920 s and standby strict replay
was 21.922 s.

### Failure and retry history

The initial RED run failed because the learner-protocol package did not yet
exist, then GREEN passed. Subsequent one-node attempts exposed and corrected an
obsolete M00 source assertion, a shared-worktree evidence mistake, and a
checkout-containment error. The first two-node attempt used `synthetic` instead
of the supported `synthetic-tiny`; a later passing runtime was followed by an
overly narrow evidence assertion that required backpressure even when committed
ancestry had already reconciled the publication.

The first nine-node attempt, PBS `2360503.opbs`, allocated nodes but failed
before runtime because the wrapper resolved a delegated script from PBS jobdir.
The immutable failure manifest and bilingual workflow review are preserved.
Per retry discipline, the repair passed targeted one-node, full one-node, and
two-node gates on the same clean commit before the single terminal retry.

### Independent Checker gate

PBS `2360636.opbs`, run `20260711_p06_checker_030129e_1node`, independently
checked persistence commit `030129e045c4e5a2abb80eb100a0e28fb78d384d` in a
clean worktree and verified Maker implementation
`2581a4d6286c7d0666f76aa3cc9d8122e66f6d25`. It passed the static research and
SQLite-free contracts, 10,000 unique reference traces, 378 tests with one
explicit skip, all 20 acceptance IDs, and the complete one/two/nine-node
lineage.

The Checker-only counterexample corrupted an immutable publication request on
read and combined that failure with a mid-interval committed successor. The
request failed closed before a new session interval could begin, the successor
remained pending until the boundary, and the learner performed zero head-CAS
operations. The final verdict is `PASS`, required-gate follow-ups are `none`,
and the `checking -> completed` transition is authorized. This does not
authorize merging `main`.

### Limitations

P06 warm recovery does not preserve inner optimizer, RNG, or dataset iterator
bitwise state and reports lost/repeated work estimates. Exact optional learner
capsules remain P07 scope. No database-era run is resumed and no embedded
database is present. P06 completion does not authorize merging `main`.

## 中文

### 状态与实现

- 阶段：P06 — learner contribution interval、boundary adoption 与 warm recovery
- 分支：`codex/duraloco-p06-learner-protocol`
- P05 归档基线：`419577899a64a12cc602870d059a092f9319bed1`
- 已验证 Maker implementation：`2581a4d6286c7d0666f76aa3cc9d8122e66f6d25`
- 当前状态：`completed`
- 验收：Maker gate 中 P06-A01 至 P06-A20 全部通过
- Checker 结论：`PASS`，且没有 required-gate follow-up

P06 保留唯一公共 `fs_diloco.learner` runtime，并增加唯一 dependency-free learner
protocol kernel。每个 proposal 现在绑定 immutable learner session、session 内单调
sequence、冻结的 committed frontier 与 fragment-version vector、互不重叠的 local-step/
data cursor interval、实际 token 计数、RNG hook、numeric contract，以及确定性 publication
request identity。发布顺序为 session record、payload、request evidence、最后 immutable
marker；丢响应重试由 request identity 识别，learner 没有 head-CAS surface。

runtime 在 local work 期间只观察新 head，并在 marker 发布后的 interval boundary 才
adopt。`reset_all` 是保守默认 inner-optimizer policy；`reset_updated_fragment` 与
`preserve` 是显式且有测试的 ablation。重启会建立新 session，把 immutable marker 与
committed interval identity 对账，并在开始新工作前采用 successor，或等待 committed
successor、权威 stop、明确 no-progress。恢复明确是 warm，而不是 bitwise exact。

### Maker 证据

- targeted 修复：`20260711_p06_repair_2581a4d_targeted1` 从任意 PBS jobdir 证明
  terminal wrapper 能解析被委托脚本。
- 最终单节点：`20260711_p06_repair_2581a4d_1node` 运行完整测试与真实
  GPT-2/WikiText-2 路径；loss 有限，四个 local step 满足十步 gate，发布两个 immutable
  interval，并记录两次 boundary adoption。
- 最终双节点：`20260711_p06_repair_2581a4d_2node` 把 syncer/learner 分置不同 host，
  在 publication 后 SIGKILL learner，以不同 session 重启，在新工作前对账旧 publication，
  提交两个 optimizer transition，并观察权威 stop。
- 最终九节点：`20260711_p06_repair_2581a4d_gpt2_9n_50x10_retry1` 使用一个
  active/standby syncer node 和八个 learner node，运行真实 GPT-2/WikiText-2、50 inner
  step 与 10 optimizer transition。精确 timing、session 数、marker 数、finite loss、
  checkpoint、fencing、split-brain 与 inclusion 断言以 terminal report 为准。

terminal retry 在 9 分 51 秒完成；保留 11 个 checkpoint，记录 96 个 finite loss 与
96 个 immutable publication marker，80 个 protocol proposal 各自恰好消费一次，提交
10 个 optimizer transition 和三个 control transition，split brain/double inclusion
均为零。learner 000 在 publication 后被 SIGKILL，以第二个 session 重启，等待 committed
successor 后完成 550 local step；其余七个 learner 完成 600。active-syncer takeover
RTO 为 68.920 秒，standby strict replay 为 21.922 秒。

### 失败与重试历史

初始 RED 因 learner-protocol package 尚不存在而失败，随后 GREEN 通过。后续单节点
尝试依次暴露并修正过期 M00 source assertion、共享 worktree 证据错误与 checkout 路径
约束错误。首次双节点使用了 `synthetic` 而不是受支持的 `synthetic-tiny`；后续 runtime
通过后，又发现证据断言过窄——当 committed ancestry 已完成对账时，不应强制要求再次
出现 backpressure event。

首次九节点 PBS `2360503.opbs` 已分配节点，但 wrapper 从 PBS jobdir 解析委托脚本，
因此在 runtime 前失败。immutable failure manifest 与双语 workflow review 均保留。
按照 retry 纪律，修复在同一干净 commit 上依次通过 targeted 单节点、完整单节点和双节点，
之后才执行唯一一次 terminal retry。

### 独立 Checker gate

PBS `2360636.opbs`、run `20260711_p06_checker_030129e_1node` 在干净 worktree
中独立检查 persistence commit
`030129e045c4e5a2abb80eb100a0e28fb78d384d`，并验证 Maker implementation
`2581a4d6286c7d0666f76aa3cc9d8122e66f6d25`。它通过静态 research 与
SQLite-free contract、10,000 条唯一 reference trace、378 项测试（另有 1 项显式
跳过）、全部 20 项验收，以及完整的单/双/九节点 lineage。

Checker 专属反例在读取时损坏 immutable publication request，并同时注入 interval
中途出现的 committed successor。损坏请求在新 session interval 开始前 fail closed，
successor 保持 pending 直到 boundary，learner 的 head-CAS 操作为零。最终 verdict 为
`PASS`，required-gate follow-up 为 `none`，并授权 `checking -> completed` 状态转换；
这不授权合并 `main`。

### 限制

P06 warm recovery 不保存 inner optimizer、RNG 或 dataset iterator 的 bitwise state，
而是报告 lost/repeated work estimate。可选 exact learner capsule 属于 P07。不会续跑
数据库时代 run，也没有 embedded database。P06 完成不授权合并 `main`。
