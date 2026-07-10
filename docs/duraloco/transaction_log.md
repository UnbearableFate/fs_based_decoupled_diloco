# DuraLoCo P04 Transaction Log Contract

## Authority and commit point

`runs/<run>/generations/<generation>/control/head.json` is the only mutable
authority. Genesis uses create-if-absent setup; every optimizer transition
after genesis becomes committed only through one `conditional_replace` of that
head. Params, outer optimizer state, proposal, commit, and frontier objects are
immutable preparations. A complete preparation that loses the head CAS is an
orphan and is never part of replay.

The `parent_head_version` stored in a logical commit is the SHA-256 identity of
the canonical parent head bytes. The opaque backend version/generation is used
only as the CAS precondition and is deliberately excluded from object IDs so
memory and POSIX produce the same committed state digest.

## Durable prefix

Each frontier contains the complete fragment map. Every fragment entry pairs
one params ref and one outer-state ref and names their producing commit. The
frontier also contains the canonical cumulative consumed-proposal set and the
deterministic scheduler cursor. Its parent frontier digest and the deterministic
commit key produce one contiguous global prefix.

Replay starts only from the verified head and checks, for every prefix:

- run/generation, parent, sequence, frontier digest, and commit identity;
- proposal causal base, staleness, lineage monotonicity, and unique inclusion;
- canonical selection weights and the P02 reference optimizer transition;
- params/outer-state content refs and atomic pairing in the successor frontier;
- exact cumulative consumption and scheduler state.

Listing never determines authority. It is used only by orphan inspection.

## Cache and failure behavior

The SQLite consumption database is derived. `rebuild_cache` folds the committed
log into a fresh database and atomically replaces the old cache. Deletion or
corruption of the cache cannot change head, replay, or proposal consumption.

The crash matrix covers before/after each params, outer-state, commit, and
frontier put plus before/after head CAS. Every point recovers to the complete
old prefix, except a crash after successful CAS, which recovers to the complete
new prefix. A retry identifies success by the exact committed head/commit ID;
competing different transitions from one parent have one winner.

## Terminal milestone gate

P04 completes only after the same verified commit passes:

- 1-node Lustre commit/replay/cache/crash validation;
- 2-node same-parent competing writers;
- a qsub 9-node, 15-minute real `gpt2` + WikiText-2 run with one syncer and
  eight learners, `inner_steps=50`, and exactly ten outer transitions;
- a P04 probe bound to SHA-256 hashes of all eleven real training checkpoints,
  plus the complete P04 test suite.

P04 does not yet make this log the production syncer authority. That integration
is P05. The terminal P04 probe records deterministic checkpoint-hash projections
so the real training run and P04 semantics share one immutable evidence bundle.

## 中文

### 权威状态与提交点

`runs/<run>/generations/<generation>/control/head.json` 是唯一可变权威。
Genesis 使用 create-if-absent 初始化；genesis 之后的每次 optimizer transition
只有通过一次 head `conditional_replace` 才成为 committed。params、outer
optimizer state、proposal、commit 与 frontier 均是不可变 prepare 对象。即使
prepare 完整，只要 head CAS 未成功，它就是 orphan，replay 不会包含它。

commit 中的 `parent_head_version` 是父 head 规范字节的 SHA-256 逻辑身份。
backend 的不透明 version/generation 只用作 CAS precondition，不进入逻辑 ID，
因此 memory 与 POSIX 可以产生相同的 committed state digest。

### Durable prefix

每个 frontier 保存完整 fragment map；每个 fragment entry 同时绑定 params ref、
outer-state ref 与 producing commit。frontier 还保存规范化累计 consumed-proposal
集合和确定性 scheduler cursor。parent frontier digest 与确定性 commit key 构成
唯一连续的 global prefix。

Replay 只从校验后的 head 开始，并逐 prefix 校验 run/generation、parent、sequence、
digest、proposal 因果 base/staleness/lineage、唯一 inclusion、规范权重、P02
reference optimizer、payload refs、params/outer-state 配对、consumption 和
scheduler state。listing 不决定权威，只用于 orphan inspection。

### Cache、故障与最终 gate

SQLite consumption DB 是派生 cache。删除或损坏后，`rebuild_cache` 从 committed
log 构造新 DB 并原子替换；cache 不改变 head、replay 或 consumption facts。

Crash matrix 覆盖每个 params、outer-state、commit、frontier put 和 head CAS 的
前后。CAS 前恢复旧完整 prefix；CAS 成功后恢复新完整 prefix。基于同一 parent
的不同 transition 只有一个 winner。

P04 只有在同一 verified commit 通过单节点 Lustre、双节点竞争写入，以及
qsub 提交的 9-node/15 分钟真实 GPT-2 + WikiText-2 训练后才完成。训练使用
1 syncer + 8 learners、`inner_steps=50`、恰好 10 次 outer transition，并把
11 个真实 checkpoint 的 SHA-256 绑定到 P04 probe，同时运行完整 P04 tests。

P04 尚不把该 log 设为 production syncer authority；该集成属于 P05。P04 最终
probe 使用真实 checkpoint hash 的确定性 projection，把真实训练与 P04 语义放在
同一个不可变 evidence bundle 中。
