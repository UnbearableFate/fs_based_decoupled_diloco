---
plan_id: "P08"
title: "Distributed Performance Core：Direct Fragment I/O、Streaming Reducer、Bundling 与 Telemetry"
status: "ready"
date: "2026-07-12"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/duraloco-p07-distributed-lifecycle"
planning_basis_commit: "c099adc3c3a99127569a7d9bf38a58547022173c"
planning_basis_runtime_commit: "2295467fd25ae7969eb2b993ef4b193141239286"
planning_basis_report_job: "2368976.opbs"
planning_basis_checker_job: "2369002.opbs"
target_branch: "codex/duraloco-p08-distributed-performance"
depends_on:
  - "P07"
required_skill: "miyabi-development"
execution_mode: "single-writer implementation on P07 verified contract + independent checker"
automatic_progression: true
next_phase: "P10"
agent_decision_gates:
  - "是否启用multi-FWO preparation和one-CAS bundle由profile、serial-equivalence和failure evidence决定；无瓶颈时保留单FWO路径。"
  - "CUDA/C++ extension、tensor layout或precision改变必须有profile、numeric equivalence和fallback。"
human_approval_gates: []
---

# P08 — Distributed Performance Core：Direct Fragment I/O、Streaming Reducer、Bundling 与 Telemetry

## 0. 2026-07-12 启动就绪更新

P07 已由独立 Checker 验证完成，因此 P08 可从
`c099adc3c3a99127569a7d9bf38a58547022173c` 顺序启动。当前 evidence baseline 为：

- factor-one D8：P06B 470 秒；
- hedged D8-R2：P06C 528 秒，input/output 分别为 factor-one 的 1.77×/1.90×；
- lifecycle D8-R2：P07 1100 秒，后期单 cycle lifecycle latency 从 45.58 秒增长至
  141.89 秒，effective-live tail delta 56（上限 64）；
- P07 runtime/report/checker：`2295467`、PBS `2368976`、PBS `2369002`。

P08 必须保留 P07 的 single-head authority、empty-cache strict fallback、two-snapshot
retention、typed reachability、unknown quarantine、guarded GC、exact capsule、marker-last
ordering 与 long-substage lease heartbeat。performance cache、scanner cursor、validation token、
prefetch 与 telemetry 仍必须可删除，且不能成为 authority。

第一个执行 loop 是 profile-first：先冻结 matched C9/D8/D8-R2 workload 与 stage schema，
用 targeted one-node benchmark 建立 direct/legacy fragment access、copy bytes、read/SHA/
finite-check count、peak RSS 和 lifecycle scan breakdown，再依次运行 D1 与 D2。只有 profile
证明 single-FWO/head serialization 达到预注册 bottleneck threshold，才允许设计新 generation
的 bundle；否则 P08-A16–A18 以 Checker 认可的 `not_applicable` 关闭。

## 1. 阶段使命

优化learner-hosted LFE和Floating Committer的关键路径，使工作内存、copy和I/O接近fragment scope；建立可重建publish→plan→prepare→commit→adopt全链路的telemetry；量化并限制LFE对learner GPU的CPU、NUMA、memory bandwidth和Lustre干扰。只有证据表明single-FWO/head serialization成为瓶颈时，才实现bounded concurrent prepare和one-CAS `CommitBundlePlan`。

### 1.1 研究主张

D8/D8-R2的性能不是由prototype whole-model copy、q×fragment驻留或无界metadata scan主导；分散syncer可在复用learner CPU的同时保持可接受GPU goodput，并将冗余/共享存储成本精确归因。

### 1.2 完成后的系统增量

- direct fragment gather/scatter；
- O(fragment) streaming weighted reducer；
- bounded prefetch/scanner/object validation reuse；
- LFE CPU/NUMA/resource controller；
- structured stage telemetry；
- 可选bounded multi-FWO prepare + serial-equivalent one-CAS bundle；
- D8/D8-R2 matched performance reports。

## 2. 前置条件

- [x] P07-A01–A24通过，P06C distributed correctness仍为其verified dependency；
- [x] factor1和R2 raw latency/resource baseline存在；
- [x] CRS/LFE numeric equivalence harness可重跑；
- [x] P07 verified commit的object identity/lifecycle接口冻结；
- [ ] profiler不改变authority或timing-sensitive selection semantics。

## 3. 范围

### 3.1 必须完成

- [ ] parameter-index direct gather/scatter；
- [ ] streaming weighted reduce与deterministic order；
- [ ] bfloat16 transport/float32 accumulation合同；
- [ ] typed validation token在attempt内复用；
- [ ] bounded pinned CPU buffers、threads、RSS、prefetch和in-flight bytes；
- [ ] incremental proposal/FWO/PFT discovery，listing只discovery；
- [ ] epoch/head change cancellation与strict revalidation；
- [ ] stage-level telemetry和raw benchmark harness；
- [ ] CPU affinity/NUMA/GPU step interference experiments；
- [ ] factor1/R2 duplicate cost telemetry；
- [ ] central CRS vs distributed LFE matched profile；
- [ ] 如触发evidence gate：bounded concurrent prepare与CommitBundlePlan。

实现必须从当前已有`param_index.py`、`fragment_index.py`、`fragment_codec.py`、
`ProposalCatalog`的`ValidatedProductionPayload`和`ProductionTransactionalLog`扩展，不能
新建互不兼容的layout、scanner或validation truth。direct gather/scatter同时涉及learner
proposal publication和LFE parent loading；只优化LFE而仍让learner每次whole-model flatten
时，不得声称端到端copy已达到fragment scope。

### 3.2 明确不做

- 不默认实现per-fragment heads；
- 不让performance cache成为durable authority；
- 不以synthetic bandwidth代替D8 E2E；
- 不无证据手写CUDA kernel；
- 不改变selection/quorum/outer optimizer语义；
- 不通过降低validation、fsync、digest或fencing换性能；
- 不让prefetch跨epoch/head复用。

## 4. 预期仓库变更

```text
fs_diloco/optimizer/
  fragment_access.py
  streaming_reduce.py
  buffers.py
fs_diloco/distributed_syncer/
  scanner.py
  prefetch.py
  execution_budget.py
  bundle_plan.py              # only if gate triggers
  bundle_commit.py            # only if gate triggers
fs_diloco/telemetry/
  events.py
  recorder.py
  summaries.py
  topology_metrics.py
  interference.py
benchmarks/
  bench_fragment_access.py
  bench_streaming_reduce.py
  bench_lfe_pipeline.py
  bench_bundle_commit.py
scripts/miyabi/
  profile_d8.sh
  profile_d8_r2.sh
tests/performance_core/
  test_fragment_equivalence.py
  test_streaming_memory_bound.py
  test_validation_reuse.py
  test_epoch_cancellation.py
  test_bundle_serial_equivalence.py
```

## 5. 先冻结的设计决策

- [ ] D-0801：fragment layout cache和canonical layout identity；
- [ ] D-0802：reduction order、accumulation dtype和deterministic mode；
- [ ] D-0803：LFE core affinity、NUMA、thread/RSS/I/O budgets；
- [ ] D-0804：typed validation token lifetime和invalidations；
- [ ] D-0805：scanner cursor是否仅process-local；必须可从storage重建；
- [ ] D-0806：telemetry event schema、clock synchronization和sampling overhead；
- [ ] D-0807：multi-FWO trigger thresholds与maximum speculative window；
- [ ] D-0808：bundle canonical fragment order、parent、proposal consumption和serial-equivalence proof；
- [ ] D-0809：bundle failure/cancellation/lifecycle interface；
- [ ] D-0810：性能claim的matched topology/resource accounting。

`CommitBundlePlan`不是默认scope。只有Loop 5 profile明确证明single-FWO/head serialization
是主瓶颈、且预计收益超过预注册阈值时，才新增bundle schema。由于bundle会改变
commit/frontier/replay/reachability identity，它需要新ADR、protocol/run-generation兼容策略
和P07 lifecycle extension；不能作为当前generation的透明优化。

## 6. Codex执行循环

### Loop 1 — Distributed critical-path baseline

**目标。** 量化D8/D8-R2每段延迟、copy、RSS、object ops和GPU interference。

**RED。** metric缺stage、role、epoch/FWO/transition identity、topology/resource allocation时分析fail closed；固定相同commit/config的C9/D8/D8-R2 baseline。

**GREEN。** 记录discovery、validation、read、reduce、outer step、object publication、PFT visibility、winner validation、coordination、CAS、materialization和adoption。

**HARDEN。** telemetry writer crash/lag不得影响training；clock skew使用monotonic local spans+causal IDs，不伪造global精确时钟。

**CHECK/PERSIST。** raw JSONL/manifests、environment、CPU/GPU/Lustre counters。

**停止条件。** 能从raw events重建每个committed transition和loser attempt timeline。

### Loop 2 — Direct fragment access与buffer isolation

**目标。** 避免whole-model flatten/scatter和不相关parameter clones。

**RED。** legacy/direct在多layout/dtype、updated/unupdated fragments、optimizer-state mapping下对照；copy bytes和RSS assertions。

**GREEN。** 扩展现有param/fragment index与codec，提供cached canonical layout、targeted
gather/scatter、bounded pinned buffers和explicit ownership/lifetime；保持public learner和
current safetensors payload contract唯一。

**HARDEN。** non-contiguous tensors、shared parameters、mixed dtype、cancel/crash、learner同时训练、NUMA placement。

**CHECK/PERSIST。** numeric digests和copy/RSS profile。

**停止条件。** copy/I/O随fragment而非whole model增长，GPU learner状态未被错误修改。

### Loop 3 — Streaming reducer、validation reuse与prefetch

**目标。** 逐proposal累加，峰值working set不随quorum线性持有全部tensor。

**RED。** q、weights、order、staleness、corruption、response loss、epoch/head jump、same object repeated refs。

**GREEN。** typed validated input→streaming accumulator→release；bounded prefetch；same ObjectRef在attempt内read/SHA/finite-check一次；cheap rejection在payload I/O前。

**HARDEN。** midstream corrupt input、LFE/committer cancellation、old epoch token、slow Lustre和listing duplicate/omission。

**CHECK/PERSIST。** reference equivalence、object read counters和memory curve。

**停止条件。** peak working set接近O(fragment)，不以削弱validation换取。

### Loop 4 — LFE resource interference control

**目标。** 将sync workload吸收到learner CPU而不不可控地拖慢GPU。

**RED。** sweep cores/threads/NUMA/prefetch/RSS/hedge modes；记录GPU step time、CPU utilization和memory bandwidth proxy；超budget触发assertion。

**GREEN。** launch/config中显式resource budget；backpressure、priority/affinity和hedge suppression；manifest记录实际placement。

**HARDEN。** learner dataloader高CPU、LFE burst、R2 duplicate、whole-node degraded core、memory pressure。

**CHECK/PERSIST。** no-LFE shadow、factor1、R2 matched comparison。

**停止条件。** 选定默认预算有证据和guardrails，负trade-off被报告。

### Loop 5 — Bounded concurrency与bundle evidence gate

**目标。** 仅在single-FWO序列化显著限制goodput时提高prepare/commit并行度，同时保持一个global history。

**RED。** 先用trace/profile证明瓶颈；构造disjoint fragments、same fragment、proposal overlap、parent advance、one PFT failure和bundle response-loss traces。

**GREEN。** 若gate触发：多个FWO可从同parent bounded prepare；CommitBundlePlan固定ordered fragments和consumption；pure simulator证明与canonical serial application等价；一个final bundle transition和一次head CAS。

**HARDEN。** partial PFT set、stale member、duplicate results、bundle cancellation、large manifest、lifecycle roots。

**CHECK/PERSIST。** bundle-off/on D2/D8 benchmark和semantic digest comparison。若gate不触发，记录为何单FWO足够，并保留接口测试。

**停止条件。** bundle path有新generation/schema、serial-equivalence、P07 lifecycle和fault
proof；或profile gate未触发并由Checker将所有bundle acceptance标记为有证据的
`not_applicable`，且任何性能claim不依赖bundle。

### Loop 6 — D8/D8-R2 optimized acceptance

**目标。** 在最终clean commit重跑correctness、performance和interference gates。

**RED/GREEN。** D8 factor1与D8-R2 50×10，matched C9；至少一个executor/committer故障；收集raw stage profile。

**HARDEN。** head/epoch change取消prefetch；strict fallback；corrupt successor；telemetry缺失fail closed。

**CHECK/PERSIST。** P07 integration interface、报告、checksums和Checker。

**停止条件。** 优化路径不改变digests/invariants，性能数据可复现。

## 7. 不变量与失败注入

- [ ] optimized/reference/CRS共享policy/numeric semantics；
- [ ] validation/digest/fencing不能被性能开关关闭；
- [ ] cache/prefetch/cursor全可删除；
- [ ] head/epoch变化废弃旧tokens和prepared planning window；
- [ ] bundle仍只有一个global head CAS；
- [ ] bundle与canonical serial order等价；
- [ ] LFE resource budget优先保护learner GPU；
- [ ] telemetry不参与correctness。

## 8. 验收标准

- [ ] P08-A01：direct fragment access与legacy/reference等价；
- [ ] P08-A02：copy/I/O measurement接近fragment scope；
- [ ] P08-A03：streaming reducer与reference等价；
- [ ] P08-A04：peak working set不呈q×fragment旧线性驻留；
- [ ] P08-A05：typed validation在attempt内复用并有read/SHA/finite-check上界；
- [ ] P08-A06：cheap rejection先于payload I/O；
- [ ] P08-A07：scanner restart/duplicate/list omission不影响correctness；
- [ ] P08-A08：head/epoch jump取消prefetch/token并strict revalidate；
- [ ] P08-A09：每个commit/loser attempt可由telemetry重建全timeline；
- [ ] P08-A10：raw manifests/events保留fail/inconclusive/retry lineage；
- [ ] P08-A11：LFE CPU affinity/NUMA/RSS/threads/in-flight进入manifest并实际audit；
- [ ] P08-A12：GPU step time/interference有no-LFE、factor1、R2 matched data；
- [ ] P08-A13：bfloat16 transport/float32 accumulation合同不回归；
- [ ] P08-A14：same FWO primary/backup遵守冻结backend/thread/reduction identity并exact；改变可能影响numerics的resource setting必须形成不同implementation identity并走numeric comparison，不能冒充same FWO；
- [ ] P08-A15：single-FWO bottleneck evidence gate有明确结论；
- [ ] P08-A16：profile gate结论已归档；若启用bundle，new-generation CommitBundlePlan schema/canonical order通过，否则Checker接受`not_applicable`；
- [ ] P08-A17：若启用bundle，与serial transitions semantic/state digest等价且P07 reachability已扩展；否则`not_applicable`；
- [ ] P08-A18：若启用bundle，partial/crash/response-loss/duplicate tests通过；否则`not_applicable`；
- [ ] P08-A19：仍无per-fragment heads或第二authority；
- [ ] P08-A20：D1/D2 optimized correctness gates通过；
- [ ] P08-A21：D8 50×10 optimized terminal和raw profile通过；
- [ ] P08-A22：D8-R2 controlled fault optimized terminal通过；
- [ ] P08-A23：active surface/artifacts无SQLite/embedded DB；
- [ ] P08-A24：report/checksums/clean commit、P07 regression与lifecycle integration interface一致，`STATE.yaml.next_action=P10`。

## 9. Maker–Checker与自动推进

Checker必须验证benchmark不会把validation或fsync关闭，手工触发head jump使prefetch失效，
并核对PBS/affinity实际资源而非配置声明。P08必须在P07 verified commit上运行全部lifecycle
regressions；P08 Checker通过后进入P10。

## 10. 可复制给Codex的启动指令

```text
从P07 verified commit执行P08。扩展现有param/fragment codec、ProposalCatalog validated payload和production log接口，优化learner/LFE direct fragment I/O、streaming reducer、validation reuse、bounded prefetch和CPU/NUMA资源隔离；建立publish→prepare→commit→adopt telemetry。先profile再决定是否实现bounded multi-FWO/one-CAS bundle；未触发时以Checker认可的not_applicable关闭，触发时必须使用新schema/generation并与canonical serial order等价。保持single global head和全部validation/fencing。通过P07 regressions与P08 Checker后进入P10。
```
