---
plan_id: "P06B"
title: "Learner-Hosted Fragment Executors、Distributed Prepare 与 Floating Commit"
status: "planned"
date: "2026-07-11"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/duraloco-p06a-syncer-kernel"
planning_basis_commit: "resolve_from_P06A_verified_report"
target_branch: "codex/duraloco-p06b-learner-hosted-sync"
depends_on:
  - "P06A"
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
next_phase: "P06C"
agent_decision_gates:
  - "LFE process/sidecar packaging、CPU预算和bootstrap committer选举细节由agent依据Miyabi profile决定，经Checker复核。"
human_approval_gates: []
---

# P06B — Learner-Hosted Fragment Executors、Distributed Prepare 与 Floating Commit

## 1. 阶段使命

在不改变single global head和P05 fencing语义的前提下，把fragment validation/
aggregation/outer-step/immutable preparation放到learner节点受限CPU资源上的LFE。任一
learner host可以成为短期Floating Committer；系统以replication factor 1完成
D1→D2→D8，无专用syncer节点。

Membership、FWO和PFT不是当前P06 `head-fenced-v1` run spec/frontier/control schema中的
字段。P06B必须以新的run generation和新的`coordination_protocol`/schema digest启动，
不得向已完成P06 generation原地追加未知control transition，也不得把P06 archive称为
exact continuation。新generation使用相同初始化模型/config做matched comparison；任何
checkpoint bootstrap仍遵守D-M0003的warm/new-generation语义。

CRS保留为C9 oracle和offline/shadow comparison，不参与distributed generation的写入。

### 1.1 研究主张

persistent syncer service可被storage-resident optimizer history与replaceable learner-hosted executors替代；owner/executor本地状态全部丢失后，系统仍能从共享文件系统恢复并继续。

### 1.2 完成后的系统增量

- learner节点启动受限LFE；
- 新protocol generation中的committed membership revision与deterministic ownership factor 1；
- Floating Committer发布FWO、验证PFT并执行现有head CAS；
- D8 8 learner nodes完成50×10且`dedicated_syncer_nodes=0`；
- central-vs-distributed trace/digest equivalence；
- executor/committer crash和response-loss安全恢复。

## 2. 前置条件

- [ ] P06A-A01–A20通过；
- [ ] pure kernels、FWO/PFT schemas和capability audit冻结；
- [ ] CRS C9 oracle baseline可用；
- [ ] P05 lease/fencing适配成floating committer lease的ADR完成；
- [ ] Miyabi learner节点CPU/NUMA/Lustre baseline已记录。
- [ ] P06A冻结的新run-spec/frontier/control schema upgrade与bootstrap/rollback规则已经Checker复核；

## 3. 范围

### 3.1 必须完成

- [ ] LFE CLI/process lifecycle与learner launch integration；
- [ ] LFE CPU/RSS/thread/I/O budgets；
- [ ] MembershipControlTransition v1；
- [ ] 新run generation/bootstrap manifest，冻结distributed coordination protocol、execution backend和capability digests；
- [ ] deterministic ownership map v1，replication factor 1；
- [ ] Floating Committer lease/fencing/bootstrap/takeover；
- [ ] FWO authoritative planning/publication；
- [ ] LFE prepare-only execution与marker-last PFT；
- [ ] committer winner validation/final transition/head CAS；
- [ ] response-loss、head advance、stale epoch和orphan PFT handling；
- [ ] learner只adopt committed final transition；
- [ ] CRS offline/shadow equivalence；
- [ ] D1/D2/D8 no-dedicated-syncer gates；
- [ ] topology/capability/authority manifests。

### 3.2 明确不做

- 不做overlapping owners、backup或hedge；
- 不做dynamic replication；
- 不让多个independent final transitions并行CAS；
- 不做per-fragment heads；
- 不删除CRS；
- 不做destructive GC；
- 不让heartbeat直接改变membership；
- 不把LFE local queue/cursor持久化为authority。

## 4. 预期仓库变更

```text
fs_diloco/distributed_syncer/
  membership.py
  ownership.py
  work_order_store.py
  prepared_store.py
  executor.py
  committer.py
  bootstrap.py
  recovery.py
  topology_manifest.py
fs_diloco/distributed_syncer/cli.py              # module subcommands; do not shadow fs_diloco.cli
scripts/miyabi/
  run_duraloco_p06b_d1.pbs
  run_duraloco_p06b_d2.pbs
  run_duraloco_p06b_d8.pbs
tests/distributed_syncer/
  test_membership_commit.py
  test_ownership_r1.py
  test_executor_prepare_only.py
  test_floating_committer.py
  test_work_order_pft_commit.py
  test_crash_response_loss.py
  test_storage_only_recovery.py
```

## 5. 先冻结的设计决策

- [ ] D-06B01：LFE是learner同process thread、separate process还是sidecar；默认优先separate process以隔离GIL/故障；
- [ ] D-06B02：floating committer默认复用P05 conditional lease与head-committed owner token；如新增role字段必须属于新protocol generation且不能产生第二lease authority；
- [ ] D-06B03：新generation bootstrap避免选举循环：operator/launcher先生成logical member与session IDs，原子genesis同时冻结revision-0 membership和run spec；只有该集合中的committer candidates可竞争P05 lease并提交首个owner epoch bump。后续membership变化才使用control transition；同时冻结P06 matched initialization/warm bootstrap边界；
- [ ] D-06B04：membership eligibility与learner/executor session绑定；
- [ ] D-06B05：ownership rendezvous hash canonicalization；
- [ ] D-06B06：FWO发布和final commit的request identity/response-loss reconciliation；
- [ ] D-06B07：PFT发现、validation、reuse和stale classification；
- [ ] D-06B08：D8默认CPU affinity/RSS/in-flight I/O budget；
- [ ] D-06B09：CRS shadow/offline comparison不能获得distributed generation write capability；
- [ ] D-06B10：单active FWO或bounded planning window；本阶段默认一个active authoritative FWO。
- [ ] D-06B11：CPU LFE execution backend、Torch/BLAS/thread/reduction-order identity；same-FWO duplicates只允许同一冻结backend，C9 GPU oracle比较使用明确tolerance而非伪造content-digest相等；
- [ ] D-06B12：canonical prepared-result identity排除executor/attempt/timing，attempt envelope与result digest分离，final transition identity不依赖listing/first-finish顺序。

## 6. Codex执行循环

### Loop 1 — Topology、membership与capability foundation

**目标。** 先建立“谁可执行/谁可commit”的committed facts和fail-closed capability。

**RED。** heartbeat-only owner change、stale session、duplicate member ID、executor尝试head CAS、CRS误入distributed generation写入必须失败。

**GREEN。** 扩展`RunSpec`、frontier/replay与control schema并启动全新distributed
generation；原子genesis冻结revision-0 membership/capabilities，bootstrap committer只能从
该集合竞争P05 lease并提交首个owner epoch bump；定义后续MembershipControlTransition；
ownership map factor 1从committed facts确定性派生；manifest记录role placement。旧reader
遇到新protocol必须fail closed，新reader仍能只读验证P06 archive。

**HARDEN。** partial membership publication、epoch response loss、stale heartbeat、clock skew、same ID/conflicting capability digest。

**CHECK/PERSIST。** capability static/runtime audit，membership replay digest。

**停止条件。** 删除所有local membership cache后得到同一owner map，heartbeat不具authority。

### Loop 2 — LFE process与prepare-only path

**目标。** learner host CPU可安全执行FWO并发布PFT。

**RED。** LFE读取未commit parent、改变selection、写head、超CPU/RSS预算、crash mid-payload/PFT marker。

**GREEN。** separate LFE process读取canonical FWO和validated inputs，调用P06A kernels，
marker-last写content-addressed parameter/state、canonical prepared-result和attempt envelope；
不持有commit credential/path。CPU backend/thread/reduction order必须进入FWO implementation identity。

**HARDEN。** cancellation、SIGKILL、learner process crash但LFE存活、LFE crash但learner存活、whole node loss、corrupt input/output、diskless restart。

**CHECK/PERSIST。** local simulator和D1 raw traces，resource counters。

**停止条件。** PFT可由CRS离线重算得到同digest，未commit PFT不会被learner采用。

### Loop 3 — Floating Committer与single authoritative commit

**目标。** 把planner/committer从dedicated节点迁移到任一learner host，同时保留P05安全性。

**RED。** 双committer、stale fencing、CAS response loss、head advance while prepare、same FWO conflicting PFT、committer crash各阶段。

**GREEN。** committer strict replay→select/plan→FWO→validate PFT→final transition→head CAS；
lease可在learner hosts间takeover。final transition只绑定canonical work-order/result digest和
content refs；executor ID、attempt ID、timing与first-finish顺序只属于evidence envelope，
不得改变optimizer transition identity。

**HARDEN。** kill before/after FWO、after PFT validation、before/after CAS、before ack；new committer复用合法PFT或replan，不重复logical inclusion。

**CHECK/PERSIST。** D1/D2 committer failover和ancestry reconciliation报告。

**停止条件。** dedicated syncer进程缺席时系统持续commit，双committer不能形成两个successors。

### Loop 4 — Learner integration与storage-only recovery

**目标。** 新distributed generation的final transitions成为learner唯一adoption source。

**RED。** learner误读PFT/latest derived file、adopt mid-interval、executor local state丢失、committer local state丢失、all processes restart。

**GREEN。** launcher在每个learner node启动learner+LFE；learner boundary读取committed frontier；所有control/data local caches可重建。

**HARDEN。** restart order permutation、listing omission、slow Lustre、materialization lag、authoritative stop、warm learner recovery。

**CHECK/PERSIST。** 删除local dirs后的D1/D2 recovery；P06 interval/adoption regressions。

**停止条件。** shared storage是唯一不可替代状态，distributed run不依赖CRS。

### Loop 5 — D8 no-dedicated-syncer acceptance与equivalence

**目标。** 以八个learner节点完成主生产shape并量化共置干扰。

**RED。** topology checker检测任何dedicated syncer node；central/distributed digest mismatch；GPU step regression无telemetry；work order卡死无terminal reason。

**GREEN。** D8 PBS/launch scripts、manifest和terminal state；CRS对同trace offline/shadow复算；采集CPU/GPU/Lustre和分段latency。

**HARDEN。** kill一个LFE后本阶段可通过committer重建membership/reassign factor-1 owner（允许短暂停顿）；kill committer后takeover；不要求同时冗余。

**CHECK/PERSIST。** matched C9/D8 comparison，Checker核实资源allocation和无隐式第九
节点。selected IDs、hex weights、scheduler/control semantics必须exact；若C9和LFE的
execution backend不同，parameter/outer-state保存双方content digest并按预先冻结的
`atol/rtol`比较，不声称bitwise digest equality。

**停止条件。** D8 50×10、≤15分钟目标、无专用syncer，correctness/equivalence和恢复gate通过。

## 7. 不变量与失败注入

- [ ] final head仍唯一authority；
- [ ] LFE只能prepare；
- [ ] committer lease/fencing与head CAS共同裁决；
- [ ] membership/ownership只由committed epoch决定；
- [ ] factor 1下每fragment一个eligible owner，但owner loss可经新epoch reassign；
- [ ] FWO固定selection，LFE不能重新扫描决定quorum；
- [ ] PFT不消费proposal；
- [ ] same FWO divergent PFT阻塞；
- [ ] learner只adopt committed transition；
- [ ] executor/committer local state全部可删除；
- [ ] distributed generation中CRS无write capability。
- [ ] P06B只写新distributed run generation；P06 archive generation保持只读且不被in-place升级；
- [ ] final transition identity不绑定executor/attempt/telemetry或first-finish顺序；

故障矩阵：LFE/learner/committer SIGKILL、whole node loss、partial object、response loss、head race、epoch race、listing omission、slow storage、corruption和restart permutation。

## 8. 验收标准

- [ ] P06B-A01：新run generation的RunSpec/frontier/control upgrade、MembershipControlTransition严格schema/identity/replay和旧reader fail-closed通过；
- [ ] P06B-A02：factor-1 ownership在同epoch跨process产生同digest；
- [ ] P06B-A03：heartbeat/listing不能直接改变owner；
- [ ] P06B-A04：LFE separate process/sidecar可由learner launch，资源预算进入manifest；
- [ ] P06B-A05：LFE production entrypoint只接收无head key/conditional_replace的restricted facade，static/runtime audit防误接authority API；报告明确同Unix账号非Byzantine边界；
- [ ] P06B-A06：FWO固定parent、fragment、selection、weights、epoch和implementation identities；
- [ ] P06B-A07：PFT marker-last、parameter/state pair和same-ID conflict tests通过；
- [ ] P06B-A08：同backend CRS/LFE对相同FWO的core content digests exact；跨CPU/GPU比较保留双方digests并通过冻结tolerance，报告不得把numeric equivalence写成content identity；
- [ ] P06B-A09：Floating Committer复用/扩展P05 lease/fencing并通过双owner反例；
- [ ] P06B-A10：committer各crash point和CAS response-loss恢复无duplicate commit；
- [ ] P06B-A11：head advance使stale PFT被拒绝或明确rebase，不能套用新parent；
- [ ] P06B-A12：learner只在boundary adopt final committed frontier，不读取PFT；
- [ ] P06B-A13：删除executor/committer local state后storage-only recovery成功，且未读取P06 derived exports或旧generation authority；
- [ ] P06B-A14：D1真实model/data ≤10 steps finite且至少一distributed commit/adopt；
- [ ] P06B-A15：D2无专用syncer，executor kill、committer kill和whole-node kill各通过；
- [ ] P06B-A16：D8 manifest证明8 learner nodes、8 learners、LFEs、`dedicated_syncer_nodes=0`；
- [ ] P06B-A17：D8 GPT-2/WikiText-2 50×10在15分钟目标内terminal，interval/adoption/stop正确；
- [ ] P06B-A18：matched C9/D8的policy/control identity exact、tensor numeric tolerance与quality smoke equivalence通过；双方content digests和backend identities完整保留；
- [ ] P06B-A19：报告CPU affinity/RSS、GPU step time、Lustre bytes/ops和publish→prepare→commit→adopt；
- [ ] P06B-A20：active surface无SQLite/embedded DB和第二authority；
- [ ] P06B-A21：CRS保留为oracle/fallback但distributed generation无write access；
- [ ] P06B-A22：双语report、checker、manifest、checksums和clean commit一致；
- [ ] P06B-A23：new-generation bootstrap/rollback report完整，`STATE.yaml.next_action=P06C`，不得直接进入P07/P08/P10。

## 9. 验证矩阵

| 层级 | 必需验证 |
|---|---|
| local | membership/ownership、FWO/PFT、capability、state-machine、differential |
| D1 | learner+LFE+committer同节点；真实小步；crash/restart |
| D2 | 无专用syncer；committer/executor/whole-node failover |
| D8 | 8 learner nodes；50×10；资源与interference telemetry |
| C9 | matched oracle/baseline，不与D8同generation写入 |

## 10. Maker–Checker交接

Maker提交topology manifests、capability audits、all fault traces、C9/D8 comparison和每个
acceptance证据。Checker必须检查PBS资源申请中没有隐藏第九节点，删除所有local state
重启，并检查LFE production dependency graph/constructed facade无法意外到达head CAS；
不得把“任意同账号恶意Python无法import storage backend”作为当前failure model的gate。

## 11. 自动推进

所有A01–A23通过后进入P06C。实现顺序必须是schema/bootstrap unit gate→D1→D2→D8；
任一层未通过不得跳级。若D8不满足15分钟但correctness通过，不得伪造pass；保存matched
C9/D8数据，定位CPU/I/O干扰并仍在P06B修复。P06C之前禁止加入active-active redundancy。

## 12. 可复制给Codex的启动指令

```text
使用miyabi-development skill执行P06B。基线为P06A verified commit。实现learner-hosted LFE、committed membership/ownership factor 1、FWO/PFT和Floating Committer；保留single global head与P05 fencing。先D1，再D2，最后D8；D8必须无专用syncer节点。CRS只作离线/shadow oracle，不得写distributed generation。不要实现overlap/hedge/per-fragment heads。全部gate通过后next_action=P06C。
```
