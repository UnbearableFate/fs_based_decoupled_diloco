---
plan_id: "P11"
title: "Miyabi Integration、Chaos 与 Dedicated-Syncer-Free Acceptance"
status: "planned"
date: "2026-07-11"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/duraloco-p10-distributed-sacc"
planning_basis_commit: "resolve_from_P10_verified_report"
target_branch: "codex/duraloco-p11-distributed-acceptance"
depends_on:
  - "P10"
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
next_phase: "P12"
agent_decision_gates:
  - "select<=16、walltime<=02:00:00的Miyabi jobs可由agent按1→2→8节点阶梯自主提交；non-transient failure遵守retry lock。"
human_approval_gates:
  - "超出既定Miyabi资源、72h正式soak或公共云资源"
---

# P11 — Miyabi Integration、Chaos 与 Dedicated-Syncer-Free Acceptance

## 1. 阶段使命

把P06B–P10的distributed syncer主线固化为可重复的Miyabi生产workflow，完成D1、D2、D8和D8-R2的preflight、chaos、artifact packaging与operator drill。C9 dedicated CRS保留为matched reference baseline，但P11的主acceptance是八个learner节点、零专用syncer节点。

### 1.1 研究主张

系统在实际HPC scheduler、Lustre和整节点故障条件下保持唯一authority、无全局停机或可界定RTO，并把原需9节点的1S+8L工作负载迁移为8节点D8；资源节省及learner-host干扰都有可审计证据。

### 1.2 完成后的系统增量

- 标准PBS/preflight/launch/verify/packager；
- D1/D2/D8/D8-R2 terminal gates；
- executor、committer、learner、whole-node、storage-tail和lifecycle fault tapes；
- C9 matched baseline；
- operator runbook和clean artifact bundle。

## 2. 前置条件

- [ ] P10-A01–A24通过；
- [ ] fixed/shadow/enforced选择和默认mode冻结；
- [ ] P07 lifecycle和P08 telemetry集成；
- [ ] D8/D8-R2 topology manifests可校验；
- [ ] current clean commit、dependencies和checksums一致。

## 3. 范围

### 3.1 必须完成

- [ ] PBS scripts/preflight/static shell checks；
- [ ] environment/module/cache/storage namespace validation；
- [ ] role placement和capability audit；
- [ ] D1 real acceptance；
- [ ] D2 failover/chaos；
- [ ] D8 50×10 terminal acceptance；
- [ ] D8-R2 controlled chaos acceptance；
- [ ] matched C9 CRS baseline；
- [ ] snapshot/capsule/GC dry-run integration；
- [ ] SACC fixed/shadow/default mode validation；
- [ ] fault tape、authority timeline、stage timings和qstat lineage；
- [ ] fail-closed artifact packager；
- [ ] operator runbook和recovery drill；
- [ ] terminal retry lock discipline。

### 3.2 明确不做

- 不自动提交72h正式soak；
- 不在login node运行runtime；
- 不把C9重新设为生产主路径；
- 不在P11引入新optimizer/protocol generation；
- 不删除失败/取消/人工终止runs；
- 不把operator termination冒充infrastructure failure。

## 4. 预期仓库变更

```text
scripts/miyabi/
  preflight.sh
  pbs_d1_acceptance.sh
  pbs_d2_chaos.sh
  pbs_d8_acceptance.sh
  pbs_d8_r2_chaos.sh
  pbs_c9_reference.sh
  verify_topology.sh
  package_artifacts.sh
  retry_lock.py
plans/duraloco/runbooks/
  distributed_syncer_operations.md
  failure_recovery.md
  artifact_reproduction.md
tests/integration/
  test_pbs_scripts_static.py
  test_topology_manifest.py
  test_authority_surface.py
  test_artifact_packager.py
  test_retry_lock.py
```

## 5. 先冻结的设计决策

- [ ] D-1101：D8/D8-R2 exact PBS resource layout和CPU affinity；
- [ ] D-1102：default production controller/redundancy mode；
- [ ] D-1103：fault tape timing与expected RTO/RPO bounds；
- [ ] D-1104：C9 matched baseline的资源/配置对齐；
- [ ] D-1105：acceptance terminal criteria和inconclusive分类；
- [ ] D-1106：artifact bundle minimum evidence；
- [ ] D-1107：retry lock解除条件；
- [ ] D-1108：operator drill与authoritative stop；
- [ ] D-1109：optional longer soak approval boundary。

## 6. Codex执行循环

### Loop 1 — PBS/preflight标准化

**目标。** 每个shape在提交前fail fast检查commit、modules、storage、namespace、topology和forbidden surfaces。

**RED。** wrong node count、hidden syncer node、missing LFE、duplicate GPU assignment、bad cache path、login-node runtime、stale plan checksum、SQLite artifact。

**GREEN。** reusable preflight、PBS scripts、manifest skeleton、role/hostname/rank mapping和actual CPU affinity audit。

**HARDEN。** queued/cancelled、module drift、storage permissions、partial artifact dir、resubmission lineage。

**CHECK/PERSIST。** shellcheck/static tests和dry-run render。

**停止条件。** invalid job不进入training，valid job可由manifest完整描述。

### Loop 2 — D1真实acceptance

**目标。** 最小真实model/data path验证learner+LFE+committer+lifecycle/controller。

**RED/GREEN。** ≤10 optimizer steps，至少一FWO/PFT/final commit/adopt；snapshot/capsule；executor/committer restart；fixed/shadow modes。

**HARDEN。** payload/marker kill、head jump/corrupt successor、local-state deletion和strict replay。

**CHECK/PERSIST。** current commit D1 bundle。

**停止条件。** finite loss、authority/digests正确、artifact完整。

### Loop 3 — D2 failover/chaos

**目标。** 两learner节点证明committer、primary/backup、whole-node和reconfiguration语义。

**RED/GREEN。** P05 old-owner resume、P06C duplicate/divergence、owner/committer同节点kill、false suspicion、capsule restore、GC dry-run。

**HARDEN。** kill points覆盖before/afterPFT、before/afterCAS、response loss和stale epoch return。

**CHECK/PERSIST。** fault tape replay和authority timeline。

**停止条件。** 零split brain/double inclusion/mixed state/live deletion。

### Loop 4 — D8 primary acceptance

**目标。** 8 learner nodes、0 dedicated syncer完成GPT-2/WikiText-2 50 inner steps×10 outer transitions，目标15分钟。

**RED。** topology checker、terminal manifest、interval/adoption、lifecycle、telemetry、controller和resource criteria预注册。

**GREEN。** fixed和default production mode至少各一run（可在同一clean commit不同config）；所有角色hostname/session/fragment ownership可追踪。

**HARDEN。** 一个LFE kill和一个committer takeover；不要求本run整节点loss，后者在D8-R2。

**CHECK/PERSIST。** matched C9 comparison、node/GPU-hours和GPU interference。

**停止条件。** D8 terminal，或真实失败按retry discipline保存并修复。

### Loop 5 — D8-R2 controlled chaos

**目标。** 完整redundancy和distributed lifecycle/controller在主shape通过故障campaign。

**RED。** pre-record fault tape：primary LFE、backup、committer、whole learner node、slow Lustre/CPU、snapshot/GC overlap。

**GREEN。** 运行50×10或等价预注册workload；保留failure-free control；记录RTO/RPO、fault goodput、duplicate cost、quality smoke。

**HARDEN。** 至少一次primary+committer co-failure和late stale node return；same-FWO divergence injection在separate expected-BLOCKED run。

**CHECK/PERSIST。** Checker独立从bundle重建authority和fault timeline。

**停止条件。** safety全部通过，liveness/性能结果完整。

### Loop 6 — Artifact/operator drill

**目标。** 新操作者只凭bundle/runbook可验证、恢复和解释run。

**RED。** 删除汇总文件、缺raw event、缺qstat、缺commit/config/checksum或缺failure lineage时packager必须失败。

**GREEN。** package manifests、commands、logs、objects refs、traces、analysis、checker和reproduction script；演练authoritative stop、takeover、capsule restore和strict verify。

**HARDEN。** clean directory reproduction、read-only store copy、partial bundle、historical failure inclusion。

**CHECK/PERSIST。** independent artifact review。

**停止条件。** bundle self-describing且fail closed。

## 7. 不变量

- [ ] D8/D8-R2无专用syncer节点；
- [ ] C9不与distributed run同generation写入；
- [ ] head mutation只经audited committer API；
- [ ] learner/LFE无head-CAS surface；
- [ ] fault注入不删除真实失败证据；
- [ ] retry lock防同shape盲目重提；
- [ ] artifact缺关键evidence时fail closed；
- [ ] login node仅control plane。

## 8. 验收标准

- [ ] P11-A01：全部PBS/shell/static checks通过；
- [ ] P11-A02：preflight检测hidden dedicated syncer/role mismatch/forbidden surface；
- [ ] P11-A03：D1 real ≤10-step finite且distributed commit/adopt；
- [ ] P11-A04：D1 strict replay/snapshot/capsule/controller smoke通过；
- [ ] P11-A05：D2 committer/owner/whole-node failover无split brain；
- [ ] P11-A06：D2 duplicate/divergence/false-suspicion fault tests符合预期；
- [ ] P11-A07：D8 manifest为8 learner nodes、0 dedicated syncer；
- [ ] P11-A08：D8 GPT-2/WikiText-2 50×10目标15分钟terminal；
- [ ] P11-A09：D8每个role hostname/session/GPU/CPU affinity/ownership可追踪；
- [ ] P11-A10：D8 LFE kill与committer takeover期间training继续并正确terminal；
- [ ] P11-A11：matched C9 central reference run完整且不参与D8 authority；
- [ ] P11-A12：C9/D8资源、latency、GPU interference和quality smoke可比；
- [ ] P11-A13：D8-R2 controlled chaos 50×10或预注册等价workload通过；
- [ ] P11-A14：whole-node及primary+committer co-failure有RTO/RPO/fault goodput；
- [ ] P11-A15：same-FWO divergence expected-BLOCKED artifact完整；
- [ ] P11-A16：snapshot/capsule/GC dry-run与chaos并发零live deletion；
- [ ] P11-A17：SACC default mode决策可重放且fixed fallback通过；
- [ ] P11-A18：所有pass/fail/inconclusive/queued-cancelled/retry有parent lineage；
- [ ] P11-A19：non-transient terminal failure触发retry lock及D1→D2 requalification；
- [ ] P11-A20：operator termination保留真实exit/status，不冒充infra failure；
- [ ] P11-A21：artifact packager缺证据fail closed；
- [ ] P11-A22：Checker从clean bundle重跑当前suite、历史反例和新反例；
- [ ] P11-A23：active source/config/CLI/PBS/tests/artifacts无SQLite/embedded DB；
- [ ] P11-A24：authority audit证明无第二authority/per-fragment heads；
- [ ] P11-A25：report/state/checksums/clean commit一致；
- [ ] P11-A26：`STATE.yaml.next_action=P12`。

## 9. 自动推进与资源门

P11通过后进入P12。72h soak、>16 nodes、>2h单job或public cloud需要明确批准；未批准不阻塞P11/P12的既定必需实验。非transient D8/D8-R2失败不得直接同shape重提。

## 10. 可复制给Codex的启动指令

```text
执行P11R Miyabi acceptance。标准化PBS/preflight后按D1→D2→D8→D8-R2阶梯验证；D8/D8-R2必须8 learner nodes且0 dedicated syncer，C9只作matched reference。运行fault tapes、lifecycle/controller和artifact/operator drill。遵守non-transient retry lock与login-node纪律。全部gate通过后进入P12。
```
