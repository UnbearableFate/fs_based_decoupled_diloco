# Design-Level Findings / 设计层发现

Format per finding: problem → evidence → impact → recommended solution.
每项格式：问题 → 证据 → 影响 → 建议方案。

---

## D-01 (HIGH) — Frontier consumption set grows without bound / frontier 消费集无界增长

**EN — Problem.** Every frontier stores the *complete* set of all proposal IDs ever consumed:
`consumed_proposal_ids = sorted(previous ∪ selected)` (`fs_diloco/log/production.py:1138`,
`fs_diloco/log/commit.py:488`), and replay verifies the full-set equality at every step
(`fs_diloco/log/replay.py:1313`). Control transitions copy the full list too
(`production.py:599`).

**Impact.** After n transitions with k selections each, a frontier is O(n·k); writing one
frontier per commit makes cumulative log bytes O(n²). Every replay, snapshot, and prefix digest
re-serializes these sets. At n=10 this is noise; at n=1000 with 8 learners each frontier
carries ~8000 IDs (~0.5 MB), the log carries ~250 MB of *pure consumption bookkeeping*, and
every digest and replay pays for it.

**Solution.** The full set is not needed for safety. Double-inclusion (I-003) is already
enforced by three bounded structures replay maintains: `last_lineage_sequence` (one watermark
per learner/session/fragment), `consumed_interval_bases`, and staleness bounds. A proposal
whose base is older than `max_global_staleness` can never be selected again, so consumption
facts older than the staleness window are dead weight. Migrate (in a new generation) to:
frontier stores (a) per-lineage sequence watermarks, (b) consumed IDs within the staleness
window only, (c) a rolling SHA-256 accumulator of the retired consumption prefix for audit.
Replay checks equality of the windowed set + watermark map + accumulator — same invariant,
O(learners) instead of O(history).

**中文 — 问题。** 每个 frontier 存储*完整*的历史已消费 proposal ID 集合
（`production.py:1138`、`commit.py:488`），replay 每一步都做全集相等校验
（`replay.py:1313`），控制事务也复制全表（`production.py:599`）。

**影响。** n 次 transition、每次 k 条选择后，frontier 体积 O(n·k)，日志累计字节 O(n²)。
n=1000、8 learner 时每个 frontier 携带约 8000 个 ID（约 0.5MB），日志中约 250MB 纯粹是消费
记账，且每次 digest 与 replay 都要为其买单。

**方案。** 安全性并不需要全集。防重复纳入（I-003）已由三个有界结构保证：每
learner/session/fragment 的序列水位线 `last_lineage_sequence`、`consumed_interval_bases` 与
staleness 上界。base 早于 `max_global_staleness` 的 proposal 永远不可能再被选中，因此窗口外
的消费事实是死重。在新 generation 中迁移为：frontier 存 (a) 每 lineage 的序列水位线，(b) 仅
staleness 窗口内的已消费 ID，(c) 已退役消费前缀的滚动 SHA-256 累积值供审计。replay 校验
窗口集 + 水位线表 + 累积值 —— 不变量不变，成本从 O(历史) 降为 O(learner 数)。

---

## D-02 (HIGH) — Prefix digest recomputed from scratch at every commit / 前缀 digest 每步全量重算

**EN — Problem.** `_prefix_digest` (`fs_diloco/log/replay.py:322`) canonical-serializes and
hashes **all** frontiers `[0..i]` and commits `[0..i-1]` — and it is called once per commit
index during replay (`replay.py:1356`, `replay.py:1099`). One strict replay of n commits does
O(n²) serialization/hash work; combined with D-01's O(n)-sized frontiers this trends to O(n³)
bytes hashed.

**Impact.** The committed-state digest is the anchor for I-008 (strict ≡ snapshot+suffix) and
for the lifecycle audits, so this cost sits inside every replay, every lifecycle cycle, and
every takeover. It is a measurable part of why lifecycle cycles grew 34→68 s in H0 as history
grew, and it grows without limit.

**Solution.** Replace with a *chained* digest:
`digest_i = SHA256(digest_{i-1} ‖ canonical(commit_i) ‖ canonical(frontier_i) ‖ head_token_i)`,
`digest_0 = SHA256(spec_digest ‖ canonical(genesis))`. This is exactly as tamper-evident (any
prefix mutation changes every later digest), needs O(1) incremental work per commit, and lets a
snapshot resume the chain from its covered digest. Requires only that all verifiers agree on
the formula — a protocol/schema version bump, best done with the D-01 generation migration.

**中文 — 问题。** `_prefix_digest`（`replay.py:322`）对 `[0..i]` 的全部 frontier 与 commit 做
canonical 序列化并整体哈希，而 replay 对每个 commit 序号都调用一次（`replay.py:1356`、
`1099`）。一次 strict replay 是 O(n²) 的序列化/哈希；叠加 D-01 的 O(n) frontier 后趋于
O(n³) 字节哈希量。

**影响。** 该 digest 是 I-008 与 lifecycle 审计的锚点，因此这笔成本存在于每次 replay、每个
lifecycle 周期、每次接管中。它是 H0 中 lifecycle 从 34 秒涨到 68 秒的可测组成部分，且无上限
增长。

**方案。** 改为*链式* digest：`digest_i = SHA256(digest_{i-1} ‖ canonical(commit_i) ‖
canonical(frontier_i) ‖ head_token_i)`。防篡改性完全等价（前缀任何改动都会改变其后所有
digest），每 commit 只需 O(1) 增量工作，且 snapshot 可从其覆盖 digest 处续链。只需协议/schema
升版，宜与 D-01 的 generation 迁移同批完成。

---

## D-03 (HIGH) — Snapshots embed the entire history / snapshot 内嵌全部历史

**EN — Problem.** `prepare_snapshot_transition` embeds **every** frontier, commit, proposal
manifest, and membership object of the whole run into each snapshot
(`fs_diloco/log/production.py:744-767`). This is forced by how I-008 is enforced: the audits
compare complete `ReplayResult` objects (`committer.py:219-221`, `483-484`), whose `frontiers`
and `commits` tuples span genesis→head, so snapshot-mode replay must be able to reproduce all
of history, not just current state.

**Impact.** Snapshot size ≈ Σ|frontier_i| + Σ|commit_i| ≈ O(n²) with D-01. Snapshot creation
cost grows every cycle (P08R measured lifecycle cycles 0.7 s → 23.1 s within *ten*
transitions). "Snapshot compaction" reduces read *ops* but no *bytes*: nothing is ever actually
truncatable while snapshots must carry everything.

**Solution.** Redefine the recovery equivalence at the *state* level: snapshot stores the
covered committed state (fragment refs+versions, consumption representation per D-01, lineage
watermarks, control-request map, coordination/membership projections) plus the chained prefix
digest per D-02. I-008 becomes "state digest and every state field of snapshot+suffix equal
strict replay" — the same guarantee recovery actually relies on. Full-history re-verification
remains available as an offline audit (`inspect_cli replay`) whenever the physical prefix is
retained. This makes snapshots O(model + learners), enables true log truncation after two
retained bases, and is the single highest-leverage scalability change.

**中文 — 问题。** `prepare_snapshot_transition` 把整个 run 的**每个** frontier、commit、
proposal manifest 与 membership 对象都嵌入 snapshot（`production.py:744-767`）。根源是 I-008
的执法方式：审计直接比较完整 `ReplayResult`（`committer.py:219-221`、`483-484`），其
`frontiers`/`commits` 元组覆盖 genesis→head，故 snapshot 模式 replay 必须能复现全部历史而非
仅当前状态。

**影响。** 叠加 D-01 后 snapshot 体积约 O(n²)；每个周期的创建成本递增（P08R 实测 lifecycle
周期在*十次* transition 内从 0.7 秒涨到 23.1 秒）。所谓"snapshot 压缩"只减少读*次数*不减少
*字节*：只要 snapshot 必须背负一切，就没有任何东西真正可截断。

**方案。** 把恢复等价性重定义在*状态*层面：snapshot 存覆盖的已提交状态（fragment 引用+版本、
按 D-01 的消费表示、lineage 水位线、control-request 表、协调/membership 投影）加 D-02 的链式
前缀 digest。I-008 变为"snapshot+suffix 的状态 digest 与全部状态字段等于 strict replay" ——
这正是恢复真正依赖的保证。只要物理前缀仍保留，全历史重验证仍可作为离线审计
（`inspect_cli replay`）。此举让 snapshot 变为 O(模型+learner 数)，并使两个保留基点之后的
日志真截断成为可能 —— 是杠杆最大的可扩展性改动。

---

## D-04 (MEDIUM) — Fully serial committer pipeline / committer 全串行流水线

**EN — Problem.** The committer handles exactly one fragment per transition, and each
transition is strictly sequential: scan → FWO → wait (LFE compute) → validate → prepare → CAS →
post-CAS replay → materialize, then `time.sleep(0.5)` (`committer.py:800-1407`). During the
~7 s LFE compute the committer only heartbeats; during scan/validate the LFEs idle.

**Impact.** Global optimizer throughput is bounded by the *sum* of all stage latencies
(~18.3 s/transition measured) even though the stages use disjoint resources.

**Solution (safety-preserving pipelining).** Keep the single head CAS and single owner, but
overlap independent stages: (a) while waiting for the PFR of fragment f, run catalog
scan/validation for the next fragment f+1 (its FWO can only be *published* after the parent
commit exists, but validation work is parent-independent); (b) move `publish_materialized_view`
off the critical path into the substage worker (learners tolerate stale views by design);
(c) make the 0.5 s sleep configurable and skip it when a quorum is already waiting. None of
these change any committed identity. A larger step — multiple outstanding FWOs for different
fragments — is compatible with the CAS design but changes FWO parent semantics; treat as a
separate, explicitly-gated experiment.

**中文 — 问题。** committer 每次 transition 只处理一个 fragment，且各阶段严格串行（扫描 →
FWO → 等待 LFE → 验证 → prepare → CAS → CAS 后 replay → 物化），末尾还有固定
`time.sleep(0.5)`（`committer.py:800-1407`）。LFE 计算约 7 秒期间 committer 只在续租；扫描/
验证期间 LFE 闲置。

**影响。** 全局吞吐受*各阶段时延之和*限制（实测约 18.3 秒/次），尽管这些阶段使用互不相干的
资源。

**方案（保安全的流水化）。** 保持唯一 head CAS 与唯一 owner，但重叠独立阶段：(a) 等待
fragment f 的 PFR 期间，为下一 fragment f+1 做 catalog 扫描/验证（FWO 须等 parent commit
存在才能*发布*，但验证工作与 parent 无关）；(b) 把 `publish_materialized_view` 移出关键路径
放进子阶段 worker（learner 本就容忍视图滞后）；(c) 0.5 秒睡眠改为可配置，quorum 已就绪时跳过。
以上都不改变任何已提交 identity。更大的一步 —— 多个不同 fragment 的在途 FWO —— 与 CAS 设计
兼容但改变 FWO 的 parent 语义，应作为单独、显式门控的实验。

---

## D-05 (MEDIUM) — Params/outer written twice, read twice per transition / 每次 transition 参数双写双读

**EN — Problem.** The LFE publishes full new params+outer under the prepared namespace
(`executor.py:190-191`); the committer then downloads both (`committer.py:1046`,
`_validate_result`) and re-publishes the *same bytes* under the authority namespace
(`production.py:1043`, `1054`). Learners later read the materialized copies — a third full
write (C-13) and read.

**Impact.** ≥2 full writes + ≥2 full reads of model-sized payloads per transition. For GPT-2
this is ~1 GB/transition of Lustre traffic; it scales linearly with model size and dominates
`successor_publication` (30.6→50.8 s in the P08R comparison).

**Solution.** Both copies are content-addressed by the same SHA-256. Unify the payload key
namespace (or teach `put_immutable` a same-content promotion path using `os.link` across
prefixes within the same filesystem) so the authority frontier can reference the already-
verified prepared payload without a byte copy. Reachability already protects any object
referenced by a committed chain, and `verified_get` re-checks bytes on read, so no invariant
weakens. Fallback if namespace unification is unwanted: server-side `os.link` in the backend
when source and target roots share a device.

**中文 — 问题。** LFE 在 prepared 命名空间发布完整新 params+outer
（`executor.py:190-191`）；committer 下载两者（`committer.py:1046`）后把*同样的字节*重新发布
到权威命名空间（`production.py:1043`、`1054`）；learner 之后再读物化副本 —— 第三次全量写
（见 C-13）与读。

**影响。** 每次 transition 至少 2 次全量写 + 2 次全量读模型级 payload。GPT-2 约合每次 1GB
Lustre 流量，随模型线性增长，是 `successor_publication`（对比中 30.6→50.8 秒）的主体。

**方案。** 两份副本本就以同一 SHA-256 内容寻址。统一 payload key 命名空间（或让
`put_immutable` 支持同内容跨前缀 `os.link` 升级路径），使权威 frontier 直接引用已验证的
prepared payload，免去字节拷贝。可达性机制本就保护被已提交链引用的对象，`verified_get` 读时
仍校验字节，不弱化任何不变量。若不愿统一命名空间，可在后端对同设备根之间做 `os.link` 兜底。

---

## D-06 (MEDIUM) — Hedging waits for both attempts / hedged 模式等待双份结果

**EN — Problem.** Once the hedge delay elapses (or in active_active), `_wait_for_result` sets
`required_attempts = 2` and will not proceed until *both* the primary and the backup publish
(`committer.py:280-296`). A merely-slow primary therefore makes the hedge *add* the backup's
full latency; a silently-dead primary blocks until failure evidence or the no-progress timeout.
P08R measured ~5 s extra per hedged transition.

**Impact.** The stated purpose of hedging (cut tail latency) is inverted; hedging currently
only buys duplicate-execution evidence.

**Solution.** Decouple *commit progress* from *divergence audit*: commit on the first fully
validated result; when the second attempt arrives, compare identities in the background and
treat divergence as the same stop-condition blocker it is today (the losing attempt is already
retained as evidence). I-011's fail-closed guarantee then applies retroactively-but-promptly —
before the next transition commits, since the comparison is cheap and the committer is serial.
If strictly-before-commit comparison is a hard research requirement, keep the current mode but
document that `hedged` is an evidence mode, not a latency mode, and add failure-evidence
auto-generation when the primary exceeds a deadline so the wait can collapse to one attempt.

**中文 — 问题。** hedge 延迟一到（或 active_active 模式下），`_wait_for_result` 把
`required_attempts` 设为 2，必须 primary 与 backup *都*发布结果才继续
（`committer.py:280-296`）。primary 只是慢时，对冲反而*增加* backup 的全程延迟；primary 静默
死亡时则阻塞到故障证据或无进展超时。P08R 实测每个 hedged transition 多约 5 秒。

**影响。** 对冲的本意（削尾延迟）被反转；目前 hedging 只换来重复执行证据。

**方案。** 把*提交推进*与*分歧审计*解耦：第一个通过全量验证的结果即可提交；第二个 attempt
到达后在后台比较 identity，分歧仍按今日的 stop-condition 处理（落败 attempt 本就保留为证据）。
由于比较廉价且 committer 串行，I-011 的失败关闭保证在下一次 transition 提交前即可兑现。若
"提交前必须比较"是硬性研究要求，则保留现状但明确记载 `hedged` 是证据模式而非延迟模式，并在
primary 超时后自动生成故障证据，使等待可收敛为单 attempt。

---

## D-07 (MEDIUM) — Learner adoption trusts derived files / learner 采用路径信任派生文件

**EN — Problem.** Learners load fragment weights via `torch.load`-style
`load_fragment_weight(info["weight_path"])` with no digest check against the committed
`params_ref` (`learner.py:452-501`); `latest.json` carries paths and versions but no hashes.

**Impact.** Authority safety is untouched (derived data cannot enter recovery), but *research
validity* is exposed: a torn write, stale file, or bit corruption in a materialized fragment
silently feeds every learner a wrong base; the resulting proposals still validate (finite,
right shape, correctly-declared base) and get committed. Nothing in the system would ever
notice.

**Solution.** Cheapest: include each fragment file's SHA-256 (already known — it is the
authority payload digest) in `latest.json`, and have learners verify on load (sub-second for
GPT-2, amortized once per adoption). Cleaner: have learners read the authority object directly
with `verified_get(frontier.params_ref)` — the bytes already sit on the same shared filesystem
and are envelope-verified; materialized copies then serve only external checkpointing.

**中文 — 问题。** learner 用 `load_fragment_weight(info["weight_path"])` 加载 fragment 权重，
不对照已提交 `params_ref` 做 digest 校验（`learner.py:452-501`）；`latest.json` 只有路径与
版本，没有哈希。

**影响。** 权威安全不受影响（派生数据进不了恢复），但*研究有效性*暴露在外：物化 fragment 的
撕裂写、陈旧文件或位翻转会静默喂给所有 learner 错误的 base；产出的 proposal 依然通过验证
（有限值、形状正确、base 声明无误）并被提交。系统中没有任何环节会察觉。

**方案。** 最廉价：在 `latest.json` 中带上每个 fragment 文件的 SHA-256（本来就有 —— 即权威
payload digest），learner 加载时校验（GPT-2 亚秒级，每次采用摊销一次）。更干净：learner 直接
`verified_get(frontier.params_ref)` 读权威对象 —— 字节本就在同一共享文件系统上且有 envelope
校验；物化副本只服务外部 checkpoint 用途。

---

## D-08 (MEDIUM) — Clock-skew assumption is never verified / 时钟偏差假设从未验证

**EN — Problem.** Lease expiry and takeover eligibility compare `time.time_ns()` across hosts
under an assumed `max_clock_skew_seconds = 2.0` (`coordination/lease.py:276-279`,
`config.py:87`). The capability probe verifies locks, fsync, and CAS races — but nothing ever
measures actual inter-node clock offset. Hedge timing also mixes clocks (`committer.py:279`).

**Impact.** If a standby's clock runs >2 s fast, it can acquire the lease before the true safe
window ends. The head-version CAS still prevents committed divergence (the final safety net
holds), but the design's explicit "old owner's in-flight window has ended" guarantee is
silently voided, and both owners can waste work / trip fail-closed paths.

**Solution.** Add a clock-evidence probe to run startup (the same two-node pattern as the lock
probe): each node writes its `time.time_ns()` plus a storage-server-observable ordering token;
fail closed if the measured offset exceeds a budgeted fraction of `max_clock_skew_seconds`.
Record the evidence in the capability report. Optionally re-probe when a takeover begins.

**中文 — 问题。** lease 过期与接管资格是跨主机比较 `time.time_ns()`，仅假设
`max_clock_skew_seconds = 2.0`（`lease.py:276-279`、`config.py:87`）。能力探测验证了锁、
fsync、CAS 竞争 —— 却从不测量真实节点间时钟偏移。hedge 计时同样混用时钟
（`committer.py:279`）。

**影响。** 若 standby 时钟快超过 2 秒，它会在真正的安全窗口结束前取得 lease。head 版本 CAS
仍能阻止已提交状态分叉（最后的安全网有效），但设计上"旧 owner 在途窗口已结束"的显式保证被
静默作废，双 owner 会浪费工作或触发失败关闭路径。

**方案。** 在运行启动时增加时钟证据探测（复用双节点锁探测模式）：各节点写入自己的
`time.time_ns()` 与可由存储服务器观察的顺序 token；实测偏移超出 `max_clock_skew_seconds`
预算比例时失败关闭。证据记入能力报告。接管开始时可选择重探。

---

## D-09 (LOW) — Recovery floor is policy, not physics / 恢复下限是策略而非物理

**EN** — The 37–47 s takeover wait comes from TTL=45 s / renew=10 s / skew=2 s. The docs
correctly forbid *violating* the fencing budget, but never define the procedure for *lowering*
it safely. The actual constraint is TTL > worst-case renewal latency (a storage op) + margin;
measured renewals are sub-second. **Solution:** define an evidence-driven tuning gate: collect
renewal-latency distribution from real D8 runs, then qualify e.g. TTL=15 s / renew=3 s /
margin=5 s on 1-node → 2-node → 8-node, cutting the recovery floor by ~30 s without touching
any invariant. Keep the current values as the conservative default.

**中文** — 37–47 秒接管等待来自 TTL=45s / renew=10s / skew=2s。文档正确禁止*违反* fencing
预算，却没有定义*安全降低*它的程序。真实约束是 TTL > 最坏续租时延（一次存储操作）+ 裕量；
实测续租是亚秒级。**方案：** 建立证据驱动的调参门：从真实 D8 运行收集续租时延分布，然后按
1 节点 → 2 节点 → 8 节点资格路径验证如 TTL=15s / renew=3s / 裕量=5s，可在不动任何不变量的
前提下把恢复下限削去约 30 秒。当前值保留为保守默认。

---

## D-10 (LOW) — No automatic failed-member reintegration / 无失败成员自动重入

**EN** — Whole-host loss is handled by committed membership removal; rejoining requires manual
action, and the failure model explicitly makes no reintegration claim. That is honest but
operationally expensive for long runs: capacity degrades monotonically. **Solution sketch
(future phase):** a rejoin is just membership revision N+1 adding a member whose learner starts
via the existing warm-recovery path; the committed-membership and rendezvous-ownership
machinery already handles arbitrary revisions. The missing pieces are only (a) an authenticated
rejoin request analogous to `ReconfigurationRequestV1` and (b) a qualification test where a
removed member rejoins and its first proposals validate. No new protocol concepts required.

**中文** — 整机丢失的处置是提交 membership 移除；重新加入需人工操作，故障模型也明确不做重入
主张。这很诚实，但对长运行代价高：容量单调退化。**方案草案（未来阶段）：** 重入不过是
membership revision N+1 新增成员，其 learner 走既有 warm 恢复路径启动；已提交 membership 与
rendezvous 所有权机制本就支持任意 revision。缺的只是 (a) 类似 `ReconfigurationRequestV1` 的
可认证重入请求，(b) 一个"被移除成员重入且其首批 proposal 通过验证"的资格测试。无需新协议
概念。

---

## D-11 (LOW) — No disaster-recovery export of authority / 权威缺少灾备导出

**EN** — All authority lives in one Lustre namespace. The threat model excludes permanent loss
of acknowledged-durable objects, which is fair for research — but a single `rm -rf`, quota
purge, or scratch-expiry event erases the entire committed trajectory including all evidence.
**Solution:** a read-only exporter (login-node-safe) that copies the head, snapshots, and the
committed reachable closure to a second filesystem or archive after each phase gate; the
verification CLI already provides everything needed to check an exported copy end to end.

**中文** — 全部权威位于单个 Lustre 命名空间。威胁模型排除"已确认持久对象的永久丢失"，对研究
项目合理 —— 但一次 `rm -rf`、配额清理或 scratch 过期就会抹掉全部已提交轨迹与全部证据。
**方案：** 提供只读导出器（登录节点可安全运行），在每个阶段门后把 head、snapshot 与已提交
可达闭包复制到第二文件系统或归档；现有验证 CLI 已足以对导出副本做端到端校验。
