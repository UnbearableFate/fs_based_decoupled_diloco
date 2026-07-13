# Project Review / 项目评审

**EN** — Review date 2026-07-13, branch `codex/duraloco-p08r-replay-440s`, working tree at the
post-P08 state (P08R in progress). Scope: system design *and* implementation. Method: full read
of the storage, protocol, log, coordination, distributed-syncer, and learner layers; design
documents and the P08R evidence (`plans/duraloco/phases/P08R_R2_527S_ANALYSIS.md`) were
cross-checked against the code.

**中文** — 评审日期 2026-07-13，分支 `codex/duraloco-p08r-replay-440s`，工作树处于 P08 之后
（P08R 进行中）。范围：系统设计与实现两方面。方法：完整阅读存储、协议、日志、协调、分布式
syncer 与 learner 各层代码；并将设计文档与 P08R 证据
（`plans/duraloco/phases/P08R_R2_527S_ANALYSIS.md`）与代码交叉核对。

## Documents / 文档

| Doc | Content / 内容 |
|---|---|
| [01_executive_summary.md](01_executive_summary.md) | All findings ranked, one line each / 全部发现的排序速览 |
| [02_design_findings.md](02_design_findings.md) | D-01…D-11: design-level issues + solutions / 设计层问题与方案 |
| [03_code_findings.md](03_code_findings.md) | C-01…C-13: code-level issues + solutions / 代码层问题与方案 |
| [04_performance_scalability.md](04_performance_scalability.md) | Asymptotic and measured performance analysis / 渐近与实测性能分析 |
| [05_recommendations.md](05_recommendations.md) | Prioritized roadmap / 优先级路线图 |

## Severity legend / 严重度说明

**EN**

| Level | Meaning |
|---|---|
| **HIGH** | Will cause incorrect behavior, resource exhaustion, or blocked progress under realistic conditions (long runs, larger models, common faults). Fix before scaling up. |
| **MEDIUM** | Degrades performance, observability, or robustness; or contradicts a documented contract; safe today only because runs are small/short. |
| **LOW** | Hygiene, currency, or minor waste; fix opportunistically. |

**中文** — **HIGH**：在现实条件（长运行、更大模型、常见故障）下会导致错误行为、资源耗尽或
进度阻塞，扩大规模前必须修复。**MEDIUM**：损害性能、可观测性或健壮性，或与既有契约文档相悖；
目前安全只是因为运行规模小、时间短。**LOW**：卫生、时效性或轻微浪费问题，可顺手修复。

## Overall verdict / 总体结论

**EN** — This is an unusually disciplined codebase. The correctness core — canonical identity,
envelope storage, single head CAS, fencing, strict replay, fail-closed validation — is coherent,
well-tested, and matches its own design documents almost everywhere. No finding in this review
breaks the safety invariants I-001…I-012 for the validated 10-transition qualification shape.
The dominant theme of the findings is instead **asymptotic scalability**: several core data
structures and audit mechanisms grow with run length (frontier consumption sets, prefix digests,
history-embedding snapshots, unbounded operation history), so costs that are invisible at 10
transitions grow quadratically or worse over hundreds. The secondary themes are robustness
details (RSS budget check, silent corrupt-object skipping) and unverified derived-data trust in
the learner adoption path.

**中文** — 这是一个纪律性极强的代码库。正确性核心 —— canonical identity、envelope 存储、唯一
head CAS、fencing、strict replay、失败即关闭的验证 —— 逻辑自洽、测试充分，几乎处处与自身设计
文档一致。本评审没有任何发现会破坏已验证的 10-transition 资格实验形态下的安全不变量
I-001…I-012。发现的主导主题是**渐近可扩展性**：若干核心数据结构与审计机制随运行长度增长
（frontier 消费集、前缀 digest、内嵌全历史的 snapshot、无界操作历史），在 10 次 transition
下看不见的成本，到几百次时会以平方或更高阶增长。次要主题是健壮性细节（RSS 预算检查、静默
跳过损坏对象）与 learner 采用路径对派生数据的未校验信任。
