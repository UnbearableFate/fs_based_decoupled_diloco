# Executive Summary / 发现速览

**EN** — 24 findings: 11 design-level (D), 13 code-level (C). Ranked by severity within each
group. Details and solutions: `02_design_findings.md`, `03_code_findings.md`.

**中文** — 共 24 项发现：设计层 11 项（D）、代码层 13 项（C）。组内按严重度排序。详情与方案
见 `02_design_findings.md` 与 `03_code_findings.md`。

## Design findings / 设计层发现

| ID | Sev. | Finding / 发现 |
|---|---|---|
| D-01 | HIGH | Frontier `consumed_proposal_ids` grows forever → O(n) frontier objects, O(n²) cumulative log I/O / frontier 消费集永久增长 → frontier 对象 O(n)、日志累计 I/O O(n²) |
| D-02 | HIGH | Per-commit `_prefix_digest` re-hashes the whole prefix → O(n²)–O(n³) work inside every strict replay / 每 commit 重算全前缀 digest → strict replay 内部 O(n²)–O(n³) |
| D-03 | HIGH | Snapshots embed the complete history; I-008 equality over full `ReplayResult` forbids truncation → snapshots grow ~O(n²) / snapshot 内嵌全历史，且 I-008 按完整 `ReplayResult` 判等禁止截断 → snapshot 约 O(n²) 增长 |
| D-04 | MEDIUM | Fully serial committer pipeline (one fragment per transition, fixed 0.5 s sleep) bounds global throughput / committer 全串行（每次一个 fragment、固定 0.5 秒睡眠）限制全局吞吐 |
| D-05 | MEDIUM | Full params+outer payloads written twice and read ≥2× per transition (~4× model-size Lustre traffic) / 每次 transition params+outer 全量写两次、读至少两次（约 4 倍模型体量的 Lustre 流量） |
| D-06 | MEDIUM | Hedged mode requires *both* attempts once the backup activates — hedging adds latency instead of cutting it / hedged 模式 backup 激活后要求*双份*结果 —— 对冲反而增加延迟 |
| D-07 | MEDIUM | Learners adopt derived weight files with no digest verification against committed refs / learner 采用派生权重文件时不对照已提交引用做 digest 校验 |
| D-08 | MEDIUM | Lease safety depends on cross-node wall-clock sync (≤2 s skew) that is assumed, never probed / lease 安全依赖跨节点时钟同步（≤2 秒偏差）——只是假设，从未探测 |
| D-09 | LOW | 37–47 s takeover floor is a config policy, not a physical bound; a justified-tuning path is missing / 37–47 秒接管下限是配置策略而非物理界限，缺少"论证后调参"路径 |
| D-10 | LOW | No automatic failed-member reintegration (documented gap; roadmap suggestion) / 无失败成员自动重入（已声明缺口；给出路线建议） |
| D-11 | LOW | Single-filesystem authority has no disaster-recovery export / 单文件系统权威缺少灾备导出 |

## Code findings / 代码层发现

| ID | Sev. | Finding / 发现 |
|---|---|---|
| C-01 | HIGH | `PosixStorageBackend._history` grows unboundedly and is linearly re-scanned per replay → memory leak + quadratic telemetry cost / `_history` 无界增长且每次 replay 线性重扫 → 内存泄漏 + 遥测成本平方级 |
| C-02 | HIGH | LFE RSS budget uses `ru_maxrss` (lifetime peak): one spike permanently poisons every later work order in that process / LFE 用 `ru_maxrss`（终身峰值）判预算：一次尖峰永久毒化该进程后续所有工单 |
| C-03 | MEDIUM | `list_prefix` silently drops corrupt-envelope files — contradicts the explainable-inventory contract / `list_prefix` 静默丢弃 envelope 损坏文件 —— 违背可解释盘点契约 |
| C-04 | MEDIUM | A new `PosixStorageBackend` (with capability probes) is constructed for *every* learner proposal publication / 每次 learner 发布 proposal 都新建一个 `PosixStorageBackend`（含能力探测） |
| C-05 | MEDIUM | One lock inode is created per storage key and never reclaimed → unbounded Lustre metadata growth / 每个存储 key 产生一个永不回收的锁 inode → Lustre 元数据无界增长 |
| C-06 | MEDIUM | Pinned-snapshot validation failure during replay is swallowed with no log/telemetry / replay 中 pinned snapshot 验证失败被静默吞掉，无日志/遥测 |
| C-07 | MEDIUM | `_wait_for_result` re-reads *all* attempt objects every 100 ms poll; hedge timing compares clocks across hosts / `_wait_for_result` 每 100ms 轮询重读*全部* attempt 对象；hedge 计时跨主机比较时钟 |
| C-08 | LOW | `put_immutable` idempotent hit trusts the header only — misses a free payload-repair opportunity / `put_immutable` 幂等命中只信 header —— 错过免费的 payload 修复机会 |
| C-09 | LOW | Doc drift: storage contract still says `range_get` is not true range I/O; the code now has verified chunked range reads / 文档漂移：存储契约仍称 `range_get` 非真范围 I/O，代码已实现分块校验范围读 |
| C-10 | LOW | `docs/` tree deleted mid-rewrite while `README.md` and `check_docs.py` still point at it / `docs/` 在重写中被删除，而 `README.md` 与 `check_docs.py` 仍指向它 |
| C-11 | LOW | Crash between `link` and temp-unlink leaks `.duraloco-tmp` files; no janitor / `link` 与临时文件删除之间崩溃会泄漏 `.duraloco-tmp` 文件；无清理者 |
| C-12 | LOW | `atexit` handler registered per `run_committer` call accumulates in long-lived processes / 每次调用 `run_committer` 注册一个 `atexit` 处理器，长活进程中累积 |
| C-13 | LOW | Default `materialize_full_every_events=None` forces a full-model weight write after every transition / 默认 `materialize_full_every_events=None` 使每次 transition 都全量写整模型权重 |

## The three structural risks in one paragraph / 三大结构性风险一段话

**EN** — D-01, D-02, and D-03 interact: frontiers carry an ever-growing consumption set, every
replay re-hashes every prefix at every step, and every snapshot embeds every past object. At the
validated scale (10 transitions) all three are invisible; at 500+ transitions the *audit
machinery itself* becomes the dominant and eventually prohibitive cost, even though the protocol
remains correct. All three have solutions that preserve every safety invariant (rolling digests,
watermark-based consumption bounds, state-based snapshot equivalence) but require a schema
change, i.e. a new run generation — which the generation mechanism was explicitly built for.

**中文** — D-01、D-02、D-03 相互叠加：frontier 携带只增不减的消费集，replay 在每一步重新哈希
全部前缀，snapshot 内嵌全部历史对象。在已验证规模（10 次 transition）下三者都不可见；到 500+
次时，*审计机制本身*会成为主导乃至不可承受的成本 —— 尽管协议依然正确。三者的解法（滚动
digest、基于水位线的消费集界定、基于状态的 snapshot 等价）都能保全全部安全不变量，但需要
schema 变更，即开新 run generation —— 而 generation 机制正是为此而设计的。
