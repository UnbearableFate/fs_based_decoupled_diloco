# DuraLoCo Documentation & Project Review / DuraLoCo 文档与项目评审

**EN** — This documentation set was produced by a full review of the repository on 2026-07-13
(branch `codex/duraloco-p08r-replay-440s`). It has two halves:

1. `architecture/` — a self-contained description of the system: design goals, architecture,
   every module, the data flow, and the operational workflows.
2. `review/` — a critical review of both the system design and the code, listing every
   identified mistake, risk, or improvement opportunity, each with the most practical solution.

**中文** — 本文档集来自 2026-07-13 对整个仓库（分支 `codex/duraloco-p08r-replay-440s`）的完整
评审，分为两部分：

1. `architecture/` —— 系统的完整自述：设计目标、体系结构、各模块说明、数据流与运行工作流。
2. `review/` —— 对系统设计与代码的批判性评审：列出所有发现的错误、风险与改进点，并给出
   最可行的解决方案。

## Contents / 目录

### Architecture / 体系结构

| Doc | Content / 内容 |
|---|---|
| [01_system_overview.md](architecture/01_system_overview.md) | Goals, design principles, current status / 目标、设计原则、当前状态 |
| [02_architecture.md](architecture/02_architecture.md) | Roles, authority model, topology / 角色、权威模型、拓扑 |
| [03_modules.md](architecture/03_modules.md) | Every package and module explained / 全部包与模块说明 |
| [04_data_flow.md](architecture/04_data_flow.md) | Object model and end-to-end data flow / 对象模型与端到端数据流 |
| [05_workflows.md](architecture/05_workflows.md) | Startup, steady state, failover, lifecycle, stop / 启动、稳态、故障切换、生命周期、停止 |

### Review / 评审

| Doc | Content / 内容 |
|---|---|
| [review/README.md](review/README.md) | Scope, method, severity legend / 范围、方法、严重度说明 |
| [01_executive_summary.md](review/01_executive_summary.md) | Top findings at a glance / 主要发现速览 |
| [02_design_findings.md](review/02_design_findings.md) | System-design-level findings D-01…D-11 / 设计层发现 |
| [03_code_findings.md](review/03_code_findings.md) | Code-level findings C-01…C-13 / 代码层发现 |
| [04_performance_scalability.md](review/04_performance_scalability.md) | Performance & asymptotic scalability analysis / 性能与可扩展性分析 |
| [05_recommendations.md](review/05_recommendations.md) | Prioritized action roadmap / 按优先级排列的行动路线 |

## Reading order / 阅读顺序

**EN** — New to the project: read `architecture/` 01→05 in order. Maintainers who already know
the system: go straight to `review/01_executive_summary.md`, then the two findings documents.

**中文** — 初次接触项目：按顺序阅读 `architecture/` 01→05。已熟悉系统的维护者：直接阅读
`review/01_executive_summary.md`，再看两份发现清单。

## Validity rules / 有效性规则

**EN** — Statements in `architecture/` describe the code as it exists at review time; where the
code and the older design documents disagree, the review says so explicitly. Nothing in this set
overrides `plans/duraloco/STATE.yaml` or phase acceptance evidence.

**中文** — `architecture/` 中的陈述以评审时刻的代码为准；当代码与旧设计文档不一致时，评审文档
会明确指出。本文档集不覆盖 `plans/duraloco/STATE.yaml` 或阶段验收证据的效力。
