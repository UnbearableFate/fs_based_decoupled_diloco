---
plan_id: "P07"
title: "Distributed Lifecycle：Compaction、Reachability GC、Acks 与 Learner Capsules"
status: "planned"
date: "2026-07-11"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/duraloco-p06c-redundant-fragment-executors"
planning_basis_commit: "resolve_from_P06C_verified_report"
target_branch: "codex/duraloco-p07-distributed-lifecycle"
depends_on:
  - "P06C"
required_skill: "miyabi-development"
execution_mode: "single-writer staged implementation + independent checker"
automatic_progression: true
next_phase: "P08"
agent_decision_gates:
  - "snapshot形式、ack语义、orphan/loser grace和capsule cadence由agent基于replay/reachability evidence决定。"
human_approval_gates:
  - "destructive GC apply outside synthetic/test namespaces"
---

# P07 — Distributed Lifecycle：Compaction、Reachability GC、Acks 与 Learner Capsules

## 1. 阶段使命

在P06C的FWO/PFT、committed membership/ownership和redundant execution对象图上，实现snapshot+suffix replay、可解释reachability、默认dry-run的安全GC、learner acknowledgements以及exact learner capsules。生命周期逻辑必须适用于D8/D8-R2，不假设存在长期central syncer或固定owner。

### 1.1 研究主张

共享存储不仅承载正常optimizer authority，也能在没有stateful syncer service的情况下支持bounded growth、checkpoint/replay、owner failover和exact learner recovery；GC安全性由immutable root snapshot和committed ancestry证明，而不是由当前进程或目录listing判断。

### 1.2 完成后的系统增量

- strict full、memoized full、snapshot+suffix三种replay等价；
- distributed object graph与explainable roots；
- FWO/PFT winner/loser、epoch、response-loss和capsule-aware GC；
- exact learner capsule，与warm restart分开；
- D8-R2 accelerated soak显示有界steady state。

## 2. 前置条件

- [ ] P06C-A01–A24通过；
- [ ] PFT winner/loser、epoch和FWO lifecycle requirements冻结；
- [ ] P06C verified commit与本worktree dependency digest一致；
- [ ] P08尚未启动；P07先冻结shared object identity/reachability/capsule interfaces；
- [ ] destructive apply使用独立approval token和namespace guard。

## 3. 范围

### 3.1 必须完成

- [ ] authoritative snapshot manifest和covered head；
- [ ] snapshot+suffix replay与strict fallback；
- [ ] distributed reachability graph；
- [ ] learner/executor/committer ack semantics；
- [ ] roots：head/prefix、snapshot、capsule、FWO、PFT winner/loser grace、membership/ownership、stop/control、response-loss、experiment pins；
- [ ] immutable mark snapshot、head/epoch revalidation和default dry-run GC；
- [ ] delete request identity/response-loss reconciliation；
- [ ] exact learner capsule：model/frontier、inner optimizer、RNG、data cursor、interval state；
- [ ] warm vs exact recovery reporting；
- [ ] D8/D8-R2 accelerated bounded-growth soak；
- [ ] restore-after-GC和owner-reassignment-after-GC tests。

### 3.2 明确不做

- 不删除committed history中仍被live snapshot/capsule/experiment引用的objects；
- 不因PFT“未commit”立即删除；
- 不让inactive heartbeat自动解除roots；
- 不做跨provider archival policy；
- 不修改optimizer算法或ownership protocol；
- 不在用户真实run上自动destructive apply；
- 不用database保存reachability index。

## 4. 预期仓库变更

```text
fs_diloco/log/
  snapshot.py
  compaction.py
  replay_modes.py
  reachability.py
  gc.py
  pins.py
  acknowledgements.py
fs_diloco/distributed_syncer/
  lifecycle_roots.py
  prepared_retention.py
fs_diloco/learner_protocol/
  capsule.py
  exact_recovery.py
fs_diloco/lifecycle_cli.py                    # 或fs_diloco.log子命令；不得shadow现有fs_diloco.cli
tests/lifecycle/
  test_snapshot_suffix_replay.py
  test_distributed_reachability.py
  test_prepared_winner_loser_roots.py
  test_gc_concurrency.py
  test_gc_response_loss.py
  test_capsule_roundtrip.py
  test_restore_after_gc.py
  test_bounded_growth_d8.py
```

## 5. 先冻结的设计决策

- [ ] D-0701：snapshot是committed control transition还是immutable side object+committed pin；
- [ ] D-0702：ack区分observed、durably adopted、capsuled和no-longer-needs；
- [ ] D-0703：inactive learner/executor是否阻止哪些对象回收；
- [ ] D-0704：PFT winner、same-digest loser、divergent blocker evidence和orphan的不同retention；
- [ ] D-0705：active FWO/epoch change/response-loss reconciliation roots；
- [ ] D-0706：capsule consistency point与未决interval/proposal；
- [ ] D-0707：GC mark/apply、approval token、namespace和head/epoch revalidation；
- [ ] D-0708：snapshot+suffix与process-local memoization组合及strict fallback；
- [ ] D-0709：bundle transition（若P08后集成）对reachability的扩展接口；
- [ ] D-0710：bounded-growth target和accelerated soak映射。

## 6. Codex执行循环

本阶段虽然共享一个P07 Checker verdict，但实现必须按可独立回退的子门顺序推进：

```text
P07.1 snapshot/replay read-only
  → P07.2 reachability + GC dry-run
  → P07.3 synthetic namespace apply + restore
  → P07.4 exact-capsule tiny path
  → P07.5 D1 → D2-R2 → D8-R2 integration
```

前一子门没有Maker evidence和局部Checker结论时，不得开始后一子门；尤其不能在
snapshot/reachability尚未证明时实现destructive apply。

### Loop 1 — Snapshot、compaction与suffix replay

**目标。** 从latest valid reachable snapshot加committed suffix重建与empty-cache strict full相同状态。

**RED。** snapshot partial write、covered head不在ancestry、head并发前进、snapshot corrupt/missing/stale、epoch/control-only transition遗漏、bundle/object ref缺失。

**GREEN。** immutable snapshot内容和manifest；绑定covered transition；restore选择合法reachable snapshot；suffix strict validate；失败自动回退empty-cache strict full。

**HARDEN。** failure cache不污染memoization；snapshot writer/committer/owner crash；multiple snapshots/list omission；CRS/D8 replay共同适用。

**CHECK/PERSIST。** 每个prefix的strict/memoized/snapshot digests和object read counts。

**停止条件。** 所有prefix状态等价，坏snapshot只影响性能不影响correctness。

### Loop 2 — Ack、watermark与distributed reachability

**目标。** 为每个live/candidate object给出从immutable roots到对象的可解释路径。

**RED。** active FWO、PFT winner/loser、late old-epoch PFT、membership transition、learner capsule、response-loss record、pinned experiment被旧central-only graph遗漏。

**GREEN。** typed object graph与root snapshot；ack/watermark按role/session/fragment区分；explain CLI输出root→edge→object和retention reason。

**HARDEN。** learner/owner churn、false suspicion、capsule upload中断、snapshot concurrently created、listing omission和unknown object quarantine。

**CHECK/PERSIST。** Checker随机抽样live和candidate delete反向追踪。

**停止条件。** 无无法解释的live root或立即delete candidate。

### Loop 3 — Safe GC

**目标。** 只删除在immutable mark snapshot中不可达、超过grace且在apply前重新验证仍安全的对象。

**RED。** GC与FWO/PFT publication、final commit、capsule/snapshot、restore、epoch change并发；delete response loss；batch partial success；list omission；payload-before-marker。

**GREEN。** mark generation、dry-run report、approval token、head/epoch revalidation、idempotent delete request identity、audit/tombstone record。

**HARDEN。** apply crash/restart、same key independent delete、old loser PFT late validation、D8 node failure during GC。

**CHECK/PERSIST。** synthetic namespaceapply后strict restore；真实namespace默认dry-run。

**停止条件。** fault matrix零live deletion，repeated apply幂等。

### Loop 4 — Learner capsule exact recovery

**目标。** 与warm restart分开，恢复learner inner optimizer、RNG/data cursor、model/frontier和interval boundary。

**RED。** capsule before/afterproposal、mid-interval、adoption race、head/epoch advance、partial capsule、same ID conflict、whole-node loss。

**GREEN。** 先把当前`hf_data` iterator与learner state改造成显式restorable source：
synthetic path保存真实`torch.Generator` state，WikiText path保存dataset/tokenization identity和
batch index；同时捕获inner optimizer、scheduler/scaler、CPU/CUDA RNG、model/frontier与
interval boundary。随后发布immutable capsule components+manifest marker，定义consistency
point、restore validation、未决intervaldiscard/reconcile规则和new session/sequence规则。

**HARDEN。** bfloat16/float32 identities、scheduler/scaler、dataloader cursor、capsule response loss、GC pin/unpin。

**CHECK/PERSIST。** synthetic tiny在同device/backend要求bitwise continuation；WikiText真实
小步仅在dataset/tokenizer/cache identity与全部RNG/iterator state可验证时才称exact，否则
必须fail closed或明确降级warm；保存warm/exact cost comparison。

**停止条件。** exact claim只在全部captured states下成立，缺字段fail closed或明确降级warm。

### Loop 5 — D8-R2 accelerated soak与bounded growth

**目标。** 在distributed redundant topology验证snapshot/GC/capsule不阻塞training且storage达到可解释steady state。

**RED。** 预注册object/bytes growth bound、snapshot/capsule cadence、orphan/loser rates和fault tape。

**GREEN。** D8-R2 accelerated run，周期snapshot/capsule/GC dry-run；synthetic namespace可在批准下apply；注入owner/node/committer failure。

**HARDEN。** restore from multiple points、GC后owner reassignment、corrupt snapshot fallback、slow learner watermark。

**CHECK/PERSIST。** raw object inventory、reachability summaries、growth curve、restore times和GPU impact。

**停止条件。** live storage随retention window而非总transition数无界增长，或负结果被完整解释并阻塞claim。

## 7. 不变量与失败注入

- [ ] snapshot不是第二authority；
- [ ] snapshot+suffix与strict replay等价；
- [ ] FWO/PFT/epoch/control roots完整；
- [ ] listing absence不证明不可达；
- [ ] GC default dry-run，apply需要approval；
- [ ] mark基于immutable root snapshot，apply前revalidate head/epoch；
- [ ] exact capsule与warm restart标签分开；
- [ ] owner change不需要被删除对象中的private state；
- [ ] active source/artifacts无SQLite/embedded DB。

## 8. 验收标准

- [ ] P07-A01：strict full、memoized full、snapshot+suffix对每个prefix digest一致；
- [ ] P07-A02：corrupt/missing/stale snapshot fail closed并回退strict；
- [ ] P07-A03：snapshot不成为第二head/authority；
- [ ] P07-A04：reachability可解释每个live/candidate object；
- [ ] P07-A05：roots包含head/prefix、epoch/ownership、active FWO、PFT winner/loser grace、capsule、snapshot、response-loss和pins；
- [ ] P07-A06：unknown/quarantine object不被listing omission误删；
- [ ] P07-A07：GC默认dry-run，apply有namespace+approval token；
- [ ] P07-A08：concurrent GC/commit/prepare/reconfigure/restore/capsule零live deletion；
- [ ] P07-A09：delete response-loss和partial batch以request identity幂等恢复；
- [ ] P07-A10：payload-before-marker与late old-membership-revision PFT有明确grace；
- [ ] P07-A11：same-digest loser和divergent blocker evidence retention不同且可审计；
- [ ] P07-A12：restorable iterator/RNG/optimizer/scheduler/scaler contract通过，synthetic learner capsule在同backend exact tiny continuation通过；
- [ ] P07-A13：缺失inner/RNG/data state时不误称exact；
- [ ] P07-A14：capsule publication/response-loss/session rules通过；
- [ ] P07-A15：空local目录restore与owner reassignment成功；
- [ ] P07-A16：lifecycle CLI不shadow现有`fs_diloco.cli`；
- [ ] P07-A17：D1/D2 lifecycle fault tests通过；
- [ ] P07-A18：按P07.1→P07.5子门完成后，D8-R2 50×10 terminal同时完成snapshot/replay/capsule/GC dry-run断言；
- [ ] P07-A19：accelerated soak显示bounded steady-state或明确BLOCKED；
- [ ] P07-A20：GC后从至少两个live restore points恢复并继续commit；
- [ ] P07-A21：lifecycle overhead、object count、bytes、ops和GPU impact有raw data；
- [ ] P07-A22：active surface无SQLite/embedded DB；
- [ ] P07-A23：Checker独立审核roots并执行一个未列并发反例；
- [ ] P07-A24：report/checksums/clean commit和P08 integration interface一致。

## 9. 验证矩阵

| 层级 | 必需验证 |
|---|---|
| local | replay equivalence、graph/property、GC race、capsule fault tests |
| D1 | snapshot/capsule/restore真实小步 |
| D2-R2 | owner/committer failure并发lifecycle |
| D8-R2 | 50×10 + accelerated soak + dry-run GC |
| destructive | 仅synthetic/approved namespace，restore-after-apply |

## 10. Maker–Checker与自动推进

Maker提交root schema、object inventory、GC plans、capsule traces和D8-R2 evidence。Checker必须从raw store inventory独立重建部分graph并尝试删除一个看似orphan但仍被late response-loss或loser grace引用的对象。

P07完成后把冻结的object identity、snapshot/reachability、capsule和GC integration contract
交给P08。P08从P07 verified commit顺序启动；P10只依赖最终P08 verified commit及其对P07
regression的Checker证据。

## 11. 可复制给Codex的启动指令

```text
从P06C verified commit执行P07。严格按P07.1 replay-only→P07.2 dry-run→P07.3 synthetic apply→P07.4 capsule→P07.5 distributed integration推进。为D8/D8-R2对象图实现snapshot+suffix、distributed reachability、default-dry-run GC、acks和exact learner capsules。FWO、PFT winner/loser、membership/ownership和response-loss evidence必须成为roots/grace。不要改optimizer/ownership语义，不要在真实namespace自动apply。Checker通过后把冻结接口交给P08。
```
