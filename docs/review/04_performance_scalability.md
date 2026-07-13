# Performance & Scalability Analysis / 性能与可扩展性分析

**EN** — This document connects the measured P08R numbers to the structural cost model of the
implementation, and projects where costs go as runs get longer and models get bigger. Measured
inputs: factor-one full experiment 337.6 s vs R2 527.0 s (10 transitions, GPT-2/WikiText-2,
8 nodes); normal transition ≈18.3 s; hedged ≈23–24 s; lifecycle cycles 0.7→23.1 s within one
run; H0 lifecycle 34.3→68.4 s over five cycles; worst-case takeover-to-commit 89.44 s.

**中文** — 本文把 P08R 的实测数字与实现的结构性成本模型联系起来，并外推运行更长、模型更大时
成本的走向。实测输入：factor-one 完整实验 337.6 秒 vs R2 527.0 秒（10 次 transition、
GPT-2/WikiText-2、8 节点）；普通 transition 约 18.3 秒；hedged 约 23–24 秒；单次运行内
lifecycle 周期 0.7→23.1 秒；H0 五次 lifecycle 34.3→68.4 秒；最坏接管到提交 89.44 秒。

## 1. Where a normal 18.3 s transition goes / 一次 18.3 秒 transition 的去向

**EN** — Approximate critical path (factor one, from stage telemetry):

| Stage | Cost driver | Scales with |
|---|---|---|
| Catalog discovery + validation (~4.7 s agg/run ÷10) | listing + payload validation of new proposals | proposals/interval, payload size |
| FWO/input-bundle publication | small manifests | constant |
| Prepared visibility (~7.9 s) | LFE compute (streaming reduce + outer step) **plus** C-07 polling redundancy | fragment numel |
| Winner validation | full read + decode of params/outer | model size |
| Successor publication (~3.1 s) | **second** full write of params/outer (D-05) + commit/frontier | model size + D-01 frontier size |
| Head CAS + post-CAS replay | CAS is cheap; replay cost per D-02/D-01 | history length |
| Materialization | fragment files + full model write (C-13) | model size |
| Fixed sleep | `time.sleep(0.5)` | constant |

Three of the eight rows move model-sized payloads that a zero-copy design would not move
(D-05, C-13), and two grow with history (D-01/D-02). This is why "control-path, filesystem-I/O"
dominates the elapsed accounting rather than GPU work (GPU step ≈26 ms).

**中文** — 关键路径近似（factor one，取自阶段遥测）见上表。八行中有三行在搬运模型体量的
payload，而零拷贝设计本可不搬（D-05、C-13）；另有两行随历史增长（D-01/D-02）。这就是为什么
耗时记账中占主导的是"控制路径与文件系统 I/O"而非 GPU 工作（GPU 单步约 26 毫秒）。

## 2. Asymptotic model / 渐近模型

**EN** — Let n = committed transitions, k = selections per transition, P = fragment payload
bytes, L = learners.

| Mechanism | Today | After D-01+D-02+D-03 |
|---|---|---|
| Frontier object size | O(n·k) | O(L + staleness window) |
| Log bytes cumulative | O(n²·k) | O(n·(P + L)) |
| Strict replay manifest work | O(n²)–O(n³) hashing | O(n) chained-digest verify |
| Snapshot size | O(n²·k + P) | O(P + L) |
| Lifecycle cycle time | grows every cycle (measured) | ~flat |
| Empty-cache takeover replay | O(history payloads) → snapshot+suffix already bounds tensor rereads; manifest work still O(n²) | O(suffix) end to end |

The measured growth curves (lifecycle 0.7→23.1 s within ten transitions; H0 34→68 s across
five cycles) are the small-n prefix of these asymptotes. Nothing here is a correctness bug —
it is the audit machinery pricing itself out of long runs.

**中文** — 设 n=已提交 transition 数、k=每次选择数、P=fragment payload 字节、L=learner 数。
上表对比现状与 D-01+D-02+D-03 改造后的量级。实测增长曲线（单次运行内 lifecycle 0.7→23.1
秒；H0 五周期 34→68 秒）正是这些渐近线的小 n 前缀。这些都不是正确性缺陷 —— 而是审计机制把
自己在长运行中定价出局。

## 3. The recovery budget / 恢复预算

**EN** — The 89.44 s worst case decomposes as ≈37–47 s lease-expiry wait (policy; see D-09) +
empty-cache strict replay + reselection + next transition. The replay part is already bounded
by snapshot+suffix for tensor bytes (the `ac2d961` repair proved 0 tensor bytes / 0.26 s on the
second suffix replay); the manifest-side O(n²) (D-02) is what will erode this bound as n grows.
Lowering TTL per D-09 (evidence-gated) is the only lever on the first term; D-02/D-03 are the
levers on the second.

**中文** — 89.44 秒最坏情况分解为约 37–47 秒 lease 过期等待（策略问题，见 D-09）+ 空缓存
strict replay + 重新选择 + 下一次 transition。replay 的张量字节部分已被 snapshot+suffix
限定（`ac2d961` 修复实证第二次 suffix replay 读 0 张量字节 / 0.26 秒）；随 n 增长侵蚀该界的
是 manifest 侧的 O(n²)（D-02）。第一项唯一的杠杆是按 D-09 证据化降低 TTL；第二项的杠杆是
D-02/D-03。

## 4. R2 (factor two) overhead structure / R2（因子二）开销结构

**EN** — Of the 189.5 s R2 excess: ~90 s was five lifecycle cycles (now partially repaired by
the suffix-cache fix; structurally addressed by D-03), ~47 s extra prepared-visibility wait
(structural: D-06 — hedging requires both attempts; plus C-07 polling), ~15 s extra post-run
reporting (inherent to the qualification shape). The reliability *evidence* value of R2 is
real; the review's point is that most of its latency cost is policy (D-06) and audit growth
(D-03), not intrinsic to duplicate execution — active_active on idle CPU cores overlaps
compute almost fully.

**中文** — R2 多出的 189.5 秒中：约 90 秒是五个 lifecycle 周期（suffix 缓存修复已部分缓解，
结构性解法是 D-03）；约 47 秒是 prepared-visibility 额外等待（结构性原因 D-06 —— 对冲要求
双份结果，叠加 C-07 轮询）；约 15 秒是运行后报告（资格实验形态固有）。R2 的可靠性*证据*价值
是真实的；本评审要说明的是其延迟成本大部分来自策略（D-06）与审计增长（D-03），并非重复执行
本身 —— 空闲 CPU 核上的 active_active 几乎可完全重叠计算。

## 5. Scaling to bigger models / 放大到更大模型

**EN** — With GPT-2 (~0.5 GB fp32 flat), payload movement is already ~half the transition.
Every payload-touching term scales linearly in model size: proposal payloads (bf16), LFE reads,
PFR writes, committer winner validation, authority re-publication (D-05), materialization
(C-13), and replay finite-scans. For a 7B model (~28 GB fp32) the current per-transition
payload traffic would be hundreds of GB — infeasible. Priority order for model scaling:
D-05 (eliminate double publication) → C-13/D-04b (materialize off critical path, by cadence) →
fragment-count increase (smaller fragments; the fragment machinery is already built for this) →
verified range reads (already available in v2 envelopes, C-09) for partial validation, plus
GPU-assisted finite checks (`set_replay_validation_device` already exists).

**中文** — GPT-2（fp32 平铺约 0.5GB）下 payload 搬运已占 transition 约一半。所有触碰
payload 的项都随模型线性增长：proposal payload（bf16）、LFE 读取、PFR 写入、committer 胜者
验证、权威重发布（D-05）、物化（C-13）、replay 有限值扫描。7B 模型（fp32 约 28GB）下现行
每次 transition 的 payload 流量将达数百 GB —— 不可行。面向模型放大的优先序：D-05（消除双重
发布）→ C-13/D-04b（物化按节奏移出关键路径）→ 增加 fragment 数（更小的 fragment；机制已
就绪）→ 用 v2 envelope 的可校验范围读（C-09）做局部验证，并用 GPU 加速有限值检查
（`set_replay_validation_device` 已存在）。

## 6. What is already good / 已经做得好的部分

**EN** — Credit where due: header-only listing/inventory (payload bytes read = 0 across all D8
inventories); content-addressed payload dedup between learner and catalog; per-scope validation
tokens avoiding revalidation; streaming bounded-prefetch reduction in the LFE; snapshot+suffix
replay with the repaired cache union; verified chunked range reads in v2 envelopes; and the
stage telemetry that made this analysis possible at all. These are the right foundations — the
findings above are about extending the same discipline to the remaining growth terms.

**中文** — 应有的肯定：仅读 header 的列举/盘点（全部 D8 盘点 payload 读取为 0 字节）；
learner 与 catalog 之间内容寻址的 payload 去重；按 scope 的验证 token 避免重复验证；LFE 的
有界预取流式归约；修复缓存并集后的 snapshot+suffix replay；v2 envelope 的可校验分块范围读；
以及让本分析成为可能的阶段遥测本身。这些是正确的地基 —— 上述发现只是要求把同样的纪律延伸到
剩余的增长项上。
