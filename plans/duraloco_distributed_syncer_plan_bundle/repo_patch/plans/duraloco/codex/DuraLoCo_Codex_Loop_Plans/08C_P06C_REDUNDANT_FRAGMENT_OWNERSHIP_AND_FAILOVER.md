---
plan_id: "P06C"
title: "Redundant Fragment Ownership、Hedged Execution 与 Failover"
status: "planned"
date: "2026-07-11"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/duraloco-p06b-learner-hosted-sync"
planning_basis_commit: "resolve_from_P06B_verified_report"
target_branch: "codex/duraloco-p06c-redundant-fragment-executors"
depends_on:
  - "P06B"
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
next_phase: "P07"
agent_decision_gates:
  - "默认warm-standby或hedge delay由agent基于D8 latency/failure evidence选择；必须保留fixed modes用于ablation。"
human_approval_gates: []
---

# P06C — Redundant Fragment Ownership、Hedged Execution 与 Failover

## 1. 阶段使命

在P06B无专用syncer主路径上增加replication factor 2、primary/backup ownership、可选hedged execution和committed reconfiguration。系统允许同一FWO被多个LFE重复执行，但只允许一个final logical commit；same-work-order divergent outputs必须fail closed。

### 1.1 研究主张

把executor放入learner failure domain不会要求复制持久optimizer server state。通过storage-resident parent、committed ownership和redundant prepare，whole learner-node failure可由其他learner host接管，且ownership迁移不需要optimizer-state transfer。

### 1.2 完成后的系统增量

- factor 2 owner sets；
- primary、warm standby、fixed active-active和hedged modes；
- deterministic winner validation；
- failure evidence→committed membership epoch change；
- D8-R2 chaos acceptance；
- redundancy cost/benefit telemetry；
- P07可从冻结的P06C object-lifecycle contract顺序启动；P08等待P07接口冻结后再开始。

## 2. 前置条件

- [ ] P06B-A01–A23通过；
- [ ] D8 no-dedicated-syncer baseline与C9 comparison存在；
- [ ] same FWO CRS/LFE equivalence稳定；
- [ ] PFT lifecycle在未做GC时可审计；
- [ ] failure detector只提供evidence、不直接拥有authority。

## 3. 范围

### 3.1 必须完成

- [ ] ownership replication factor 2；
- [ ] primary/backup role和deterministic ordering；
- [ ] warm standby mode；
- [ ] fixed active-active test mode；
- [ ] hedged execution with committed/configured delay；
- [ ] duplicate PFT equivalence/winner protocol；
- [ ] divergent duplicate fatal handling；
- [ ] committed reconfiguration under member/node loss；
- [ ] false suspicion safety；
- [ ] simultaneous primary/backup/committer failures matrix；
- [ ] D2-R2与D8-R2 chaos runs；
- [ ] wasted duplicate compute/I/O与tail-latency telemetry。

### 3.2 明确不做

- 不基于heartbeat自动无commit地重映射；
- 不把第一个完成者未经digest validation直接commit；
- 不实现Byzantine voting；
- 不做per-fragment independent authority；
- 不做destructive loser cleanup；
- 不让backup读取primary本地状态；
- 不把replication固定宣称总是优于factor 1。

## 4. 预期仓库变更

```text
fs_diloco/distributed_syncer/
  redundant_ownership.py
  hedge_policy.py
  duplicate_validation.py
  reconfiguration.py
  failure_evidence.py
  winner_selection.py
scripts/miyabi/
  pbs_d2_r2.sh
  pbs_d8_r2.sh
  chaos_executor_kill.sh
  chaos_node_loss.sh
tests/distributed_syncer/
  test_ownership_r2.py
  test_hedged_execution.py
  test_duplicate_equivalence.py
  test_divergent_duplicate_blocks.py
  test_reconfiguration_commit.py
  test_false_suspicion.py
  test_multi_failure_matrix.py
```

## 5. 先冻结的设计决策

- [ ] D-06C01：owner ordering/tie-break和factor change的epoch规则；
- [ ] D-06C02：backup何时读取/validate inputs，warm程度；
- [ ] D-06C03：hedge delay是run config、work-order field还是controller hint；本阶段必须可重放；
- [ ] D-06C04：duplicate equivalence是bitwise还是semantic digest；
- [ ] D-06C05：winner object identity规则，不影响semantic result；
- [ ] D-06C06：failure evidence阈值、false suspicion和reconfiguration authority；
- [ ] D-06C07：old epoch PFT reuse条件；默认fail closed；
- [ ] D-06C08：simultaneous failures的liveness boundary；
- [ ] D-06C09：loser PFT grace/retention接口交给P07R；
- [ ] D-06C10：D8-R2默认模式和ablation modes。

## 6. Codex执行循环

### Loop 1 — Replicated ownership与role determinism

**目标。** 同一committed epoch下每个fragment得到一致的primary/backup集合。

**RED。** membership order变化、hash tie、member session restart、factor change和stale epoch反例。

**GREEN。** rendezvous/top-r owner derivation、canonical owner order、ownership digest和role manifest。

**HARDEN。** member churn、same node多session、insufficient members、fragment count变化、epoch response loss。

**CHECK/PERSIST。** cross-process/cross-language如有实现的golden vectors。

**停止条件。** owner mapping只依赖committed facts，factor 2配置可重放。

### Loop 2 — Duplicate prepare与equivalence enforcement

**目标。** 同FWO多executor执行仍产生唯一、可验证的semantic result。

**RED。** same FWO same digest、same FWO divergent digest、different FWO same payload、partial PFT和duplicate response loss。

**GREEN。** duplicate set index由committer在RuntimeView派生；验证input/output digests；
等价attempt归并到一个canonical prepared-result digest。final transition identity引用
work-order/result digest与content-addressed parameter/state refs，不引用first-finish、
executor ID、attempt ID或telemetry。具体attempt/loser lineage作为审计evidence保留。

**HARDEN。** primary/backup不同CPU thread count、input arrival order、restart、cache state、bfloat16 decoding；任何divergence保存artifact并停止。

**CHECK/PERSIST。** active-active D1/D2 repeated equivalence soak。

**停止条件。** duplicate count和arrival/listing order不改变transition identity、committed
state digest或proposal consumption。

### Loop 3 — Warm standby与hedged execution

**目标。** 在正常情况下限制冗余成本，在慢/故障情况下压低prepare tail latency。

**RED。** hedge timer local wall-clock漂移、primary完成与hedge同时触发、cancel丢失、backup过度抢占CPU。

**GREEN。** work order记录mode与hedge policy identity；backup在固定/可重放delay后启动；winner commit后其他attempt取消或完成为loser；资源预算/backpressure优先保护GPU learner。

**HARDEN。** slow I/O、straggler CPU、primary crash、backup crash、timer restart和false hedge。

**CHECK/PERSIST。** fixed-off、warm、active-active、hedged四种mode的latency/CPU/I/O对比。

**停止条件。** hedge只影响liveness/performance，不影响selection或semantic result。

### Loop 4 — Committed reconfiguration与whole-node failover

**目标。** 节点失效后在不迁移optimizer state的情况下重新分配fragment责任。

**RED。** heartbeat误报、network/storage delay、primary+learner共死、stale node返回、committer与owner同节点死亡、membership change与active FWO并发。

**GREEN。** failure evidence聚合；current committer提交新MembershipControlTransition；新owner从committed parent/FWO/proposals恢复；active old-epoch work按ADR完成或取消。

**HARDEN。** consecutive epoch changes、insufficient quorum、double suspicion、old PFT late arrival、all LFEs temporary unavailable。

**CHECK/PERSIST。** D2-R2 kill matrix；证明没有state transfer或private checkpoint。

**停止条件。** false suspicion不破坏safety，真实node loss在定义RTO内恢复commit。

### Loop 5 — D8-R2 chaos与research baseline

**目标。** 在主shape证明冗余协议并测量收益边界。

**RED。** controlled failure tape、straggler injection和no-failure control；manifest缺失failure event或duplicate cost则分析失败。

**GREEN。** 运行D8 factor1、D8-R2 warm/hedged、可选active-active短run；注入executor kill、whole node kill、committer kill和combined failure。

**HARDEN。** 至少一次kill发生在prepare中间、一次CAS前后、一次primary+committer同节点；保持authoritative stop和terminal report。

**CHECK/PERSIST。** fault goodput、RTO/RPO、prepare p50/p95/p99、hedge rate、duplicate CPU/I/O、GPU step impact和model smoke quality。

**停止条件。** safety gates全部通过，liveness与cost结果不论正负都完整保存。

## 7. 不变量与故障注入

- [ ] owner overlap不等于multi-writer authority；
- [ ] 每个FWO最多一个final committed successor；
- [ ] 每个proposal在committed ancestry中最多一次logical inclusion；
- [ ] same FWO divergent outputs在真实运行中fatal并阻塞该run；预期故障注入必须产生可审计expected-BLOCKED outcome，但不因此把正确fail-closed的P06C阶段标成BLOCKED；
- [ ] winner按validated digest而非未验证“first finish”选择；
- [ ] ownership change必须committed；
- [ ] stale epoch/owner不能commit；
- [ ] new owner不读取old owner local state；
- [ ] hedge/cancel只影响资源，不改变numeric/selection；
- [ ] factor 1仍保留为baseline/fallback。

## 8. 验收标准

- [ ] P06C-A01：factor-2 ownership跨process deterministic；
- [ ] P06C-A02：primary/backup roles和ownership digest进入manifest/FWO；
- [ ] P06C-A03：membership不足时fail closed或按ADR明确降级，不静默改变factor；
- [ ] P06C-A04：same-FWO same-result duplicates可安全commit，且winner arrival/order不改变final transition identity；
- [ ] P06C-A05：same-FWO divergent digest在注入测试中产生expected-BLOCKED run并保存完整evidence；非注入真实divergence会阻塞阶段调查；
- [ ] P06C-A06：different-ID same-payload不被错误dedupe；
- [ ] P06C-A07：warm standby、active-active test和hedged modes均有自动测试；
- [ ] P06C-A08：hedge delay/mode identity可重放且进入work order；
- [ ] P06C-A09：winner commit后loser不能影响transition identity、consumption/frontier；
- [ ] P06C-A10：failure evidence本身不是authority；
- [ ] P06C-A11：committed reconfiguration在primary/whole-node loss后生效；
- [ ] P06C-A12：stale executor result被membership revision/ownership拒绝，stale committer head mutation被P05 fencing epoch拒绝；
- [ ] P06C-A13：ownership迁移无optimizer-state transfer，删除local dirs后可接管；
- [ ] P06C-A14：D2-R2 primary kill、backup kill、committer kill、whole-node kill通过；
- [ ] P06C-A15：primary+committer同节点联合故障通过定义的RTO/RPO；
- [ ] P06C-A16：false suspicion测试只造成额外计算/延迟，不破坏safety；
- [ ] P06C-A17：D8-R2 GPT-2/WikiText-2 50×10 terminal，无专用syncer；
- [ ] P06C-A18：controlled chaos中零duplicate logical inclusion、零mixed parameter/state；
- [ ] P06C-A19：报告factor1 vs warm/hedged的latency、CPU/I/O、GPU interference和fault goodput；
- [ ] P06C-A20：negative result同样保存，不以未证明性能收益阻止correctness conclusion；
- [ ] P06C-A21：PFT winner/loser和epoch objects的P07R lifecycle requirements已冻结；
- [ ] P06C-A22：active surface无SQLite/embedded DB/per-fragment heads/第二authority；
- [ ] P06C-A23：双语report、checker、manifest、checksums和clean commit一致；
- [ ] P06C-A24：`STATE.yaml.next_action=P07`，P07 lifecycle/object-identity contract完成后才允许P08启动。

## 9. 验证矩阵

| 层级 | 必需验证 |
|---|---|
| local | ownership golden vectors、duplicate state machine、hedge/reconfiguration property tests |
| D1-R2 | same-host executor duplicates与determinism |
| D2-R2 | owner/committer/whole-node failure matrix |
| D8-R2 | 50×10、controlled chaos、resource/latency telemetry |
| C9/D8 | CRS equivalence与factor1 comparison |

## 10. Maker–Checker交接

Maker提交failure tape、每个PFT/epoch/work-order lineage、fault timing、RTO/RPO和resource data。Checker必须构造一个false suspicion和一个same-FWO divergence注入，核对系统是fail closed而不是选择“多数/最快”继续。

## 11. 自动推进

P06C全部gate通过后从verified commit启动P07。为降低当前仓库尚未存在的membership/FWO/
PFT/snapshot schema同时演化风险，required route不并行实现P07和P08；P07先冻结snapshot、
reachability与GC接口，P08再在该verified commit上做性能优化。P07 destructive apply仍受
human approval。

## 12. 可复制给Codex的启动指令

```text
使用miyabi-development skill执行P06C。基线为P06B verified commit。在single global head和prepare-only LFE基础上实现factor-2 committed ownership、primary/backup、warm/active-active test/hedged modes、duplicate result enforcement和committed reconfiguration。先D1-R2/D2-R2故障矩阵，再D8-R2 chaos。same-FWO divergence注入必须得到expected-BLOCKED run。不要实现per-fragment heads或destructive GC。通过后顺序启动P07，P08等待P07接口冻结。
```
