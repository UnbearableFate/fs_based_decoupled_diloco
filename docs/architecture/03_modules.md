# Module Guide / 模块说明

**EN** — This is a complete map of `fs_diloco/` (≈28k lines). Modules are grouped by layer,
bottom-up: storage → protocol → log → coordination → distributed syncer → learner → supporting.
For each module: what it does and what it must never do.

**中文** — 本文是 `fs_diloco/`（约 2.8 万行）的完整地图，按层自底向上分组：存储 → 协议 →
日志 → 协调 → 分布式 syncer → learner → 支撑模块。每个模块说明"做什么"与"绝不允许做什么"。

## 1. Storage layer / 存储层 — `fs_diloco/storage/`

| Module | EN | 中文 |
|---|---|---|
| `base.py` | Semantic storage API shared by memory/POSIX/future object backends: immutable create, conditional replace, verified get/head, range read, prefix listing, batch delete. | 各后端共享的语义存储 API：不可变创建、条件替换、校验读取/头部、范围读、前缀列举、批量删除。 |
| `posix.py` | The production backend. Every visible file is a checksummed envelope (magic, header digest, header JSON, payload). Mutations use per-key advisory `flock`, same-dir temp file, fsync, `link`/`replace`, parent-dir fsync. Random opaque versions defeat ABA; request IDs make lost-response retries idempotent. V2 envelopes carry per-64MiB chunk digests enabling verified range reads. | 生产后端。每个可见文件都是带校验和的 envelope（magic、header digest、header JSON、payload）。修改使用按 key 的 advisory `flock`、同目录临时文件、fsync、`link`/`replace`、父目录 fsync。随机不透明版本防 ABA；request ID 使响应丢失重试幂等。V2 envelope 携带每 64MiB 分块 digest，支持可校验范围读。 |
| `layout.py` | Canonical key validation: rejects absolute paths, `..`/`.`, backslash, control chars, the reserved lock namespace. | canonical key 校验：拒绝绝对路径、`..`/`.`、反斜杠、控制字符与保留锁命名空间。 |
| `memory.py` | Deterministic in-memory backend for the reference model and tests. | 参考模型与测试用的确定性内存后端。 |
| `fault_injection.py` | Wraps any backend with deterministic, replayable faults (timeouts, crashes at staged points). | 用确定性、可重放的故障（超时、阶段性崩溃点）包装任意后端。 |
| `capability_probe.py` | Fail-closed probe + CLI: filesystem type, Lustre flock scope, atomic replace, directory fsync, CAS race behavior, cross-node lock evidence. Authority roots refuse to open without proven cross-node locking. | 失败即关闭的探测器与 CLI：文件系统类型、Lustre flock 作用域、原子替换、目录 fsync、CAS 竞争行为、跨节点锁证据。未证明跨节点排他时权威根拒绝打开。 |
| `miyabi_contract_worker.py` | Two-rank Lustre CAS/visibility contract worker for PBS validation. | PBS 验证用双 rank Lustre CAS/可见性契约 worker。 |
| `errors.py`, `object_ref.py` | Typed error taxonomy (NotFound / ImmutableConflict / PreconditionFailed / IntegrityError / LockTimeout / CapabilityError / StorageIOError); canonical `(key, sha256, size)` reference type. | 类型化错误分类；canonical `(key, sha256, size)` 引用类型。 |

## 2. Protocol layer / 协议层 — `fs_diloco/protocol/`

| Module | EN | 中文 |
|---|---|---|
| `canonical_json.py` | Canonical identity encoding: NFC strings, sorted keys, no floats (numeric values travel as hex strings), duplicate keys rejected. All content IDs are SHA-256 of canonical bytes. | canonical identity 编码：NFC 字符串、排序键、禁止 float（数值以 hex 字符串传输）、拒绝重复键。所有 content ID 都是 canonical 字节的 SHA-256。 |
| `schemas.py` | Strict typed schemas for every v2 object: HeadManifest, CommitManifest, ControlCommitManifest, FrontierManifest, ProposalManifest, MembershipProjection, SnapshotProjection, ObjectRef… Unknown fields, bad enums, NaN/Inf are rejected. | 全部 v2 对象的严格类型化 schema；未知字段、非法 enum、NaN/Inf 一律拒绝。 |
| `identities.py` | Computes commit IDs / frontier digests from canonical bodies minus their own ID fields. | 从去掉自身 ID 字段的 canonical body 计算 commit ID / frontier digest。 |
| `validation.py` | The layered proposal validation pipeline: schema → run contract → lineage → causal base/staleness → namespace/ObjectRef → safetensors structure → finite-value scan. | 分层 proposal 验证管线：schema → 运行契约 → lineage → 因果 base/staleness → 命名空间/ObjectRef → safetensors 结构 → 有限值扫描。 |
| `safetensors_validation.py` | Dependency-free safetensors header/shape/dtype/offset/finite checks. | 无依赖的 safetensors 头/形状/dtype/offset/有限值检查。 |
| `work_order_v1.py`, `work_order_v2.py` | Canonical FWO schema; v2 adds primary/backup owners and the redundancy policy. | canonical FWO schema；v2 增加 primary/backup owner 与冗余策略。 |
| `prepared_transition_v1.py` | PFR + attempt-envelope schemas. | PFR 与 attempt envelope schema。 |
| `manifests.py`, `quarantine.py`, `errors.py`, `invariants.py`, `v1_adapter.py`, `__main__.py` | Strict manifest loading; idempotent quarantine records for invalid inputs; typed reports; read-only legacy v1 parsing; CLI manifest inspector. | 严格 manifest 加载；无效输入的幂等 quarantine 记录；类型化报告；只读 v1 解析；CLI manifest 检查器。 |

## 3. Transaction log / 事务日志 — `fs_diloco/log/`

| Module | EN | 中文 |
|---|---|---|
| `commit.py` | `TransactionalLog`: genesis initialization, head load, prepare-transition (publish params/outer/commit/frontier as immutable objects), then `commit_prepared` = one head CAS with request-ID resolution of ambiguous outcomes. Contains the reference (small-vector) path. | `TransactionalLog`：genesis 初始化、head 读取、prepare-transition（把 params/outer/commit/frontier 发布为不可变对象），然后 `commit_prepared` = 一次 head CAS，并用 request ID 消解歧义结果。含参考（小向量）路径。 |
| `production.py` | `ProductionTransactionalLog`: the safetensors tensor adapter. Adds fenced control transitions (epoch_bump / stop / resume / membership / snapshot_pin), owner-token activation, the process-local verified-object replay cache with strict invalidation rules, and distributed work-order binding on optimizer commits. | `ProductionTransactionalLog`：safetensors 张量适配器。增加 fenced 控制事务（epoch_bump / stop / resume / membership / snapshot_pin）、owner token 激活、带严格失效规则的进程内已验证对象 replay 缓存，以及 optimizer 提交上的分布式 work-order 绑定。 |
| `replay.py` | Strict replay: verify head → walk parent chain to genesis → check every commit/frontier/proposal/weight/consumption/membership/control rule → produce `ReplayResult` with reachable keys and the committed state digest. Also snapshot+suffix replay with equality audit, and orphan inspection. | strict replay：校验 head → 沿 parent 链回溯 genesis → 检查每条 commit/frontier/proposal/权重/消费/membership/控制规则 → 产出含可达键与已提交状态 digest 的 `ReplayResult`。另含 snapshot+suffix replay（含相等性审计）与孤儿检查。 |
| `snapshot.py` | Immutable, head-anchored snapshot manifests embedding verified objects. | 不可变、锚定 head 的 snapshot manifest，内嵌已验证对象。 |
| `reachability.py`, `gc.py`, `pins.py`, `acknowledgements.py` | Explainable object-graph reachability; immutable GC marks; guarded idempotent apply (real namespaces are dry-run only); lifecycle pins and role-scoped acks. | 可解释对象图可达性；不可变 GC mark；受保护的幂等 apply（真实命名空间仅 dry-run）；lifecycle pin 与按角色的确认。 |
| `codec.py`, `production_codec.py` | Canonical payload codecs, `verified_get` (ObjectRef-checked reads), safetensors encode/decode for params & outer state. | canonical payload 编解码、`verified_get`（按 ObjectRef 校验的读取）、params 与 outer state 的 safetensors 编解码。 |
| `layout.py`, `run.py`, `frontier.py`, `model.py`, `errors.py`, `verify.py`, `inspect_cli.py`, `bootstrap.py`, `training_probe.py`, `miyabi_worker.py`, `m00_miyabi_worker.py` | Logical key layout; frozen RunSpec/RunManifest; reference transition oracle; typed errors; verification entry points; `python -m fs_diloco.log.inspect_cli verify/replay/orphans`; warm start into a fresh generation; PBS contract workers. | 逻辑键布局；冻结的 RunSpec/RunManifest；参考 transition oracle；类型化错误；验证入口；inspect CLI；跨 generation warm start；PBS 契约 worker。 |

## 4. Coordination / 协调 — `fs_diloco/coordination/`

| Module | EN | 中文 |
|---|---|---|
| `lease.py` | `LeaseManager`: acquire/renew/release on one conditional storage object. Takeover requires `now ≥ expires_at + max_skew`; a renewed lease never changes the proposed epoch; every mutation carries a request identity for idempotent retry. | `LeaseManager`：在单个条件存储对象上执行 acquire/renew/release。接管要求 `now ≥ expires_at + max_skew`；续租不改变提议 epoch；每次变更携带 request identity 以支持幂等重试。 |
| `state_machine.py` | Dependency-free reference state machine for lease/fencing used by tests and model checking; defines `OwnerToken`. | 供测试与模型检查使用的无依赖 lease/fencing 参考状态机；定义 `OwnerToken`。 |
| `miyabi_worker.py`, `terminal_probe.py` | Two-node PBS takeover contract worker; terminal takeover assertions. | 双节点 PBS 接管契约 worker；终局接管断言。 |

## 5. Distributed syncer / 分布式 syncer — `fs_diloco/distributed_syncer/`

| Module | EN | 中文 |
|---|---|---|
| `committer.py` | The floating committer main loop (see architecture doc): fence → scan → select → FWO → wait PFR → validate → prepare → CAS → materialize; plus periodic lifecycle cycles, membership reconfiguration, terminal snapshot/strict audit, and stop finalization. Long substages run in a worker thread while the main thread keeps renewing the lease. | floating committer 主循环（见架构文档）：fence → 扫描 → 选择 → FWO → 等待 PFR → 验证 → prepare → CAS → 物化；外加周期性 lifecycle、membership 重构、终局 snapshot/strict 审计与停止收尾。长子阶段在 worker 线程中运行，主线程持续续租。 |
| `executor.py` | The LFE kernel: verify backend identity, streaming reduce, outer step, publish PFR + attempt envelope; enforces a declared CPU/RSS budget. | LFE 内核：校验后端 identity、流式归约、outer 步骤、发布 PFR 与 attempt envelope；执行声明的 CPU/RSS 预算。 |
| `ownership.py`, `membership.py` | Rendezvous-hash owner derivation; strict committed membership values (deliberately no heartbeats). | rendezvous 哈希推导 owner；严格的已提交 membership 值（刻意不含 heartbeat）。 |
| `hedge_policy.py`, `duplicate_validation.py` | Replayable redundancy policy (warm_standby/active_active/hedged); the pure decision kernel that fails closed on divergent duplicate results. | 可重放冗余策略（warm_standby/active_active/hedged）；对分歧重复结果失败即关闭的纯决策内核。 |
| `work_order_store.py`, `input_bundle.py`, `prepared_store.py` | Marker-last publication + strict loading of FWO, input bundles, and PFR attempts. | FWO、input bundle 与 PFR attempt 的 marker-last 发布与严格加载。 |
| `failure_evidence.py`, `reconfiguration.py` | Observational failure evidence (no direct authority); the derived membership-removal request the committer consumes. | 观测性故障证据（无直接权威）；committer 消费的派生 membership 移除请求。 |
| `bootstrap.py`, `cli.py`, `layout.py`, `scanner.py`, `prefetch.py`, `topology_manifest.py` | Distributed RunSpec factory; role CLI; distributed key layout; observation cursor; disposable owner-scoped prefetch; auditable role placement manifest. | 分布式 RunSpec 工厂；角色 CLI；分布式键布局；观察游标；可丢弃的 owner 范围预取；可审计角色布置 manifest。 |

## 6. Learner protocol & learner / learner 协议与进程

| Module | EN | 中文 |
|---|---|---|
| `learner_protocol/interval.py` | Immutable `ContributionInterval`: frozen base identity + step/token/cursor accounting. | 不可变 `ContributionInterval`：冻结的 base identity 与步数/token/游标记账。 |
| `learner_protocol/publication.py` | Marker-last learner publication with durable request identity (`LearnerPublisher`). | 带持久 request identity 的 marker-last learner 发布。 |
| `learner_protocol/session.py`, `adoption.py`, `data_cursor.py`, `rng_state.py` | Session identity + monotonic sequences; boundary-only adoption kernel with inner-optimizer policies (`reset_all` / `reset_updated_fragment` / `preserve`); warm-recovery data/RNG cursors. | session identity 与单调序列；仅在边界生效的采用内核及 inner-optimizer 策略；warm 恢复的数据/RNG 游标。 |
| `learner_protocol/recovery.py`, `exact_recovery.py`, `capsule.py`, `terminal_probe.py` | Warm recovery from immutable publication facts; exact capsule capture/restore of complete private state; PBS probes. | 基于不可变发布事实的 warm 恢复；exact capsule 对完整私有状态的捕获/恢复；PBS 探针。 |
| `learner.py` | The GPU learner process: adoption, inner training loop, heartbeats, proposal publication, warm/exact recovery entry, plus the legacy full-vector mode. | GPU learner 进程：采用、内层训练循环、heartbeat、proposal 发布、warm/exact 恢复入口，及遗留全向量模式。 |

## 7. Numeric & data plane / 数值与数据面

| Module | EN | 中文 |
|---|---|---|
| `optimizer/streaming_reduce.py` | O(fragment) ordered weighted left-fold reduction with bounded prefetch. | 有界预取的 O(fragment) 有序加权左折叠归约。 |
| `optimizer/reference_adapter.py`, `fragment_access.py` | Adapter over the frozen standard-library optimizer oracle; direct fragment gather/scatter. | 冻结标准库优化器 oracle 的适配器；fragment 直接 gather/scatter。 |
| `outer_optim.py`, `merge.py` | Flat-vector SGD / momentum / Nesterov / AdamW-style outer optimizers; token/staleness weighting (frozen `lambda=0.2`). | 平铺向量 SGD/momentum/Nesterov/AdamW 风格 outer 优化器；token/staleness 加权（冻结 `lambda=0.2`）。 |
| `syncer_core/` | Pure kernels shared by the central and distributed paths: planning/selection, aggregation, transaction-attempt builder, semantic digests, prepare-only facade. | 中心与分布式路径共享的纯内核：规划/选择、聚合、事务尝试构造、语义 digest、仅 prepare 的 facade。 |
| `param_index.py`, `fragment_index.py`, `fragment_scheduler.py`, `fragment_codec.py`, `tensor_codec.py` | Deterministic parameter indexing/flattening; balanced fragment layout; `round_robin_global` schedule; safetensors codecs. | 确定性参数索引/平铺；均衡 fragment 布局；`round_robin_global` 调度；safetensors 编解码。 |
| `proposal_catalog.py` | Re-entrant proposal discovery over non-authoritative listings: cheap metadata rejection first, then full payload validation with per-scope memoized validation tokens; quarantine of malformed inputs. | 基于非权威列举的可重入 proposal 发现：先廉价元数据过滤，再全量 payload 验证（按 scope 记忆化验证 token）；畸形输入进 quarantine。 |
| `hf_model.py`, `hf_data.py` | HF model/tokenizer construction (plus tiny synthetic smoke model); dataset loading and infinite per-learner batch iterators. | HF 模型/tokenizer 构建（含微型合成 smoke 模型）；数据集加载与按 learner 切分的无限批迭代器。 |

## 8. Supporting / 支撑

| Module | EN | 中文 |
|---|---|---|
| `config.py` | YAML config + validation (quorum, lease TTL/renew/margin/skew relations, grace-window vs lease budget). | YAML 配置与校验（quorum、lease TTL/续租/裕量/偏差关系、grace window 与 lease 预算约束）。 |
| `runtime_view.py` | Immutable `RuntimeView` rebuilt only from committed replay. | 只从已提交 replay 重建的不可变 `RuntimeView`。 |
| `telemetry/` | Observational stage recorder (async JSONL), strict event schema, fail-closed summary reducers, topology metrics, interference comparison, bundle-trigger gate. Never authority. | 观测性阶段记录器（异步 JSONL）、严格事件 schema、失败即关闭的汇总归约、拓扑指标、干扰对比、bundle 触发门。永非权威。 |
| `testing/` | Deterministic reference simulator, seeded model checker with deliberate safety mutants, crash-point enumeration, trace replay/minimization, numeric oracles. | 确定性参考模拟器、带蓄意安全变异体的种子化模型检查器、崩溃点枚举、trace 重放/最小化、数值 oracle。 |
| `paths.py`, `atomic_io.py`, `logging_utils.py`, `metrics.py`, `retention.py`, `liveness.py`, `failure_sim.py`, `analysis.py`, `eval_lm_harness.py`, `wandb_logging.py`, `lifecycle_cli.py`, `cli.py`, `constants.py` | Run-dir layout; atomic derived-file writes; JSONL logging; CSV metrics; local retention; heartbeat-derived liveness views; failure simulation knobs; deterministic run analysis; LM-eval export; W&B; lifecycle CLI; command dispatcher; constants. | 运行目录布局；派生文件原子写；JSONL 日志；CSV 指标；本地保留策略；基于 heartbeat 的活性视图；故障模拟开关；确定性运行分析；LM-eval 导出；W&B；lifecycle CLI；命令分发器；常量。 |

## Tests & scripts / 测试与脚本

**EN** — `tests/` mirrors the layers: `protocol/` (canonical JSON, identities, validation
matrix, golden manifests), `log/` (happy path, CAS conflict, crash matrix, replay prefix,
production runtime), `coordination/` (fencing), `distributed_syncer/` (topology, ownership,
duplicate equivalence, hedged execution, membership), `lifecycle/` (snapshot+suffix, GC
concurrency, capsule roundtrip, restore-after-GC), `reference/` (oracle transitions, double
inclusion, crash prefixes, model-checker mutants), plus `performance_core/` and
`syncer_decomposition/`. `scripts/miyabi/` holds PBS launchers/checkers, `scripts/agent/` static
contract checks runnable on login nodes, `scripts/chaos/` fault-injection helpers, and
`scripts/local/` smoke helpers for safe runtime environments.

**中文** — `tests/` 与分层一一对应：`protocol/`（canonical JSON、identity、验证矩阵、golden
manifest）、`log/`（正常路径、CAS 冲突、崩溃矩阵、replay 前缀、production 运行时）、
`coordination/`（fencing）、`distributed_syncer/`（拓扑、所有权、重复等价、hedged 执行、
membership）、`lifecycle/`（snapshot+suffix、GC 并发、capsule 往返、GC 后恢复）、`reference/`
（oracle 变换、重复纳入、崩溃前缀、模型检查变异体），另有 `performance_core/` 与
`syncer_decomposition/`。`scripts/miyabi/` 是 PBS 启动/检查脚本，`scripts/agent/` 是登录节点
可运行的静态契约检查，`scripts/chaos/` 是故障注入辅助，`scripts/local/` 是安全运行环境的
smoke 辅助脚本。
