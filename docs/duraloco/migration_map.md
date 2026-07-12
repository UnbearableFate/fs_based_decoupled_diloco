# 从早期 Prototype 到当前 DuraLoCo 的迁移状态

本表描述截至 H0 的实际状态，不把后续 phase 写成已经完成。P00–P04 报告是历史证据；当前 active
generation 不读取或转换已删除的旧持久化格式。

| 能力/事实 | 当前 authority 或实现 | 状态 | 下一 owner |
|---|---|---|---|
| Proposal publication | content-addressed payload + Protocol v2 manifest/marker | P06/P07 active | P08 优化 direct I/O/validation reuse |
| Candidate catalog/selection | process-local typed view；冲突/takeover 后重建 | 正确性已验证，扫描/内存待优化 | P08 |
| Global params + outer state | paired immutable ObjectRefs，通过 head CAS 可见 | P04–H0 active | 保持 identity |
| Proposal consumption/lineage | committed prefix fold，无第二持久 materialization | active | P08 优化复杂度 |
| Distributed execution | learner-hosted LFE，factor 1/2，FWO→PFR | P06c/P07/H0 active | P08 性能 |
| Committer HA | learner host 上 floating fenced candidates | P05–H0 active | P08 error-resume policy；P11 hardening |
| Dedicated syncer | D8-R2 为 0；central syncer 仅 legacy/reference | 已迁移 | P11 决定清理范围 |
| `latest`/stop/heartbeat/telemetry | derived/observational；stop/error 先 committed | active | P08 telemetry |
| Snapshot+suffix | committed pin，strict-equivalent，保留两个 base | P07 active | P08/P11 性能与长期运行 |
| Exact learner capsule | 完整私有 state、marker-last、synthetic exact restore | P07 active | 后续端到端 reintegration 研究 |
| Reachability/GC | explainable roots；real dry-run；synthetic apply | P07 active，real destructive 未授权 | P11/单独运维决策 |
| Storage | POSIX envelopes、single CAS、capability + cross-node lock probe | P03–H0 active | P08 true range I/O；P11 durability |
| Embedded database authority | active source/config/CLI/scripts/tests 中禁止 | 已删除并有静态门禁 | 持续回归 |
| Streaming reducer | 当前仍有 full materialization/copy | 未完成 | P08 |
| Model quality/scalability study | protocol evidence不等于质量结论 | 未完成 | P10/P11 |

历史 checkpoint 只能在显式新 generation 中 warm start。不得导入旧 proposal history、consumption、
session sequence 或 exact-continuation claim；兼容转换也不能重新引入第二 authority。
