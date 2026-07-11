# P06A Milestone Report

## English

### Status and implementation

- Phase: P06A — syncer decomposition and reference equivalence
- Branch: `codex/duraloco-p06a-syncer-kernel`
- Read-only P06 archive: `06e3ca2299d5eb1a720c1d8f9107af5223095525`
- Maker implementation: `5a7150220bf3cc6a4a46d2a563466335163d21ad`
- Current status: `checking`
- Acceptance: P06A-A01 through P06A-A20 pass at the Maker gate

P06A decomposes the Central Reference Syncer without changing topology or
authority. Deterministic selection/planning, ordered reduction and outer-step,
transaction-attempt construction, and semantic-digest policy now live behind a
one-way `syncer -> syncer_core` dependency. Production still has one fenced
committer and one global CAS head. Inactive strict FWO/PFT v1 schemas and a
prepare-only immutable object facade freeze the P06B boundary without activating
membership, ownership, learner-hosted execution, or a second authority.

### Equivalence and qualification evidence

The archive-bound oracle executes the unmodified `06e3ca2` implementation from
a detached worktree. For the frozen trace, selected IDs, hexadecimal weights,
aggregate bytes, parameter bytes, and outer-state bytes exactly equal the
decomposed path. Byte identity, paired-state semantic identity, and cross-backend
numeric equivalence remain explicitly separate claims.

The final clean implementation commit passed the focused characterization gate
(104 tests), C1 full suite (396 passed, one explicit skip) plus real GPT-2/
WikiText-2 with four local steps, finite losses, one optimizer transition and
two boundary adoptions, then C2 with two hosts, two optimizer transitions, warm
restart reconciliation and authoritative stop. C9 used one active/standby CRS
node and eight learner nodes, committed exactly 10 optimizer transitions plus
three control transitions, retained 11 checkpoints, recorded 96 finite losses,
and reported zero split brain and zero double inclusion. Active-to-standby
takeover was 69.179 s and standby strict replay was 22.286 s.

### Failure history and repair

Early wrapper-only attempts exposed missing P06A manifest enums; the archive
oracle was then moved to a detached read-only worktree. The first final C2 run
found a real marker-last retention race: terminal cleanup could unlink a fresh
unpaired tensor between writer rename and metadata publication. The repair gives
fresh unpaired artifacts a bounded grace period while preserving immediate
cleanup as an explicit zero-grace mode. A targeted one-node regression, C1 and
C2 all passed on the repaired clean commit before the single C9 attempt.

### Limitations

P06A deliberately retains the central syncer topology. The prepare facade is a
software least-authority boundary for crash/omission failures, not a Byzantine
same-Unix-account sandbox. Distributed membership, factor-1 ownership, LFE
processes and Floating Committer execution begin only in a new P06B generation.
P06A completion does not authorize merging `main`.

## 中文

### 状态与实现

- 阶段：P06A — syncer decomposition 与 reference equivalence
- 分支：`codex/duraloco-p06a-syncer-kernel`
- 只读 P06 archive：`06e3ca2299d5eb1a720c1d8f9107af5223095525`
- Maker implementation：`5a7150220bf3cc6a4a46d2a563466335163d21ad`
- 当前状态：`checking`
- 验收：Maker gate 中 P06A-A01 至 P06A-A20 全部通过

P06A 在不改变 topology 与 authority 的前提下分解 Central Reference Syncer。确定性
selection/planning、ordered reduction 与 outer-step、transaction-attempt 构造和 semantic
digest policy 现在位于单向 `syncer -> syncer_core` 依赖边界之后。production 仍只有一个
fenced committer 与一个 global CAS head。inactive 严格 FWO/PFT v1 schema 和
prepare-only immutable object facade 冻结 P06B 边界，但不启用 membership、ownership、
learner-hosted execution 或第二 authority。

### 等价与 qualification 证据

绑定 archive 的 oracle 从 detached worktree 执行未修改的 `06e3ca2` 实现。冻结 trace
上的 selected ID、十六进制 weight、aggregate bytes、parameter bytes 与 outer-state bytes
都和 decomposed path 完全一致。byte identity、parameter/state paired semantic identity
与跨 backend numeric equivalence 仍是明确分离的主张。

最终干净 implementation commit 依次通过 focused characterization gate（104 项测试）、
C1 完整 suite（396 项通过、1 项显式跳过）及真实 GPT-2/WikiText-2 路径；该路径完成四个
local step、finite loss、一个 optimizer transition 和两次 boundary adoption。随后 C2
在两个 host 上完成两个 optimizer transition、warm restart reconciliation 与权威 stop。
C9 使用一个 active/standby CRS node 和八个 learner node，恰好提交 10 个 optimizer
transition 与三个 control transition，保留 11 个 checkpoint，记录 96 个 finite loss，
split brain 与 double inclusion 均为零。active 到 standby takeover 为 69.179 秒，standby
strict replay 为 22.286 秒。

### 失败历史与修复

早期 wrapper-only attempt 暴露 P06A manifest enum 缺失；之后 archive oracle 被移到
detached read-only worktree。第一次 final C2 发现真实 marker-last retention race：terminal
cleanup 可能在 writer rename 与 metadata publication 之间删除新鲜且尚未配对的 tensor。
修复为新鲜 unpaired artifact 设置有界 grace period，同时保留显式 zero-grace immediate
cleanup 模式。修复后的同一干净 commit 先通过 targeted 单节点 regression、C1 与 C2，
然后才执行唯一一次 C9。

### 限制

P06A 有意保留 central syncer topology。prepare facade 是 crash/omission failure model 下的
software least-authority 边界，而不是抵抗同一 Unix 账号 Byzantine code 的 sandbox。
distributed membership、factor-1 ownership、LFE process 与 Floating Committer 仅在新的
P06B generation 中开始。P06A 完成不授权合并 `main`。
