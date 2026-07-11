---
plan_id: "P06A"
title: "Syncer Decomposition、Pure Kernels 与 Central Reference Equivalence"
status: "planned"
date: "2026-07-11"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "codex/duraloco-p06-learner-protocol"
planning_basis_commit: "06e3ca2299d5eb1a720c1d8f9107af5223095525"
verified_dependency_implementation: "2581a4d6286c7d0666f76aa3cc9d8122e66f6d25"
verified_dependency_checker_commit: "030129e045c4e5a2abb80eb100a0e28fb78d384d"
target_branch: "codex/duraloco-p06a-syncer-kernel"
depends_on:
  - "P06"
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
automatic_progression: true
next_phase: "P06B"
agent_decision_gates:
  - "模块边界、pure-kernel API和canonical semantic digest可由agent依据现有代码与oracle traces决定，经Checker复核。"
human_approval_gates: []
---

# P06A — Syncer Decomposition、Pure Kernels 与 Central Reference Equivalence

> 执行前读取根`AGENTS.md`、共同契约、两个系统设计、P06最终报告/Checker、
> `CURRENT_REPOSITORY_ALIGNMENT_REVIEW.md`、当前`STATE.yaml`与未关闭ADR。
> 当前P06 artifacts没有被A01–A20要求为完整CRS oracle trace bundle；P06A Loop 1必须
> 从archive tip建立该bundle，不能把它伪装成P06已经通过的gate。P06A不得改变生产拓扑：
> 所有authoritative commits仍由dedicated CRS完成。

## 1. 阶段使命

把当前集中在1100余行`fs_diloco/syncer.py`中的orchestration与仍内联的aggregation/
transaction-attempt glue拆成边界明确的模块，使data-plane计算可被CRS、未来LFE和offline
replay共同调用。不得重新实现仓库已经存在的`ProposalCatalog` selection、
`ProductionTransactionalLog` commit/replay、`outer_optim`、`optimizer.reference_adapter`、
`fragment_codec`、`fragment_index`、`param_index`或`RuntimeView`语义；应先为它们建立typed
adapter，再只抽取缺失的pure boundary。

本阶段只改变代码结构和可验证接口，不改变learner协议、selection semantics、scheduler order、lease/fencing、global head线性化点或C9生产拓扑。

### 1.1 研究主张

后续distributed route不是重新实现另一个optimizer，而是复用与CRS相同的selection、numeric和transition kernels；拓扑变化可以通过相同trace的digest equivalence独立验证。

### 1.2 完成后的系统增量

- `syncer.py`变为薄orchestrator；
- pure kernels不访问storage listing、wall clock、process identity或mutable globals；
- orchestration adapters显式注入storage、clock、lease和capabilities；
- P06 archive path、decomposed CRS与offline replay对P06A characterization traces等价；
- FWO/PFT schema以inactive形式冻结，但不启动LFE。

## 2. 前置条件

- [ ] 当前`plans/duraloco/STATE.yaml`、P06 report和Checker证明P06-A01–A20全部通过；
- [ ] P06 archive commit `06e3ca2`、verified implementation `2581a4d`和Checker commit `030129e`的角色已记录，P06A不从裸implementation commit丢失归档证据；
- [ ] P06A Loop 1将建立C1/C2/C9 characterization bundles；它们不是伪造的P06前置证据；
- [ ] P05 lease/fencing和head-CAS fault matrix可重跑；
- [ ] 当前clean commit、dependency digest和P06 report一致；
- [ ] 没有并行P07/P08 worktree修改shared syncer/log schemas。

## 3. 范围

### 3.1 必须完成

- [ ] 建立最小`syncer_core`或等价package，并保留现有public CLI；
- [ ] 复用`ProposalCatalog.scan/select`，只抽取其显式cutoff/planning输入或缺失pure policy；
- [ ] 抽取fragment/scheduler planning；
- [ ] 抽取streaming-compatible aggregation interface；
- [ ] 以`outer_optim.outer_optimizer_step`和`optimizer.reference_adapter`为既有数值实现/参考，不复制第三套outer optimizer；
- [ ] 抽取prepared transition semantic input builder，并继续由`ProductionTransactionalLog.prepare_transition/commit_prepared`唯一执行authority mutation；
- [ ] 只为现有log/replay/materialization调用建立薄adapter，不包装出第二套事务状态机；
- [ ] 为所有kernel定义typed input/output与canonical digest；
- [ ] immutable archive-checkout-vs-new differential harness；
- [ ] static/runtime capability audit；
- [ ] 预先冻结FWO/PFT schemas和versioning，不在production发布；
- [ ] CRS继续通过C1/C2/C9。

### 3.2 明确不做

- 不在learner节点启动executor；
- 不移动commit lease；
- 不引入overlapping ownership或membership epoch；
- 不并行处理多个authoritative transitions；
- 不优化性能到改变reduction order；
- 不删除CRS legacy adapter，直到P06B/P06C gates完成；
- 不实现per-fragment heads。

## 4. 预期仓库变更

```text
fs_diloco/syncer.py                         # thin CRS orchestrator
fs_diloco/syncer_core/
  types.py
  planning.py
  aggregation.py
  transaction_attempt.py
  semantic_digest.py
  capabilities.py
fs_diloco/protocol/
  work_order_v1.py                          # inactive schema
  prepared_transition_v1.py                 # inactive schema
tests/syncer_decomposition/
  test_oracle_trace_equivalence.py
  test_kernel_purity.py
  test_capability_surface.py
  test_old_new_differential.py
  test_fwo_pft_schema.py
```

实际目录可按现有仓库结构调整。优先扩展现有`proposal_catalog.py`、`log/production.py`、
`optimizer/`与`outer_optim.py`的typed接口；只有存在真实新边界时才增加文件。必须保留
“pure policy/numeric kernel”到“side-effect orchestration”的单向依赖，禁止为了目录
对称而复制现有实现。

## 5. 先冻结的设计决策

- [ ] D-06A01：kernel/module boundary与dependency direction；
- [ ] D-06A02：分别定义byte/content digest、state semantic digest和numeric comparison report，禁止用一个“semantic hash”掩盖浮点差异；
- [ ] D-06A03：同backend/同reduction order要求bitwise/content identity；跨CPU/GPU只允许声明的`atol/rtol`numeric equivalence并保留双方content digest；
- [ ] D-06A04：selection input中wall-clock/grace-window如何转成显式committed/planned fields；
- [ ] D-06A05：transition builder与commit adapter的边界；
- [ ] D-06A06：FWO/PFT schema version、unknown-field和canonical omission规则；
- [ ] D-06A07：CRS fallback adapter保留期限和deprecation gate；
- [ ] D-06A08：static capability scanner覆盖的imports、symbols和storage paths。

## 6. Codex执行循环

### Loop 1 — Characterization与red differential harness

**目标。** 在重构前固定当前CRS可观察语义。

**RED。** 在只读archive worktree `06e3ca2`运行characterization harness，生成golden
selected IDs、`float.hex` weights、aggregate bytes/content digest、parameter/outer-state
refs/content digests、frontier和transition identity；加入乱序listing、duplicate candidates、
stale base、grace边界和response-loss traces。不要修改或重新打标P06 artifacts。

**GREEN。** 建立只读characterization harness，不改production行为；trace同时记录
archive commit、run spec digest、payload codec、device/backend、Torch版本和reduction order。

**HARDEN。** 删除local cache、改变directory order、重启process，golden结果仍稳定；若现有代码暴露真正 nondeterminism，先写ADR并修复到P06 contract，而不是在新kernel复制缺陷。

**CHECK/PERSIST。** Checker抽取至少一个未列trace；保存old-path baseline和environment identity。

**停止条件。** 所有规范输入都有可重放expected output，未知差异被ADR解释。

### Loop 2 — Selection与planning pure kernels

**目标。** 把candidate validation、quorum/weight selection和fragment scheduling从I/O/orchestration中分离。

**RED。** 测试kernel若读取wall clock、directory order、global random、process ID或storage listing则失败；same canonical input必须same output。

**GREEN。** 输入显式包含parent/frontier、已由`ProposalCatalog`验证的candidate metadata、
cutoff/grace facts、scheduler state和policy identity；输出只包含selected proposals、
hex weights、fragment plan和diagnostics。不得重新读取payload或绕过现有causal validation。

**HARDEN。** adversarial order、duplicate object refs、unknown fields、canonical omission、epoch/head changes。

**CHECK/PERSIST。** 保存selection digest matrix和purity audit。

**停止条件。** CRS调用新kernel且P06 traces无变化。

### Loop 3 — Numeric aggregation与outer-step kernels

**目标。** 形成可由CRS/LFE共同调用的确定性fragment computation。

**RED。** full-vs-fragment、archive-vs-new、多dtype/layout、input order、momentum/Nesterov/AdamW state tests；parameter和outer state错误配对、outer-state `I64 step`被浮点allowlist拒绝或错误cast必须失败。

**GREEN。** typed validated inputs进入aggregation；outer step只接受显式parent fragment/state、aggregate和policy；输出parameter/state pair及digests。

**HARDEN。** NaN/Inf、corrupt payload、empty/insufficient quorum、overflow、bfloat16 transport/float32 accumulation、cancel mid-read。

**CHECK/PERSIST。** numeric oracle report、working-set和I/O计数基线。

**停止条件。** old/new numeric digests在contract内完全等价。

### Loop 4 — Transition/commit adapters与capability separation

**目标。** side effects显式化，为P06B prepare-only executor做准备。

**RED。** pure kernel import storage/lease/head-CAS时失败；模拟executor capability调用commit应fail closed；commit adapter绕过fencing或strict replay应失败。

**GREEN。** 建立transition builder、commit/recovery/materialization adapters；CRS orchestration依次调用pure kernels和authoritative adapter。

**HARDEN。** crash before/after immutable-object publication、CAS ambiguity、head jump、stale lease、response loss、corrupt successor。

**CHECK/PERSIST。** static import graph、runtime capability matrix、P05 regression evidence。

**停止条件。** `syncer.py`不再包含重复policy/numeric实现，authority路径仍唯一。

### Loop 5 — FWO/PFT inactive schemas与end-to-end equivalence

**目标。** 冻结P06B所需protocol objects，但不启用分散执行。

**RED。** same ID/conflicting content、unknown fields、missing implementation identity、parameter/state ref mismatch、stale parent/epoch schema tests。

**GREEN。** 实现canonical serialization/validation/digest；提供CRS trace到FWO/PFT的offline转换器，仅用于test/artifact。

**HARDEN。** forward/backward schema rejection、payload marker crash、content-address collisions simulation。

**CHECK/PERSIST。** 同一clean P06A implementation commit依次运行C1、C2、C9
decomposed CRS；与archive characterization逐字段比较并生成P06A handoff bundle。P06旧C9
只能作为baseline，不能替代改动后的production orchestration C9。

**停止条件。** production拓扑未变，decomposed CRS通过全部old gates和new equivalence gates。

## 7. 不变量与故障注入

- [ ] global head CAS仍是唯一线性化点；
- [ ] dedicated CRS仍是本阶段唯一committer；
- [ ] old and new paths不能在同generation双写；
- [ ] kernels无I/O、clock、lease和process-local authority；
- [ ] parameter/outer-state pair不可拆分；
- [ ] same canonical input产生same semantic digest；
- [ ] inactive FWO/PFT不能被learner adopt或GC误当committed；
- [ ] P05 takeover从empty-cache strict replay恢复。

故障注入覆盖：payload/marker crash、candidate order、CAS response loss、stale lease、head advance、partial materialization、kernel exception和process restart。

## 8. 验收标准

- [ ] P06A-A01：archive commit `06e3ca2`有只读old-path characterization baseline，且不改写P06 verdict；
- [ ] P06A-A02：selection/planning kernel纯度测试通过；
- [ ] P06A-A03：numeric/outer-step kernels对全部P06 traces等价；
- [ ] P06A-A04：parameter/outer-state pair mismatch fail closed；
- [ ] P06A-A05：content digest、state semantic digest、same-backend exact与cross-backend tolerance contract分别写入ADR/schema；
- [ ] P06A-A06：`syncer.py`成为薄orchestrator，无重复selection/outer-step policy；
- [ ] P06A-A07：现有`ProductionTransactionalLog`/lease/replay/materialization边界明确且没有第二事务实现；
- [ ] P06A-A08：static import audit证明pure kernels无side-effect dependency；
- [ ] P06A-A09：runtime test证明受限prepare facade没有head key/conditional_replace，static audit防止LFE production modules误引authority API；报告明确这不是同Unix账号下的Byzantine sandbox；
- [ ] P06A-A10：FWO/PFT v1 canonical validation、same-ID conflict、unknown-field tests通过；
- [ ] P06A-A11：P05 lease/fencing/takeover/CAS ambiguity regression通过；
- [ ] P06A-A12：C1 ≤10-step real path通过；
- [ ] P06A-A13：C2 failover path通过；
- [ ] P06A-A14：修改production orchestration后的同一clean implementation commit按C1→C2→C9通过50×10 terminal；旧P06 run仅作baseline；
- [ ] P06A-A15：old/decomposed CRS selected/aggregate/parameter/outer-state/transition digests一致；
- [ ] P06A-A16：删除所有local cache后strict replay结果一致；
- [ ] P06A-A17：active surface仍无SQLite/embedded DB；
- [ ] P06A-A18：本阶段没有learner-hosted executor、membership/ownership mutation或第二authority；
- [ ] P06A-A19：双语report、checker、manifest、checksums和clean commit一致；
- [ ] P06A-A20：`STATE.yaml.next_action=P06B`并记录archive baseline、kernel/schema、numeric backend与trace bundle digests。

## 9. 验证矩阵

| 层级 | 必需验证 |
|---|---|
| local | purity、schema、differential、numeric、capability、fault/property tests |
| C1 | decomposed CRS + learner真实小步 |
| C2 | CRS lease/fencing/takeover regression |
| C9 | matched central reference terminal/equivalence |
| static | import graph、authority/capability、SQLite scan、master/checksum |

## 10. Maker–Checker交接

Maker提交diff、module map、oracle comparison、capability audit、C1/C2/C9 manifests和每个acceptance evidence。Checker必须从旧`syncer.py`反查是否仍有隐藏policy或head mutation，并手工构造一个same-input divergent environment反例。

## 11. 自动推进

全部A01–A20通过后自动创建P06B分支。不得先实现redundancy，也不得删除CRS。若equivalence不能成立，停留P06A并修复/记录numeric contract，不能用“distributed path更合理”绕过。

## 12. 可复制给Codex的启动指令

```text
使用miyabi-development skill执行P06A。基线为P06最终verified commit。先读取P06 oracle traces、共同契约和DISTRIBUTED_SYNCER_SYSTEM_DESIGN.md。只做syncer decomposition和central reference equivalence，不改变生产拓扑，不启动learner-hosted executor。按Loop 1→5建立red differential evidence、pure kernels、side-effect adapters、inactive FWO/PFT schemas和C1/C2/C9等价。全部gate通过后将next_action设为P06B；不要启动P07/P08或删除CRS。
```
