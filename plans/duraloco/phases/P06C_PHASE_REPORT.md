# P06C Milestone Report

## English

### Status and implementation

- Phase: P06C — redundant fragment ownership, hedged execution, and failover
- Branch: `codex/duraloco-p06c-redundant-fragment-executors`
- P06B basis: `98c1b92d943f9aef290b6b549db5baf06c225428`
- Qualified runtime implementation: `cba9f487dcc697a6df7930b22280e4f0d512377b`
- Maker acceptance: P06C-A01 through P06C-A24 pass
- Current status: `checking`

P06C freezes replication factor two in the fresh distributed RunSpec. Every redundant FWO binds an
ordered primary/backup member pair and one strict `warm_standby`, `active_active`, or `hedged` policy;
the D8 policy is hedged with a replayable 6000 ms delay. LFEs remain prepare-only. Equivalent duplicate
attempts converge on one content-derived PFR, while same-FWO divergence raises a fatal error containing
both result identities. The single final optimizer transition now binds the exact FWO and PFR IDs in its
commit identity and request digest. Failure observations remain non-authoritative until one fenced
Floating Committer commits a global-head membership transition.

### Qualification evidence

The clean repair commit passed the targeted lease-stage gate (`2363213.opbs`, seven tests), full unit
gate (`2363218.opbs`, 123 tests), real GPT-2 D1-R2 (`2363228.opbs`), synthetic D2-R2
(`2363235.opbs`), and D8-R2 (`2363242.opbs`) in order. D1 produced two exact active-active attempts for
one FWO/PFR and one final transition. D2 covered primary and backup executor loss, active committer loss,
three fencing epochs, and combined whole learner-host plus committer loss. It completed four optimizer
transitions; the longest measured recovery was 21.97 seconds.

D8-R2 used exactly eight learner nodes, eight learners, eight LFEs, two learner-hosted committer
candidates, and zero dedicated syncer nodes. It completed GPT-2/WikiText-2 50x10 in 528 seconds with ten
optimizer transitions, committed membership revision one after whole-node loss, authoritative stop, and
strict replay. Nineteen attempts belong to committed FWO lineage: nine are duplicate prepares. The
publish-to-commit distribution was p50 23.41 s, p95 23.68 s, p99 23.68 s, max 24.09 s; the maximum
failure-to-next-commit recovery was 106.95 s, dominated by lease expiry detection, takeover replay, and
membership publication.

The frozen P06B factor-one control completed in 470 seconds. Hedged R2 therefore produced a negative
throughput/cost result for this storage and delay regime: elapsed time increased 12.3%, logical executor
input bytes were 1.77x, and output bytes were 1.90x. Mean sampled GPU step time was 26.87 ms versus
27.52 ms (ratio 0.976), so this run did not show measurable GPU-step interference, but it also did not
establish a net performance win. Correctness and failover conclusions do not depend on a positive result.

### Failure history and repair

The detailed ledger contains every observed workflow, harness, analysis, and runtime failure. The most
important failure was D8 job `2363156.opbs`: takeover replay, membership publication, and prepare crossed
a 45-second lease without an in-stage renewal, then renewal failed closed. The committed prefix remained
safe. The full root-cause review preserves stage timestamps and explains the repair. Runtime now forces
and telemetry-tags renewal after activation replay, before membership transition, and before work
dispatch. The required targeted→1-node→2-node ladder passed on one clean commit before the single D8
retry. No same-shape retry was made earlier.

P07 must retain reachable winner PFRs and attempt lineage, preserve divergent/abandoned evidence through
an audit grace boundary, derive reachability from committed global-head ancestry, and delete marker last.
P06C performs no destructive cleanup.

### Independent Checker handoff

The Checker must validate all Maker manifests and checksums, run the full suite and 10,000 unique
reference traces, replay a private false-suspicion counterexample, and inject same-FWO divergent PFR
observations. Divergence must fail closed; evidence alone must not change ownership. A PASS with no
required-gate follow-up authorizes `checking → completed` and `next_action=P07`; it does not authorize
merging `main`.

## 中文

### 状态与实现

- 阶段：P06C — 冗余fragment ownership、hedged execution与failover
- 分支：`codex/duraloco-p06c-redundant-fragment-executors`
- P06B基线：`98c1b92d943f9aef290b6b549db5baf06c225428`
- 已资格验证runtime：`cba9f487dcc697a6df7930b22280e4f0d512377b`
- Maker验收：P06C-A01至P06C-A24全部通过
- 当前状态：`checking`

P06C在fresh distributed RunSpec中冻结replication factor 2。每个冗余FWO绑定有序的
primary/backup member以及严格的`warm_standby`、`active_active`或`hedged` policy；D8使用可重放
的6000 ms hedge delay。LFE仍只有prepare权限。等价duplicate attempt收敛到同一content-derived
PFR；同一FWO若产生不同result identity则fatal，并保留双方ID。最终optimizer transition的commit
identity与request digest现在精确绑定FWO/PFR。failure evidence本身没有authority，只有被fence的
Floating Committer能通过唯一global head提交membership transition。

### 资格证据

干净修复提交依次通过targeted lease-stage gate（`2363213.opbs`，7项）、完整unit gate
（`2363218.opbs`，123项）、真实GPT-2 D1-R2（`2363228.opbs`）、synthetic D2-R2
（`2363235.opbs`）与D8-R2（`2363242.opbs`）。D1对同一FWO/PFR产生两个exact active-active
attempt并只提交一个final transition。D2覆盖primary/backup executor loss、active committer loss、
三个fencing epoch以及whole learner host与committer联合故障，共完成四个optimizer transition，
最大恢复时间21.97秒。

D8-R2只使用八个learner node，运行八个learner、八个LFE与两个learner-hosted committer
candidate，专用syncer node为零。GPT-2/WikiText-2 50x10在528秒内完成十次optimizer
transition；whole-node loss后提交membership revision 1，并达到authoritative stop与strict replay。
committed FWO lineage包含19个attempt，其中9个是duplicate prepare。publish-to-commit为p50
23.41秒、p95 23.68秒、p99 23.68秒、max 24.09秒；failure到下一commit的最大恢复时间106.95秒，
主要来自lease expiry检测、takeover replay与membership publication。

冻结的P06B factor-one control耗时470秒。因此当前storage/delay regime下，hedged R2是负面的
throughput/cost结果：耗时增加12.3%，logical executor input为1.77倍，output为1.90倍。GPU step
平均26.87 ms，对照为27.52 ms（比例0.976），没有观察到明显GPU-step干扰，但也不能声称净性能
收益。正确性与failover结论不依赖性能结果为正。

### 错误历史与修复

详细ledger记录了全部workflow、harness、analysis与runtime错误。最关键的是D8作业
`2363156.opbs`：takeover replay、membership publication与prepare连续跨越45秒lease，随后续租
fail closed；committed prefix保持安全。root-cause review保存了完整阶段时间。修复后，runtime在
activation replay之后、membership transition之前以及work dispatch之前强制续租并记录stage。
同一干净提交依次通过targeted→1-node→2-node资格阶梯后，才执行唯一一次D8重试。

P07必须保留reachable winner PFR与attempt lineage，对divergent/abandoned evidence设置audit grace，
只从committed global-head ancestry派生reachability，并在删除时marker last。P06C不执行破坏性清理。

### 独立Checker交接

Checker必须校验全部Maker manifest与checksum，执行完整suite和10,000条唯一reference trace，
构造私有false-suspicion反例并注入same-FWO divergent PFR。divergence必须fail closed；evidence本身
不得改变ownership。没有required-gate follow-up的PASS才授权`checking → completed`及
`next_action=P07`，且不授权合并`main`。
