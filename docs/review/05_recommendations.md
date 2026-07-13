# Recommendations & Roadmap / 建议与路线图

**EN** — Grouped by when they should land, respecting the project's own phase discipline
(evidence-gated, 1→2→8-node qualification, no silent schema changes). Effort: S <1 day,
M = days, L = a phase.

**中文** — 按落地时机分组，遵循项目自身的阶段纪律（证据门控、1→2→8 节点资格路径、禁止静默
schema 变更）。工作量：S <1 天，M = 数天，L = 一个阶段。

## P0 — Before any longer run / 任何更长运行之前

| Item | Fix | Effort | Why now / 为何现在 |
|---|---|---|---|
| C-01 | Counters instead of unbounded op history / 用计数器替代无界操作历史 | S | Memory leak + quadratic telemetry in the longest-lived process / 最长活进程中的内存泄漏与平方级遥测 |
| C-02 | Per-order RSS measurement, checked before publication / 按工单测 RSS 并在发布前检查 | S | One spike currently poisons an LFE permanently / 目前一次尖峰即永久毒化 LFE |
| C-04 | One storage backend per learner process / 每 learner 进程一个后端 | S | Removes per-interval probe overhead / 消除每 interval 探测开销 |
| C-12 | Drop per-call `atexit` / 去掉每次调用的 `atexit` | S | Trivial hygiene / 琐碎卫生 |
| C-10 | Land the docs move atomically / 原子完成 docs 迁移 | S | Checker and README are broken right now / 检查器与 README 当前是断的 |

## P1 — Inside the current P08R/P11 performance work / 纳入当前 P08R/P11 性能工作

| Item | Fix | Effort | Expected effect / 预期效果 |
|---|---|---|---|
| C-07 | Memoize attempts across polls; monotonic hedge timing / 轮询间记忆化 attempt；单调时钟对冲计时 | S | Cuts prepared-visibility metadata traffic / 削减 prepared-visibility 元数据流量 |
| D-05 | Zero-copy promotion of prepared payloads into authority / prepared payload 零拷贝晋升为权威 | M | Removes one full model write+read per transition / 每次 transition 少一次全模型写+读 |
| C-13 + D-04b | Materialization cadence + off critical path / 物化按节奏并移出关键路径 | S–M | Removes another full-model write from the loop / 再移除一次全模型写 |
| D-04a/c | Overlap next-fragment validation with PFR wait; tunable sleep / 用 PFR 等待期做下一 fragment 验证；睡眠可调 | M | Pipelines the two largest independent stages / 流水化两个最大的独立阶段 |
| D-06 | Decide hedging semantics: first-valid-commits + async divergence audit, or document hedged as evidence mode with failure-evidence auto-generation / 定夺对冲语义 | M (policy + tests) | Recovers the intended tail-latency benefit / 找回对冲本意的尾延迟收益 |
| C-03, C-06 | Surface unreadable objects and invalid pinned snapshots / 上报不可读对象与无效 pinned snapshot | S | Restores corruption observability promised by the contracts / 恢复契约承诺的腐坏可观测性 |
| C-09 | Update the storage contract for v2 range reads / 更新存储契约的 v2 范围读描述 | S | Doc currency / 文档时效 |

## P2 — A dedicated scalability generation (schema change) / 专门的可扩展性 generation（schema 变更）

**EN** — D-01, D-02, D-03 belong together in one protocol revision, introduced as a new run
generation exactly as the generation mechanism intends:

1. **D-02 chained prefix digest** — smallest change, unlocks the others.
2. **D-01 windowed consumption + lineage watermarks + retired-prefix accumulator.**
3. **D-03 state-based snapshots** and redefinition of the I-008 audit to state equivalence,
   keeping full-history replay as an offline audit while the physical prefix exists.

Gate it with: the existing reference model extended with the new digest/consumption rules; a
long-horizon synthetic benchmark (500–1000 transitions on the memory backend, asserting flat
per-transition manifest bytes and flat lifecycle time — the current test suite has no such
bounded-growth assertion); then the standard 1→2→8-node qualification. After this generation,
true log truncation behind two retained snapshot bases becomes possible (today it is
structurally impossible because snapshots embed history).

**中文** — D-01、D-02、D-03 应合并为一次协议修订，按 generation 机制的本意以新 run
generation 引入：先做 D-02 链式前缀 digest（改动最小、解锁其余），再做 D-01 窗口化消费 +
lineage 水位线 + 退役前缀累积值，最后做 D-03 基于状态的 snapshot 并把 I-008 审计重定义为
状态等价（物理前缀仍在时保留全历史 replay 作离线审计）。门控方式：扩展现有参考模型加入新
digest/消费规则；一个长视界合成基准（内存后端上 500–1000 次 transition，断言每次 transition
的 manifest 字节数与 lifecycle 时间不增长 —— 当前测试套件没有此类有界增长断言）；然后走标准
1→2→8 节点资格。此 generation 之后，"两个保留 snapshot 基点之后的日志真截断"才成为可能
（如今 snapshot 内嵌历史，结构上不可能）。

## P3 — Operational hardening / 运维强化

| Item | Fix | Effort |
|---|---|---|
| D-08 | Two-node clock-offset probe in the capability report, fail closed over budget / 能力报告加双节点时钟偏移探测，超预算失败关闭 | M |
| D-09 | Evidence-gated lease-parameter tuning (target ≈TTL 15 s) to cut the takeover floor ~30 s / 证据门控的 lease 调参（目标约 TTL 15 秒），削接管下限约 30 秒 | M |
| C-05 | Bucketed advisory locks for immutable creates / 不可变创建改用锁桶 | S–M |
| C-08 | Optional payload verify/repair on idempotent immutable puts / 幂等不可变写可选校验/修复 payload | S |
| C-11 | Grace-aged `.duraloco-tmp` cleanup in lifecycle inventory / lifecycle 盘点清理过期临时文件 | S |
| D-11 | Read-only authority export + verify-on-copy after each phase gate / 每阶段门后的只读权威导出与副本校验 | M |
| D-07 | Digest-verified learner adoption (hashes in `latest.json`, or adopt via `verified_get`) / learner 采用加 digest 校验 | S–M |
| D-10 | Member-rejoin request + qualification test (future phase) / 成员重入请求与资格测试（未来阶段） | L |

## Suggested sequencing / 建议顺序

**EN** — P0 items are risk-free and can land immediately with unit tests only. P1 items each
need the smallest targeted compute benchmark that proves the effect (the project's own
after-failure rule applied proactively), then ride the next scheduled D8 run — do not buy a
dedicated 8-node slot per item. P2 is a phase of its own with the reference model leading the
implementation, as M00→P04 did. P3 can interleave. D-07 is listed in P3 but is cheap and
guards research validity — pull it into P0/P1 if any multi-day training run is planned.

**中文** — P0 项无风险，仅需单元测试即可立即落地。P1 每项都应先用最小针对性计算基准证明效果
（把项目自身的失败后规则前置应用），然后搭下一次既定 D8 运行的车 —— 不要为单项单独申请
8 节点。P2 自成一个阶段，参考模型先行、实现随后（如 M00→P04 的做法）。P3 可穿插进行。D-07
虽列在 P3 但成本低且守护研究有效性 —— 若计划任何多天训练，应提前到 P0/P1。
