---
plan_id: "P10"
title: "Distributed SACC：Storage-Aware Coordination、Redundancy 与 Algorithm–System Co-Design"
status: "planned"
date: "2026-07-11"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/duraloco-p08-distributed-performance"
planning_basis_commit: "resolve_from_P08_verified_report"
target_branch: "codex/duraloco-p10-distributed-sacc"
depends_on:
  - "P08"
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
next_phase: "P11"
agent_decision_gates:
  - "只有通过shadow replay、guardrails、ablation和Checker的actions才可进入enforced mode。"
human_approval_gates: []
---

# P10 — Distributed SACC：Storage-Aware Coordination、Redundancy 与 Algorithm–System Co-Design

## 1. 阶段使命

实现分散式Storage-Aware Coordination Controller（SACC），先利用结构化stage metrics调节
不改变optimizer trajectory的system-only knobs（prefetch、materialization cadence、已冻结
mode内的hedge启动、LFE CPU/I/O budgets），建立deterministic shadow mode后再有限enforced。

Quorum/grace、fair selection、local interval、replication factor、bundle shape等会改变proposal
集合、numeric order、ownership或committed trajectory，不能由observational telemetry直接
在当前generation本地启用。它们属于algorithm-affecting tier：必须先有committed policy
decision schema、new run generation/identity、quality guardrail和独立Checker；证据不足时以
`not_qualified`结束该tier，P10仍可得到bounded/negative结论，不得为了完成gate强行enforce。

### 1.1 研究主张

DuraLoCo可以把storage contention、learner progress、fragment tail latency和redundancy成本统一为可观测控制问题，在不削弱authority/fencing/validation和模型质量边界的情况下提高goodput或降低资源成本。

### 1.2 完成后的系统增量

- controller observation/action schemas；
- simulator/runtime/replay共享policy kernel；
- shadow deterministic replay；
- guarded system-only backpressure/hedge/resource actions；
- optional evidence-qualified algorithm-affecting actions in a new generation；
- fixed/shadow/enforced D8/D8-R2 ablations；
- controller decisions纳入transition/work-order lineage。

## 2. 前置条件

- [ ] P08 verified commit及其P07 lifecycle regression Checker PASS；
- [ ] lifecycle与performance schemas冻结；
- [ ] D8/D8-R2 raw stage metrics完整；
- [ ] bundle path若启用已通过serial-equivalence；
- [ ] controller关闭时行为与P08 fixed baseline一致。

## 3. 范围

### 3.1 必须完成

- [ ] observation schema与quality checks；
- [ ] deterministic policy kernel/replay；
- [ ] fixed、shadow、enforced modes；
- [ ] adaptive quorum/grace/fairness的shadow analysis；只有new-generation gate通过后才可enforce；
- [ ] in-flight/bundle/prefetch/materialization backpressure；
- [ ] hedge delay和replication activation controls；
- [ ] LFE CPU thread/RSS/I/O budget controls；
- [ ] local interval/token-aware observation接口；enforcement默认out-of-scope，除非algorithm-affecting gate通过；
- [ ] min/max/hysteresis/cooldown/safe fallback；
- [ ] system-only action在激活前绑定head/membership revision和policy digest；algorithm-affecting action必须先committed并进入新generation的FWO/final transition identity；
- [ ] fault/head/epoch change invalidation；
- [ ] D8/D8-R2 fixed/shadow/enforced ablation。

本阶段的最低可完成结果是：deterministic shadow + system-only guarded enforcement +
algorithm tier `not_qualified`的完整证据。不得把“algorithm action未启用”误写成缺失gate，
也不得把observational JSONL/CSV升级为authority。

### 3.2 明确不做

- 不自修改协议schema或创建per-fragment heads；
- 不允许controller关闭strict replay、validation、fencing、marker-last或GC roots；
- 不用单一aggregate latency猜root cause；
- 不让local wall-clock-only decision在restart后不可重放；
- 不在无quality evidence时扩大算法动作范围；
- 不把shadow observation写成authority。

## 4. 预期仓库变更

```text
fs_diloco/sacc/
  observations.py
  actions.py
  policy.py
  replay.py
  guardrails.py
  fairness.py
  cost_model.py
  controller.py
  committed_decisions.py
fs_diloco/distributed_syncer/
  controller_hooks.py
fs_diloco/learner_protocol/
  controller_hooks.py
experiments/sacc/
  fixed.yaml
  shadow.yaml
  enforced.yaml
  ablations.yaml
tests/sacc/
  test_replay_determinism.py
  test_shadow_no_effect.py
  test_guardrails.py
  test_epoch_invalidation.py
  test_fairness_starvation.py
  test_action_response_loss.py
```

## 5. 先冻结的设计决策

- [ ] D-1001：observation window与causal cutoff；
- [ ] D-1002：逐action列出system-only或algorithm-affecting分类；分类不确定时按algorithm-affecting处理；
- [ ] D-1003：system-only action如何绑定当前head并安全失效；algorithm-affecting decision必须采用新control/FWO/final identity和new-generation规则；
- [ ] D-1004：adaptive grace/quorum bounds与fairness objective；
- [ ] D-1005：hedge/replication action的minimum dwell/cooldown；
- [ ] D-1006：CPU/resource budget动作如何不违反PBS allocation；
- [ ] D-1007：head/epoch/strict fallback时action invalidation；
- [ ] D-1008：shadow→system-only enforced promotion evidence，以及独立的algorithm-tier qualification；
- [ ] D-1009：cost/goodput/quality multi-objective与negative result policy；
- [ ] D-1010：controller version/implementation digest冻结。

## 6. Codex执行循环

### Loop 1 — Observation与deterministic replay

**目标。** 从persisted structured metrics产生可重放observation和action suggestions。

**RED。** missing/late/out-of-order events、clock skew、restart、same events不同directory order、epoch/head cutover和corrupt metrics。

**GREEN。** canonical observation windows、quality flags、policy kernel、action schema和offline replay CLI。

**HARDEN。** 删除local state、snapshot+suffix、C9/D8 topology差异、unknown metrics；bad observation只能safe fallback。

**CHECK/PERSIST。** simulator/runtime/replay action digest一致。

**停止条件。** 同committed evidence产生同actions，metrics本身不成为authority。

### Loop 2 — Adaptive grace、quorum与fair selection

**目标。** 在slack内提高sample efficiency，避免稳定lexical/fast-node bias和starvation。

**RED。** heterogeneous learners、slow/recovering member、repeated same quorum、token imbalance、failure/rejoin tapes。

**GREEN。** bounded grace、eligible quorum、fairness debt/token weighting先作为shadow suggestion
和offline counterfactual；不改变当前run FWO。只有new-generation algorithm gate通过后，
decision才进入committed policy/FWO identity。

**HARDEN。** min/max/hysteresis、insufficient quorum、head/epoch change、stale proposals、quality guardrails。

**CHECK/PERSIST。** fixed/shadow trace ablation和starvation bounds。

**停止条件。** shadow不改变P06 interval/consumption语义且可重放；若进入enforced，必须在
新generation通过numeric/quality/response-loss gates。

### Loop 3 — Storage/backpressure、bundling与materialization

**目标。** 根据stage bottleneck调节in-flight、bundle、prefetch、scanner和materialization频率。

**RED。** validation-bound、read-bound、CAS-conflict、manifest-growth、GPU-interference等不同根因；controller若对所有情况给同action则失败。

**GREEN。** stage-specific cost model、bounded system-only actions和rollback；bundle只在P08
path存在且bundle mode已由run spec冻结时控制，controller不得动态发明新bundle语义。

**HARDEN。** response loss、partial bundle、snapshot/GC overlap、strict fallback、long-tail storage spike。

**CHECK/PERSIST。** shadow建议与counterfactual replay；action duty/conflict budgets。

**停止条件。** action不削弱correctness，能区分瓶颈。

### Loop 4 — Redundancy、hedge与learner-host resource control

**目标。** 自适应决定何时启动backup/hedge以及LFE可用CPU/I/O预算。

**RED。** no-failure、straggler、node failure、高GPU CPU pressure、Lustre congestion tapes；固定R2可能浪费或不足。

**GREEN。** 在FWO/run spec已冻结的replication/mode上限内选择hedge启动时机，并调节
thread/prefetch budgets/cooldown；replication factor或owner set变化属于algorithm/topology
tier，必须经committed reconfiguration，controller本身不能改变ownership authority。

**HARDEN。** false suspicion、oscillation、member churn、same-FWO divergence、budget saturation。

**CHECK/PERSIST。** fixed-off/fixed-R2/shadow/adaptive ablations。

**停止条件。** controller只选择已验证mode，不能绕过duplicate validation。

### Loop 5 — Shadow mode与guardrail qualification

**目标。** 证明controller observation/action稳定且shadow对训练无行为影响。

**RED。** shadow打开后任何FWO/transition/learner digest变化即失败。

**GREEN。** D1/D2/D8/D8-R2 shadow runs，记录suggested actions和counterfactual costs。

**HARDEN。** restart/action response loss、head/epoch change、controller crash和metrics gaps。

**CHECK/PERSIST。** independent replay、stability/oscillation、promotion decision。

**停止条件。** 只将有充分evidence的action子集标记enforceable。

### Loop 6 — Guarded enforced与ablation

**目标。** 先有限启用system-only actions并比较fixed/shadow/enforced；algorithm-affecting
subset只有qualification通过后才在新generation做独立ablation。

**RED。** pre-register action subset、bounds、rollback、success/failure criteria。

**GREEN。** small D2，再D8/D8-R2 50×10；至少fixed/shadow/system-enforced三组；decision
binding/restart可恢复。algorithm-enforced组仅在qualification通过时required，否则归档
`not_qualified`原因、反例和Checker结论。

**HARDEN。** controller/committer/owner crash、action response loss、strict fallback、quality smoke regression。

**CHECK/PERSIST。** raw runs、negative results、action traces和Checker。

**停止条件。** enforced不违反invariants；收益不足可得negative结论但证据完整。

## 7. 不变量

- [ ] shadow mode零行为影响；
- [ ] controller decision可重放；
- [ ] authority仍是committed history/head；
- [ ] controller不能关闭validation/fencing/strict replay；
- [ ] algorithm-affecting actions绝不在旧generation生效；若qualified则进入new-generation committed policy/FWO/transition identity；
- [ ] head/epoch change使旧action失效或按committed rule恢复；
- [ ] min/max/hysteresis/cooldown防oscillation；
- [ ] factor1/fixed modes保留为baseline/fallback；
- [ ] lifecycle roots覆盖committed decisions。

## 8. 验收标准

- [ ] P10-A01：P08 verified commit及其P07 lifecycle regressions和independent Checker PASS；
- [ ] P10-A02：observation/action schemas严格验证；
- [ ] P10-A03：simulator/runtime/replay action digests一致；
- [ ] P10-A04：删除local state后controller replay不变；
- [ ] P10-A05：shadow mode对FWO/transition/model digests零影响；
- [ ] P10-A06：adaptive grace/quorum shadow有bounds/hysteresis；若enforce则new-generation gate通过，否则标记`not_qualified`；
- [ ] P10-A07：fair selection shadow报告starvation/token weighting；若enforce则quality/numeric/new-generation gate通过，否则`not_qualified`；
- [ ] P10-A08：stage-specific controller可区分validation/read/publication/CAS/replay/export/interference瓶颈；
- [ ] P10-A09：in-flight/bundle/prefetch/materialization actions均受guardrails；
- [ ] P10-A10：hedge/replication/resource actions不能绕过ownership/duplicate validation；
- [ ] P10-A11：algorithm-affecting decision未在旧generation生效；若qualified则进入new-generation committed lineage，否则有Checker接受的`not_qualified` evidence；
- [ ] P10-A12：decision response-loss/restart可由ancestry恢复；
- [ ] P10-A13：owner/epoch/head jump废弃或确定恢复旧action；
- [ ] P10-A14：fixed/shadow D1/D2 suites通过；
- [ ] P10-A15：仅evidence-qualified action进入enforced，system与algorithm tier分别审批；
- [ ] P10-A16：D8 fixed/shadow/system-enforced 50×10对照完成；algorithm-enforced仅在qualified时required；
- [ ] P10-A17：D8-R2 fixed/shadow/system-enforced controlled fault对照完成；algorithm-enforced仅在qualified时required；
- [ ] P10-A18：correctness零double inclusion/mixed state/live deletion；
- [ ] P10-A19：GPU interference、Lustre、latency、duplicate cost和fault goodput完整；
- [ ] P10-A20：quality smoke无未解释回归；
- [ ] P10-A21：negative/neutral result不删除，claim按evidence收缩；
- [ ] P10-A22：active surface无SQLite/per-fragment heads/第二authority；
- [ ] P10-A23：report/checksums/clean commit/Checker一致；
- [ ] P10-A24：`STATE.yaml.next_action=P11`。

## 9. 可复制给Codex的启动指令

```text
在P08 verified commit上执行P10。实现distributed SACC的canonical observations、deterministic replay和fixed/shadow modes；先只enforce不改变trajectory的prefetch/materialization/hedge-start/LFE resource actions。grace/quorum/fairness/local interval/replication factor/bundle semantics属于algorithm-affecting tier，必须用new generation、committed identity和quality gate；未qualified时诚实归档not_qualified。shadow必须零行为影响；完成D8/D8-R2 fixed-shadow-system-enforced对照后进入P11。
```
