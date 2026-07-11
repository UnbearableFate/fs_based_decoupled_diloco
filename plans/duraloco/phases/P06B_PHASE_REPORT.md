# P06B Milestone Report

## English

### Status and implementation

- Phase: P06B — learner-hosted fragment executors and distributed prepare
- Branch: `codex/duraloco-p06b-learner-hosted-sync`
- P06A basis: `4ce89280f99553f6d81821978367c53acaf10214`
- Runtime implementation: `d5e2901b75ef504a31a365790b7b9518c329dbe7`
- Evidence tooling: `8b1c47683d42ee547c9bbfdc95e15958bbeb6afb`
- Maker acceptance: P06B-A01–A21 and A23 pass; A22 awaits the independent Checker
- Current status: `checking`

P06B starts a fresh `distributed-head-fenced-v1` generation. Its genesis freezes
revision-zero membership, factor-one rendezvous ownership, executor sessions,
prepare capability, and CPU numeric implementation. Separate learner-hosted LFEs
receive a restricted prepare-only facade; Floating Committers reuse the P05
observational lease, committed fencing epoch, and single global head CAS. PFT
result identity excludes executor, attempt, timing, and arrival order.

### Qualification evidence

The clean runtime commit passed 105 focused tests, D1 (`2362549.opbs`), D2
(`2362562.opbs`), and D8 (`2362567.opbs`) in order. D2 killed and restarted an
executor, killed the active committer, took over at epoch 2, killed the complete
factor-one owner host, committed membership revision 1, and completed exactly
three optimizer transitions. D8 used exactly eight learner nodes, eight learners,
eight LFEs, two learner-hosted committer candidates, and no dedicated syncer. It
completed GPT-2/WikiText-2 50x10 in 470 seconds with 10 marker-last prepares, 10
optimizer transitions, 88 finite interval losses, and authoritative stop.

The D8 resource report records all executor CPU affinities (cores 64–71), two
NUMA memory nodes, eight threads, peak LFE RSS 11.02 GB, 440 sampled GPU steps
(mean 27.75 ms), 39.82 GB of logical LFE I/O, 150 logical LFE object operations,
and 42.81 GB/473 objects in the terminal authority inventory. Every transition
has publish→prepare→commit→adopt timing; all eight learners adopted each commit.

Comparison PBS `2362603.opbs` retained both final content digests and backend
identities. Policy, selected counts, hexadecimal weights, optimizer identity,
and every FWO/PFT/final content link are exact. CUDA CRS and CPU LFE tensors pass
the frozen `atol=0.05`, `rtol=0.10` gate (max absolute difference 0.041680,
relative L2 0.010914); no cross-backend content-identity claim is made.

### Failure history and limitations

Comparison discovery initially treated POSIX envelopes as raw JSON and later
mistook all immutable commit objects for committed ancestry. The final tool reads
canonical payloads through the backend and folds only the global-head prefix.
A D8 run exposed the terminal standby race: stop can commit between the
post-lease replay and epoch preparation. The repaired runtime treats the expected
`CommitConflict` as terminal, records the race, and creates no successor or
orphan commit. The facade is a crash/omission least-authority boundary, not a
Byzantine sandbox for arbitrary code under the same Unix account. P06B provides
factor one only; overlapping prepare begins in P06C.

## 中文

### 状态与实现

- 阶段：P06B — learner-hosted fragment executor 与 distributed prepare
- 分支：`codex/duraloco-p06b-learner-hosted-sync`
- P06A 基线：`4ce89280f99553f6d81821978367c53acaf10214`
- Runtime implementation：`d5e2901b75ef504a31a365790b7b9518c329dbe7`
- Evidence tooling：`8b1c47683d42ee547c9bbfdc95e15958bbeb6afb`
- Maker 验收：P06B-A01 至 P06B-A23 全部通过

P06B 启动全新的 `distributed-head-fenced-v1` generation。genesis 冻结 revision-zero
membership、factor-one rendezvous ownership、executor session、prepare capability 与
CPU numeric implementation。每个 learner host 启动独立 LFE，且 LFE 只获得 prepare-only
facade；Floating Committer 复用 P05 observational lease、committed fencing epoch 与唯一
global-head CAS。PFT result identity 不包含 executor、attempt、timing 或到达顺序。

### Qualification 证据

干净 runtime commit 依次通过 105 项 focused test、D1（`2362549.opbs`）、D2
（`2362562.opbs`）和 D8（`2362567.opbs`）。D2 覆盖 executor 重启、active committer
kill、epoch 2 takeover、完整 factor-one owner host kill、membership revision 1 commit，并
恰好完成三个 optimizer transition。D8 只使用八个 learner node，运行八个 learner、八个
LFE、两个 learner-hosted committer candidate，专用 syncer node 为零；GPT-2/WikiText-2
50x10 在 470 秒内完成，共有 10 个 marker-last prepare、10 个 optimizer transition、88 个
finite interval loss 与权威 stop。

D8 resource report 记录全部 executor 的 CPU affinity（64–71）、两个 NUMA memory node、
八线程、LFE peak RSS 11.02 GB、440 个 GPU step sample（平均 27.75 ms）、39.82 GB logical
LFE I/O、150 次 logical LFE object operation，以及 terminal authority 的 42.81 GB/473 个
object。每个 transition 都有 publish→prepare→commit→adopt 分段时延，且每次 commit 均被
八个 learner adopt。

comparison PBS `2362603.opbs` 保留双方 final content digest 与 backend identity。policy、
selected count、十六进制 weight、optimizer identity 及每个 FWO/PFT/final content link 都
exact。CUDA CRS 与 CPU LFE tensor 通过冻结的 `atol=0.05`、`rtol=0.10` gate（最大绝对差
0.041680，relative L2 0.010914），且没有声称跨 backend content identity。

### 失败历史与限制

早期 comparison discovery 曾把 POSIX envelope 当成 raw JSON，随后又把所有 immutable
commit object 误当成 committed ancestry。最终工具通过 backend 解码 canonical payload，
且只 fold global-head prefix。一次 D8 暴露 terminal standby race：stop 可能在 post-lease
replay 与 epoch prepare 之间提交。修复后的 runtime 将预期 `CommitConflict` 解析为 terminal，
保留 race evidence，且不生成 successor 或 orphan commit。facade 是 crash/omission model
下的 least-authority 边界，不是同一 Unix 账号任意代码的 Byzantine sandbox。P06B 仅提供
factor one；overlapping prepare 从 P06C 开始。
