# Code-Level Findings / 代码层发现

Format per finding: problem → evidence → impact → recommended fix.
每项格式：问题 → 证据 → 影响 → 建议修复。

---

## C-01 (HIGH) — Unbounded operation history, scanned linearly per replay / 操作历史无界且每次 replay 线性重扫

**EN — Problem.** `PosixStorageBackend` appends an `OperationRecord` to `self._history` for
*every* storage operation and never truncates (`fs_diloco/storage/posix.py:153`, `231-235`).
Replay telemetry then *scans the whole list* to count gets:
`sum(record.operation == "get" for record in backend.history)`
(`fs_diloco/log/replay.py:1399-1403`, `fs_diloco/log/production.py:316-327`), on every
snapshot-mode replay call.

**Impact.** In a long-lived committer, memory grows with total operations (millions of records
for a long run), and each replay's telemetry preamble costs O(total ops so far) — a quadratic
total. This is a genuine leak in the exact process that must stay healthy the longest.

**Fix.** Keep monotonic integer counters per operation type (the pattern already exists for
`read_counters`, `posix.py:201-212`) and have telemetry read counters. Make list-based history
opt-in (`record_history=True`) for tests/contract workers that inspect it
(`storage/miyabi_contract_worker.py`, `capability_probe.py`).

**中文 — 问题。** `PosixStorageBackend` 对*每次*存储操作都往 `self._history` 追加一条
`OperationRecord`，从不截断（`posix.py:153`、`231-235`）。replay 遥测又对整个列表做线性统计
（`replay.py:1399-1403`、`production.py:316-327`），每次 snapshot 模式 replay 都会执行。

**影响。** 长活 committer 的内存随总操作数增长（长运行达数百万条记录），每次 replay 的遥测
前置成本为 O(至今全部操作) —— 累计为平方级。这泄漏恰好发生在最需要长期健康的进程里。

**修复。** 按操作类型维护单调整数计数器（`read_counters` 已是这个模式，
`posix.py:201-212`），遥测改读计数器。列表式 history 改为 `record_history=True` 显式开启，
供测试与契约 worker（`miyabi_contract_worker.py`、`capability_probe.py`）使用。

---

## C-02 (HIGH) — LFE RSS budget uses lifetime peak / LFE 内存预算用终身峰值

**EN — Problem.** `execute_work_order` enforces the RSS budget with
`resource.getrusage(RUSAGE_SELF).ru_maxrss` (`fs_diloco/distributed_syncer/executor.py:220-222`).
`ru_maxrss` is the process's *lifetime high-water mark*: it never decreases.

**Impact.** One transient spike (a large early allocation, an unusually big fragment, allocator
fragmentation) permanently exceeds the budget, and *every subsequent work order in that LFE
process* raises `MemoryError` — even though current usage is fine. In factor-1 topologies this
turns one spike into a stalled fragment until the process is restarted; the check also fires
*after* payload publication, leaving orphan payloads each time.

**Fix.** Measure current RSS (`/proc/self/statm` × page size) or the delta of `ru_maxrss`
across the work order, and check *before* publishing payloads. If the budget is meant to bound
the whole process lifetime, then breaching it should terminate the process (so a supervisor
restarts it) rather than fail every order from a live process.

**中文 — 问题。** `execute_work_order` 用 `ru_maxrss` 执法 RSS 预算
（`executor.py:220-222`），而 `ru_maxrss` 是进程*终身高水位*，永不下降。

**影响。** 一次瞬时尖峰（早期大分配、特大 fragment、分配器碎片化）会永久超预算，该 LFE 进程
*之后的所有工单*都抛 `MemoryError` —— 即便当前占用完全正常。factor-1 拓扑下一次尖峰即令
fragment 停摆直至进程重启；且该检查在 payload 发布*之后*触发，每次都留下孤儿 payload。

**修复。** 改测当前 RSS（`/proc/self/statm` × 页大小）或工单前后 `ru_maxrss` 差值，并在发布
payload *之前*检查。若预算本意是约束进程全生命周期，则超限应终止进程（由监督者重启），而非
让活进程拒绝所有后续工单。

---

## C-03 (MEDIUM) — `list_prefix` silently hides corrupt objects / `list_prefix` 静默隐藏损坏对象

**EN — Problem.** During listing, any file whose envelope header fails to parse is skipped
without trace: `except (NotFound, IntegrityError, StorageIOError): continue`
(`fs_diloco/storage/posix.py:839-842`).

**Impact.** The storage contract requires corrupt/unknown objects to be *discoverable* so
lifecycle can count, protect, and explain them. A header-corrupted object becomes invisible to
reachability inventory and lifecycle reports. GC safety survives (invisible ⇒ never a delete
candidate), but the "explainable inventory" property and corruption observability are silently
lost — precisely in the situation they exist for.

**Fix.** Collect unreadable keys into a separate bucket and surface them: either return an
optional `(keys, unreadable)` result or add `list_prefix_report()`. Lifecycle should log and
count `unreadable_object_count > 0` as a corruption signal (it already treats unknown objects
as protected).

**中文 — 问题。** 列举时，envelope header 解析失败的文件被无痕跳过
（`posix.py:839-842` 的 `except … continue`）。

**影响。** 存储契约要求损坏/未知对象必须*可被发现*，以便 lifecycle 统计、保护并解释它们。
header 损坏的对象对可达性盘点与 lifecycle 报告完全不可见。GC 安全性尚存（不可见 ⇒ 永不成为
删除候选），但"可解释盘点"与腐坏可观测性被静默丢失 —— 恰恰是它们存在的意义所在。

**修复。** 把不可读 key 收进单独桶并上报：返回可选的 `(keys, unreadable)` 或新增
`list_prefix_report()`。lifecycle 应把 `unreadable_object_count > 0` 记为腐坏信号（未知对象
本就按受保护处理）。

---

## C-04 (MEDIUM) — Backend re-constructed per proposal publication / 每次发布 proposal 重建后端

**EN — Problem.** `write_update` / `write_fragment_update` construct a fresh
`PosixStorageBackend(paths.authority)` on every call (`fs_diloco/learner.py:535`, `627`; also
`783`, `1297` per process — those are fine). Each construction re-reads
`/proc/self/mountinfo`, re-probes directory fsync (an `open`+`fsync` on the authority root),
and re-derives lock-capability state (`posix.py:124-178`).

**Impact.** Per-interval overhead and unnecessary metadata traffic on Lustre, multiplied by
8 learners × every interval. Also means capability failures surface mid-training rather than at
startup.

**Fix.** Construct one backend per learner process (alongside the logger/session) and thread it
into the publication helpers; the publisher (`learner_protocol/publication.py`) already accepts
a backend argument.

**中文 — 问题。** `write_update` / `write_fragment_update` 每次调用都新建
`PosixStorageBackend(paths.authority)`（`learner.py:535`、`627`）。每次构造都重读
`/proc/self/mountinfo`、重新探测目录 fsync（对权威根做 `open`+`fsync`）、重新推导锁能力
（`posix.py:124-178`）。

**影响。** 每 interval 的固定开销与不必要的 Lustre 元数据流量，乘以 8 learner × 每个
interval。且能力故障会在训练中途而非启动时暴露。

**修复。** 每个 learner 进程构造一个后端（与 logger/session 同级）并传入发布辅助函数；
`learner_protocol/publication.py` 的 publisher 本就接受后端参数。

---

## C-05 (MEDIUM) — Lock inodes accumulate forever / 锁 inode 永久累积

**EN — Problem.** Every mutated key gets a dedicated lock file
`.duraloco-locks/<sha256(key)>.lock` that is never removed (`posix.py:306-308`; the docstring
at `posix.py:846-849` says persistent inodes are harmless — for *correctness* they are).

**Impact.** One lock inode per immutable object ever published. A long run with millions of
objects creates millions of never-reclaimed inodes in one directory — Lustre metadata-server
pressure and slow directory operations, plus inode quota consumption.

**Fix.** Immutable creates don't need per-key exclusivity, only a short mutual-exclusion
window; hash keys into a fixed pool of lock buckets (e.g. 4096) for `put_immutable`, keeping
dedicated locks only for the few truly mutable keys (head, lease). Bucketing adds negligible
contention (locks are held for microseconds around rename) and caps inode count permanently.

**中文 — 问题。** 每个被修改过的 key 都会得到一个专属锁文件
`.duraloco-locks/<sha256(key)>.lock` 且永不删除（`posix.py:306-308`；`846-849` 的文档说持久
inode 无害 —— 就*正确性*而言确实无害）。

**影响。** 每发布一个不可变对象就多一个 inode。数百万对象的长运行会在单目录下留下数百万个
永不回收的 inode —— Lustre 元数据服务器压力、目录操作变慢、inode 配额消耗。

**修复。** 不可变创建不需要按 key 独占，只需短暂互斥窗口；对 `put_immutable` 把 key 哈希进
固定数量的锁桶（如 4096），仅对真正可变的少数 key（head、lease）保留专属锁。桶化的争用可
忽略（锁只在 rename 前后持有微秒级），且永久封顶 inode 数。

---

## C-06 (MEDIUM) — Swallowed snapshot-validation failure / snapshot 验证失败被吞

**EN — Problem.** During strict replay, a pinned snapshot that fails verification is ignored
via bare `except Exception: pass` (`fs_diloco/log/replay.py:1081-1082`).

**Impact.** The *policy* is right (a corrupt snapshot must not block strict replay), but the
*silence* is wrong: a corrupted pinned snapshot is a corruption event in the authority
namespace and currently produces no log line, no telemetry, no quarantine — it is discovered
only when a snapshot-mode replay later falls back (or never).

**Fix.** Keep the fallback; record the event (key, commit_seq, exception type) into the replay
telemetry / an `OrphanReport`-like structure so lifecycle reports can count invalid pinned
snapshots. One narrow `except (VerificationError, IntegrityError, NotFound, ValueError)` is
also safer than bare `Exception`.

**中文 — 问题。** strict replay 中，验证失败的 pinned snapshot 被裸
`except Exception: pass` 忽略（`replay.py:1081-1082`）。

**影响。** *策略*正确（snapshot 损坏不得阻塞 strict replay），*沉默*不对：pinned snapshot
损坏是权威命名空间内的腐坏事件，目前既无日志也无遥测也不 quarantine —— 只有当之后
snapshot 模式 replay 回退时才（或永不）被发现。

**修复。** 保留回退；把事件（key、commit_seq、异常类型）记入 replay 遥测或类
`OrphanReport` 结构，使 lifecycle 报告能统计无效 pinned snapshot。同时把裸 `Exception` 收窄
为 `(VerificationError, IntegrityError, NotFound, ValueError)` 更安全。

---

## C-07 (MEDIUM) — Result-wait loop re-reads everything; hedge timing crosses clocks / 等结果循环重复读取；hedge 计时跨时钟

**EN — Problem.** `_wait_for_result` polls every 100 ms; on *each* poll it re-lists the marker
prefix and calls `load_prepared_attempt` (full manifest + envelope reads) for **every** marker,
including ones already loaded on previous polls (`committer.py:241-254`). Hedge eligibility
compares committer-side `time.time()` with the `published_at` timestamp written by (possibly)
another host (`committer.py:277-289`).

**Impact.** During a ~7 s LFE compute that is ~70 polls × (listing + N object reads) of
pure redundancy — measurable Lustre metadata traffic inside the critical
`prepared_visibility` stage (79→126 s aggregate in P08R). Clock mixing skews hedge delays by
inter-host offset (performance-only, but it distorts the 6000 ms policy).

**Fix.** Memoize loaded attempts by marker key across polls (they are immutable); optionally
back off the poll interval adaptively (100 ms → 500 ms after the first second). For hedge
timing, compute elapsed from the committer's own monotonic clock started at dispatch (it wrote
`active_work_order.json` itself — `published_at` need not be trusted cross-host).

**中文 — 问题。** `_wait_for_result` 每 100ms 轮询；*每次*轮询都重新列举 marker 前缀并对
**每个** marker 调 `load_prepared_attempt`（完整 manifest+envelope 读取），包括之前轮询已
加载过的（`committer.py:241-254`）。hedge 资格用 committer 侧 `time.time()` 与（可能）另一
主机写入的 `published_at` 比较（`committer.py:277-289`）。

**影响。** LFE 约 7 秒计算期间约 70 次轮询 ×（列举 + N 次对象读）纯冗余 —— 是关键
`prepared_visibility` 阶段（P08R 中合计 79→126 秒）内可测的 Lustre 元数据流量。时钟混用使
hedge 延迟偏移主机间时差（仅影响性能，但扭曲 6000ms 策略）。

**修复。** 按 marker key 跨轮询记忆化已加载 attempt（它们不可变）；轮询间隔可自适应退避
（首秒后 100ms → 500ms）。hedge 计时改用 committer 自身单调时钟自派发起算（
`active_work_order.json` 本就是它自己写的 —— 无需跨主机信任 `published_at`）。

---

## C-08 (LOW) — Idempotent immutable put trusts header only / 幂等不可变写只信 header

**EN** — On an idempotent hit, `put_immutable` compares only the envelope header's size/sha
against the caller's bytes (`posix.py:608-619`) — it never reads the stored payload. If the
stored payload is corrupt under a valid header (torn write survived by an earlier crash, or
later bit rot), the one moment when a caller *provably holds the correct bytes* passes without
repair; the corruption is found later by some `verified_get`, which can only fail closed.
**Fix:** on idempotent hits, optionally verify the payload (cheap for manifests; gate by size
for tensors) and, on mismatch, repair-in-place under the key lock via the normal temp+rename
path — the envelope design makes this an atomic replacement of provably-identical logical
content.

**中文** — 幂等命中时 `put_immutable` 只比对 envelope header 的 size/sha 与调用方字节
（`posix.py:608-619`），从不读存储的 payload。若 header 完好而 payload 损坏（早年崩溃留下的
撕裂写或后来位腐），调用方*可证明手握正确字节*的唯一时机被白白放过；损坏要等某次
`verified_get` 才发现，而那时只能失败关闭。**修复：** 幂等命中时可选校验 payload（manifest
类很廉价；张量按大小设门槛），不符时在 key 锁内走常规 temp+rename 原地修复 —— envelope 设计
使这成为对"逻辑内容可证明相同"对象的原子替换。

---

## C-09 (LOW) — Doc drift on `range_get` / `range_get` 文档漂移

**EN** — The storage-contract document still states `range_get` performs a full `get` then
slices and "must not claim true range I/O". The code has since implemented v2 envelopes with
per-64 MiB chunk digests and verified chunked range reads (`posix.py:720-780`, commit
`50fd036`). **Fix:** update the storage contract (and any P08 planning references) to describe
v2 range semantics, including the v1-envelope fallback that still reads the full payload.

**中文** — 存储契约文档仍称 `range_get` 是全量 `get` 后切片、"不得声称真范围 I/O"。代码已实现
v2 envelope（每 64MiB 分块 digest）与可校验分块范围读（`posix.py:720-780`，提交
`50fd036`）。**修复：** 更新存储契约（及 P08 计划中的相应表述），描述 v2 范围语义，并注明
v1 envelope 回退路径仍读全量 payload。

---

## C-10 (LOW) — docs/ tree deleted while still referenced / docs/ 被删但仍被引用

**EN** — At review time the working tree has all of `docs/` deleted (moved to `docs-codex/`,
untracked), while the top-level `README.md` links to `docs/README.md`, `docs/status.md`, etc.,
and `scripts/agent/check_docs.py` lists those paths as CURRENT_DOCS — so the docs checker and
every README link are currently broken. **Fix:** finish the rewrite atomically in one commit:
either move `docs-codex/` back to `docs/` (merging with this review set) or update `README.md`
+ `check_docs.py` to the new layout in the same change.

**中文** — 评审时工作树中 `docs/` 全部处于删除状态（内容移到未跟踪的 `docs-codex/`），而顶层
`README.md` 仍链接 `docs/README.md`、`docs/status.md` 等，`scripts/agent/check_docs.py` 也把
这些路径列为 CURRENT_DOCS —— 目前 docs 检查器与 README 全部链接都是断的。**修复：** 在一个
提交中原子完成重写：把 `docs-codex/` 移回 `docs/`（与本评审文档集合并），或在同一变更中同步
更新 `README.md` 与 `check_docs.py` 到新布局。

---

## C-11 (LOW) — Leaked temp files have no janitor / 泄漏的临时文件无人清理

**EN** — `_publish` creates `.duraloco-tmp` files; a crash between `os.link(temp, path)` and
`temp.unlink()` (or before publish) leaks them (`posix.py:540-589`). Listing skips them
(`posix.py:834`), so they are invisible *and* immortal. **Fix:** lifecycle inventory should
count `.duraloco-tmp` files and delete those older than a grace age (they are by construction
never referenced); this is safe because visible names are only created by `link`/`replace`.

**中文** — `_publish` 创建 `.duraloco-tmp` 临时文件；在 `os.link(temp, path)` 与
`temp.unlink()` 之间（或发布前）崩溃会泄漏它们（`posix.py:540-589`）。列举会跳过它们
（`posix.py:834`），于是既不可见又永生。**修复：** lifecycle 盘点应统计 `.duraloco-tmp` 并
删除超过宽限期的（构造上它们永不被引用）；因可见名只经 `link`/`replace` 产生，此清理是安全
的。

---

## C-12 (LOW) — Per-call `atexit` registration / 每次调用注册 `atexit`

**EN** — `run_committer` registers `atexit.register(stage_recorder.close)` on every invocation
(`committer.py:609`); in a long-lived process that calls it repeatedly (tests, standby loops)
handlers and recorder references accumulate. **Fix:** use `try/finally` (the `finally` block
already calls `stage_recorder.close()` at `committer.py:1457`) and drop the `atexit` hook, or
unregister it on exit.

**中文** — `run_committer` 每次调用都注册 `atexit.register(stage_recorder.close)`
（`committer.py:609`）；在反复调用它的长活进程（测试、standby 循环）中，处理器与 recorder
引用会累积。**修复：** 依赖既有的 `finally` 关闭（`committer.py:1457` 已调用
`stage_recorder.close()`），去掉 `atexit`，或退出时反注册。

---

## C-13 (LOW) — Default materialization writes the full model every transition / 默认物化每次全量写整模型

**EN** — `materialize_full_every_events` defaults to `None` (`config.py:164`), and
`publish_materialized_view` treats `None` as "full materialization due every transition"
(`syncer.py:193-199`). With fragment mode the per-fragment files alone would serve learners;
the full flat-weights file mainly serves eval/checkpointing. **Fix:** default the cadence to a
value ≥ number of fragments (or make `None` mean "only at stop/snapshot"), and document the
knob in the run configs; combined with D-04(b) this removes a full-model write from the
critical path.

**中文** — `materialize_full_every_events` 默认 `None`（`config.py:164`），而
`publish_materialized_view` 把 `None` 当作"每次 transition 都要全量物化"
（`syncer.py:193-199`）。fragment 模式下每 fragment 文件已足够服务 learner；整模型平铺权重
文件主要服务评测/checkpoint。**修复：** 默认节奏设为 ≥ fragment 数（或让 `None` 表示"仅在
stop/snapshot 时"），并在运行配置中写明该开关；配合 D-04(b) 可把一次全模型写移出关键路径。
