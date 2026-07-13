---
plan_id: "P12"
title: "Formal Experiments、Artifact、Related Work 与 Paper Evidence"
status: "planned"
date: "2026-07-11"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/duraloco-p11-distributed-acceptance"
planning_basis_commit: "resolve_from_P11_verified_report"
target_branch: "codex/duraloco-p12-distributed-evaluation"
depends_on:
  - "P11"
required_skill: "miyabi-development"
execution_mode: "preregistered experiments + independent analysis/checker"
automatic_progression: false
next_phase: "project_complete_or_optional_P09_by_explicit_user_choice"
agent_decision_gates:
  - "在预注册资源范围内可自主执行；claim必须随证据收缩，negative/neutral结果同样完成阶段。"
human_approval_gates:
  - "超出既定Miyabi资源、公共云、公开发布或新增长期大规模训练"
---

# P12 — Formal Experiments、Artifact、Related Work 与 Paper Evidence

> **D-0821 forward amendment:** all current P12 cells use exactly eight learner
> nodes. Do not submit C9/C9-HA or allocate a dedicated/idle ninth host. Older
> C9 text below is historical planning provenance and is non-executable.

## 1. 阶段使命

冻结实验registry并完成DuraLoCo distributed-syncer路线的correctness、resource efficiency、failure-free性能、fault goodput、lifecycle、controller、redundancy和model-quality评估；将所有图表、claim、相关工作差异和artifact reproduction绑定到immutable run manifests。P12可得Supported、Bounded/conditional或Rejected/negative结论，不能通过删除失败数据制造成功。

### 1.1 核心比较配置

| 代号 | 配置 |
|---|---|
| C9 | 8 learners + 1 dedicated CRS |
| C9-HA | 8 learners + dedicated active/standby syncer（P05 fault baseline） |
| D8 | 8 learner nodes，factor1，无专用syncer |
| D8-R2-W | D8 factor2 warm standby |
| D8-R2-H | D8 factor2 hedged |
| D8-SACC-SYS | D8/D8-R2 guarded system-only enforced controller |
| D8-SACC-ALG | 仅P10 algorithm tier qualified时的新generation算法影响controller |
| checkpoint baseline | 可用时的传统checkpoint+restart或现有project baseline |

所有比较必须明确node/GPU allocation差异，不能只比较wall-clock而忽略C9多一个GPU节点。

### 1.2 研究主张候选

- storage-resident outer optimizer authority可替代persistent syncer state；
- D8消除专用syncer allocation并保持correctness/model quality；
- R2/hedging在故障或tail latency下改善fault goodput，成本可量化；
- ownership迁移无需optimizer-state transfer；
- lifecycle保持bounded storage和safe recovery；
- SACC在某些条件下改善goodput/cost，或给出其无收益边界。

## 2. 前置条件

- [ ] P11-A01–A26通过；
- [ ] final implementation/config/semantic digests冻结；
- [ ] `RESEARCH_RELATED_WORK_AND_DIFFERENTIATION.md`更新到执行日；
- [ ] analysis environment pinned；
- [ ] experiment registry、exclusion和failure classification由Checker预审。

## 3. 范围

### 3.1 必须完成

- [ ] experiment registry与preregistration；
- [ ] correctness/fault campaign；
- [ ] C9/C9-HA/D8/D8-R2 failure-free性能和resource allocation；
- [ ] redundancy modes与break-even；
- [ ] fault goodput、RTO/RPO、lost/repeated work；
- [ ] CPU/GPU/Lustre/interference与stage attribution；
- [ ] lifecycle/storage growth/recovery；
- [ ] SACC fixed/shadow/system-enforced ablation；algorithm-enforced仅在P10 qualified时进入required cells；
- [ ] matched-token/matched-compute model quality和multi-seed计划；
- [ ] claim–evidence matrix；
- [ ] related-work differentiation update；
- [ ] clean artifact reproduction；
- [ ] internal independent review。

### 3.2 明确不做

- 不把engineering smoke run混入science sample；
- 不排除不利run而不保留manifest和预注册理由；
- 不用计划值替代实测值；
- 不在缺multi-seed evidence时宣称quality equivalence；
- 不宣称individual primitives首创；
- 不自动启动可选P09或公共云实验。

## 4. 预期仓库变更

```text
experiments/duraloco/
  registry.yaml
  cells/
  fault_tapes/
  quality/
  lifecycle/
  sacc/
analysis/
  load_manifests.py
  correctness.py
  resource_efficiency.py
  latency_breakdown.py
  fault_goodput.py
  lifecycle.py
  model_quality.py
  figures.py
  claim_evidence.py
artifacts/release/
  README.md
  MANIFEST.json
  CLAIM_EVIDENCE.md
  RELATED_WORK.md
  REPRODUCE.md
paper/
  system_claims.md
  evaluation_results.md
```

## 5. 先冻结的设计决策

- [ ] D-1201：primary/secondary endpoints与success criteria；
- [ ] D-1202：matched-token、matched-compute、matched-allocation三种比较口径；
- [ ] D-1203：seeds/repetitions和置信区间；
- [ ] D-1204：fault distributions/tapes和control groups；
- [ ] D-1205：C9多一个节点的resource accounting；
- [ ] D-1206：quality non-inferiority或bounded-difference标准；
- [ ] D-1207：run exclusion/inconclusive规则；
- [ ] D-1208：formal science vs engineering lineage隔离；
- [ ] D-1209：artifact licenses/secrets/redaction；
- [ ] D-1210：claim wording与related-work priority check。

## 6. Codex执行循环

### Loop 1 — Registry与pre-registration

**目标。** 在正式runs前冻结cells、configs、seeds、faults、metrics、exclusions和analysis commit。

**RED。** registry缺topology/resource/implementation digest或能在结果后改success criteria时失败。

**GREEN。** immutable registry checksum；每cell生成run manifest template；Checker签署pre-registration。

**HARDEN。** queued/cancelled/retry lineage、environment drift、partial cell和budget limits。

**停止条件。** analysis可在无结果情况下运行schema validation。

### Loop 2 — Correctness与resilience campaign

**目标。** 系统化验证duplicate execution、fencing、reconfiguration、replay、GC和capsule。

**配置。** D8、D8-R2-W/H、C9-HA；固定fault tapes与no-fault controls。

**指标。** double inclusion、mixed state、live deletion、divergence blocker、committed progress、RTO/RPO、lost/repeated tokens、availability/fault goodput。

**HARDEN。** failure at all commit stages、whole-node/co-failure、false suspicion、storage ambiguity、corruption、controller restart。

**停止条件。** 所有违反safety的事件解释并修复重验；未修复则核心claim rejected。

### Loop 3 — Failure-free performance与resource efficiency

**目标。** 比较C9、D8、R2和SACC的wall time、goodput、node/GPU-hours、GPU interference和storage cost。

**方法。** matched workload/commit/config；报告8 vs9节点资源；stage decomposition而非单aggregate interval。

**指标。** useful tokens/s、outer transitions/s、GPU step time、CPU/RSS、Lustre bytes/metadata ops、publish→adopt、duplicate waste、allocation efficiency。

**停止条件。** raw manifests可重建每张图，break-even条件明确。

### Loop 4 — Redundancy、fault goodput与state-transfer claim

**目标。** 确定warm/active-active/hedged在不同failure/straggler rates下的收益边界。

**方法。** replay/simulated sweeps加selected real D8 fault tapes；记录owner change时读取shared objects而非private state transfer。

**指标。** tail latency、hedge rate、wasted CPU/I/O、recovery time、fault goodput、availability、state bytes migrated（应为0 private optimizer state）。

**停止条件。** 给出适用区间或negative result，不泛化。

### Loop 5 — Lifecycle与checkpoint fusion

**目标。** 量化proposal/transition/capsule/snapshot复用、storage growth、GC和recovery成本。

**方法。** no-GC、dry-run/apply synthetic/approved、snapshot cadence、warm/exact recovery comparisons。

**指标。** bytes/object count/ops、peak/steady storage、snapshot/replay time、capsule overhead、restore success。

**停止条件。** bounded-growth和safe restore有证据，或收缩claim。

### Loop 6 — SACC ablation

**目标。** fixed、shadow、enforced的系统和算法影响。

**方法。** matched D8/D8-R2 fixed/shadow/system-enforced cells；action traces；counterfactual
replay；quality smoke。只有P10已通过new-generation committed-policy与quality gate时才加入
algorithm-enforced cells；否则分析其`not_qualified` evidence，不能把它列为missing run。

**指标。** goodput/cost、tail latency、fairness、quorum diversity、hedge/bundle duty、oscillation、quality。

**停止条件。** 只有受支持actions进入paper claim；无收益结论可接受。

### Loop 7 — Model quality

**目标。** 判断distributed topology、redundancy和controller是否保持训练质量。

**方法。** matched tokens和matched compute；预注册seeds；central CRS、D8、D8-R2、SACC；报告训练曲线和下游metrics。

**HARDEN。** seed variance、failed run handling、warm/exact restart、different actual tokens。

**停止条件。** 达到预注册证据；资源不足则明确“不支持quality equivalence claim”。

### Loop 8 — Artifact、related work与paper evidence

**目标。** 从clean bundle重建核心结果和每项claim。

**GREEN。** pin environment；打包registry/manifests/raw data/analysis/checksums；生成claim–evidence matrix和related-work comparison；移除secrets但保留provenance。

**CHECK。** 独立Checker从clean directory运行reproduction；内部审稿逐claim检查措辞、反例和priority。

**停止条件。** 无悬空primary claim；negative结果和engineering lineage均保留。

## 7. 不变量

- [ ] 结果不能修改预注册criteria；
- [ ] 所有失败/取消/排除/retry保留；
- [ ] C9/D8资源口径明确；
- [ ] correctness和quality claims分开；
- [ ] raw manifests是分析输入，不依赖DB；
- [ ] 图表可由final clean analysis commit重建；
- [ ] related work不夸大individual primitive novelty；
- [ ] P09未显式选择不影响P12完成。

## 8. 验收标准

- [ ] P12-A01：registry/pre-registration checksum和Checker PASS；
- [ ] P12-A02：C9/C9-HA/D8/D8-R2/SACC required cells完整或按预注册标记inconclusive；
- [ ] P12-A03：correctness campaign无未解释double inclusion/split/mixed state/live deletion；
- [ ] P12-A04：divergent duplicate expected-BLOCKED行为有formal evidence；
- [ ] P12-A05：failure-free overhead与node/GPU resource efficiency有真实数据；
- [ ] P12-A06：C9多一个节点在所有比较中明确计入；
- [ ] P12-A07：CPU/GPU/Lustre/interference与critical stages完整；
- [ ] P12-A08：redundancy break-even和negative regions完整；
- [ ] P12-A09：fault goodput/RTO/RPO/lost/repeated work完整；
- [ ] P12-A10：ownership migration无private optimizer-state transfer有trace证据；
- [ ] P12-A11：lifecycle bytes/ops/object count/steady growth/recovery完整；
- [ ] P12-A12：SACC fixed/shadow/system-enforced ablation完整；algorithm-enforced在P10 qualified时完整，否则`not_qualified`证据进入claim matrix；
- [ ] P12-A13：matched-token/matched-compute multi-seed quality完整，或claim明确不支持；
- [ ] P12-A14：所有failed/cancelled/excluded/retry runs保留lineage；
- [ ] P12-A15：formal science cells与M00/P05/P06 engineering runs分开；
- [ ] P12-A16：所有图表从raw manifests重建；
- [ ] P12-A17：claim–evidence matrix无悬空primary claim；
- [ ] P12-A18：related-work文档更新至执行日并避免不实first claims；
- [ ] P12-A19：clean artifact reproduction不需要SQLite/DB dump；
- [ ] P12-A20：reproduction重放至少一个stale-cache/head-jump、duplicate和retry-lock反例；
- [ ] P12-A21：final D8/D8-R2 milestone runs纳入artifact；
- [ ] P12-A22：paper措辞区分dedicated-syncer-free与coordinator-free；
- [ ] P12-A23：独立Checker/内部review完成；
- [ ] P12-A24：final report可为Supported、Bounded或Rejected，且证据完整；
- [ ] P12-A25：`STATE.yaml`标记required route completed；
- [ ] P12-A26：P09保持optional，只有用户显式选择才启动。

## 9. 完成语义

P12是必需路线终点。结论为negative或bounded不等于工程失败，只要预注册实验、证据、artifact和诚实claim全部完成。不得自动merge main或公开发布。

## 10. 可复制给Codex的启动指令

```text
执行P12R formal evaluation。先冻结registry/pre-registration，再完成C9/C9-HA/D8/D8-R2/SACC correctness、resource、fault、lifecycle和quality cells。所有fail/cancel/exclusion/retry保留；图表必须从raw manifests重建。更新related-work差异和claim-evidence，独立clean reproduction。允许Supported/Bounded/Rejected结论。P09不自动启动。
```
