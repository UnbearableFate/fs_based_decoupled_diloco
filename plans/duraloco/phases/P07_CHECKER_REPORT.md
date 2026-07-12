# P07 Independent Checker Report

verdict: PASS
required_gate_followups: none

## English

### Scope and result

The independent P07 Checker ran as PBS `2369002.opbs` against persistence and
Checker commit `c099adc3c3a99127569a7d9bf38a58547022173c`. It audited all 24
acceptance IDs, the successful one-node and D2-R2 qualification evidence, the
completed ten-transition D8-R2 authority, the recovered runtime/lifecycle
reports, and their checksums. The machine-readable verdict is preserved at
`artifacts/duraloco/P07/20260712_p07_checker_c099adc/checker_report.json`.

The Checker confirmed ten optimizer transitions, eight retained exact-capsule
markers, 245 explainable collection candidates, and an effective-live tail of
`220 → 248 → 276`. The final-three-sample delta is 56, below the preregistered
maximum of 64. It also confirmed the two injected runtime recoveries: executor
process loss recovered in 81.816 seconds and whole learner-host loss recovered
in 91.602 seconds.

### Independent counterexamples

The Checker exercised four counterexamples beyond the terminal Maker path:

1. a payload published before its marker becomes protected when it turns live
   before GC apply revalidation;
2. an equivalent same-digest loser receives bounded grace while divergent
   same-FWO evidence remains a non-collectable blocker root;
3. after GC and ownership takeover, corruption of the newest retained snapshot
   falls back to the older independently validated snapshot and then strict
   suffix replay;
4. a lifecycle substage longer than the lease TTL remains fenced because the
   owner control thread renews the lease, while renewal/ownership failure still
   fails closed.

All four passed. The Checker found no second authority, no live deletion, no
SQLite or replacement embedded database, and no required follow-up. P07 may
transition from checking to completed and hand its frozen lifecycle interfaces
to P08. This verdict does not authorize merging `main`.

## 中文

### 范围与结论

P07 独立 Checker 以 PBS `2369002.opbs` 运行，复核 persistence/Checker commit
`c099adc3c3a99127569a7d9bf38a58547022173c`。它审计了全部 24 项验收、通过的
单节点与 D2-R2 qualification、完成十次 optimizer transition 的 D8-R2 权威状态、恢复后的
runtime/lifecycle 报告及其 checksum。机器可读结论保存在
`artifacts/duraloco/P07/20260712_p07_checker_c099adc/checker_report.json`。

Checker 确认十次 optimizer transition、八个保留的 exact-capsule marker、245 个可解释
回收候选，以及 `220 → 248 → 276` 的 effective-live tail；最后三个 sample 的增量为 56，
小于预注册上限 64。它还确认两次 runtime 故障恢复：executor process 丢失在 81.816 秒内
恢复，完整 learner host 丢失在 91.602 秒内恢复。

### 独立反例

Checker 在 terminal Maker 路径之外执行了四个反例：

1. payload 先于 marker 发布，并在 GC apply 重验前变为 live 时，必须被重新保护；
2. same-digest loser 使用有界 grace，而同一 FWO 的 divergent evidence 必须成为不可自动
   回收的 blocker root；
3. GC 与 ownership takeover 之后，最新保留 snapshot 损坏时，系统回退到另一个独立验证的
   snapshot，再执行 strict suffix replay；
4. lifecycle substage 超过 lease TTL 时，由 owner control thread 持续续租保持 fencing；
   续租或 ownership 失败仍然 fail closed。

四个反例全部通过。Checker 未发现第二 authority、live deletion、SQLite 或替代 embedded
database，也没有 required follow-up。P07 可以从 checking 转为 completed，并把冻结的
lifecycle interface 交给 P08。该结论不授权合并 `main`。
