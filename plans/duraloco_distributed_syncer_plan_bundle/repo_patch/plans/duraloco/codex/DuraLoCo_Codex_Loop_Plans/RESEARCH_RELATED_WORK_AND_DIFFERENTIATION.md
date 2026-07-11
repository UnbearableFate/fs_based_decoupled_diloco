---
title: "DuraLoCo Related Work and Differentiation"
version: "1.0"
date: "2026-07-11"
status: "research positioning; update before submission"
---

# DuraLoCo 与相关研究的差异、创新边界和证据计划

## 1. 定位结论

DuraLoCo 不应把“CPU syncer”“fragment sharding”“共享存储通信”“serverless/on-demand aggregation”“backup execution”或“logging/replay”中的任一项单独声明为首创。这些机制分别已有直接先例。

本项目更有研究价值的组合是：

> 将有状态、低频、fragment-wise outer optimizer 的权威状态放入共享存储中的 committed transition history；把原本持久的 syncer 服务改为 learner-hosted、可替换、可重复执行的 fragment tasks；允许 at-least-once prepare 和 overlapping ownership，同时通过 fenced single-head commit 保证 at-most-once logical inclusion 和 parameter/outer-state pair consistency。

截至 2026-07-11 的定向检索，没有发现一项工作同时覆盖上述全部组合。不过这只是当前相关工作调查结论，不应在论文中写“first”而不做更完整的系统性检索。

## 2. 相关研究矩阵

| 方向/代表工作 | 已覆盖的核心思想 | DuraLoCo 不应声称的新颖点 | DuraLoCo 的差异 |
|---|---|---|---|
| Decoupled DiLoCo | 异步 learners、minimum quorum、adaptive grace、token weighting、fragment-wise outer optimizer；syncer 在 CPU-only replicas 上分片；vector clocks、event tape、consistent checkpoint | fragment-wise sync、CPU-only/sharded syncer、异步 learner、本身的算法框架 | 原方案的 syncer worker/shards 是持续存在的 global model/outer-state holders；DuraLoCo 把权威状态移到 storage-resident committed log，并让 executor 进入 learner failure domain且可替换 |
| Parameter Server | parameter shards、异步 updates、elasticity、fault tolerance | sharded server、worker/server co-location、异步 parameter update | DuraLoCo 的更新是绑定 parent/quorum/outer-state 的低频 transition；server memory 不是 authority；owner change 不迁移 optimizer state |
| ZeRO/FSDP/CPU offload | optimizer/gradient/parameter state sharding；CPU 执行 optimizer compute | 把 optimizer 放 CPU、按参数切分状态 | DuraLoCo 不按每一步 collective；learner独立，outer transition低频且可重复 prepare；commit由 durable history裁决 |
| LambdaML/λ-FL | 使用外部存储/缓存在 serverless workers 间交换梯度；reduce/reduce-scatter | 共享存储代替 RPC | DuraLoCo 的存储对象构成 optimizer authority、recovery log 和 lifecycle graph，而非只作为通信中介 |
| LIFL、AdaFed | event-driven/on-demand、elastic serverless aggregation | 不保留 always-on aggregator、动态聚合资源 | DuraLoCo 使用已分配 learner 节点 CPU，并处理参数+有状态 outer optimizer 的成对 transition 与 committed ancestry |
| GradsSharding | 按模型/gradient 轴把聚合拆到独立 serverless functions；FedAvg element-wise sharding；per-function memory O(|θ|/M) | fragment mini-aggregator、serverless sharded aggregation | GradsSharding 主要是 stateless FedAvg shard aggregation；DuraLoCo 固定 parent、quorum、outer optimizer state、duplicate determinism、fencing 与 logical commit |
| Backup workers/speculative execution | 启动额外 worker、采用先完成结果以缓解 straggler | overlap/backup/hedged execution | DuraLoCo 冗余执行的是有因果依赖的 stateful optimizer transition；loser不能改变 consumption，divergent duplicate必须阻塞 |
| SWIFT 等训练恢复 | logging、replication、replay、failure recovery | 用日志恢复训练 | DuraLoCo 中 durable transition 不是辅助恢复日志；durable commit 本身定义正常执行的权威状态 |
| BatchWeave | client-side object-store-native data plane；immutable objects、versioned manifest/OCC、exactly-once batch semantics、checkpoint-aligned lifecycle、无 server-side process | immutable object + conditional manifest、无专用服务、storage-mediated commit/lifecycle | BatchWeave管理 training data batches，不执行 stateful outer optimizer；DuraLoCo 的 object graph包含proposal、参数、outer state、quorum、ownership、PFT和optimizer ancestry |
| FLStore/其他 FL storage | FL update storage、cache/locality、非训练任务 | data/compute plane 与存储集成 | DuraLoCo 关注 pretraining outer optimizer authority、learner-host co-failure 和 committed transition semantics |
| Eager/Streaming DiLoCo | fragment communication 与 local compute overlap | overlap communication/compute | DuraLoCo 研究执行角色、耐久 authority 和 failover，而不是只调整通信时序 |

## 3. 最接近的基线：Decoupled DiLoCo

原始 Decoupled DiLoCo 的系统已经：

- 将模型按 fragment 执行 outer optimization；
- 由 central syncer 异步聚合 learner；
- 将 syncer worker 分成 CPU-only shards；
- 让 learner暂时缺席时对应 syncer shard仍持续存在；
- 在 syncer 中维护 global parameters 与 outer optimizer state；
- 用 vector clocks、event logging/replay 和一致 checkpoint 支撑恢复。

因此 DuraLoCo 的关键对照不是“central unsharded syncer vs sharded syncer”，而是：

```text
persistent stateful syncer shards
              versus
storage-resident optimizer state machine
+ replaceable learner-hosted executors
```

研究问题应明确为：把 syncer 放入 learner failure domain 后，能否依靠 durable state、redundancy 和 fencing，消除专用稳定 syncer 资源而不损失正确性、goodput 和模型质量？

## 4. 最接近的 fragment 聚合工作：GradsSharding

GradsSharding 按 gradient tensor 轴切成 M 个 shards，每个 serverless function 从全部 clients 聚合一个 shard。因为 FedAvg 是 element-wise，论文能够主张与 tree-based full-gradient averaging bit-identical，并将单 function memory 限制到 O(|θ|/M)。

DuraLoCo 必须展示额外问题：

1. outer optimizer state 如 momentum/Adam moments 与 parameter fragment 成对演进；
2. 每个 transition 有 parent head 与 consumed proposal set；
3. 两个 replicas 可能在不同时间观察 proposals，因此由 FWO 预先固定 selection；
4. duplicate execution 不能导致 duplicate logical inclusion；
5. stale ownership/committer 被 fencing 拒绝；
6. committed prefix 是恢复接口；
7. learner adoption 只读取 final committed frontier。

论文中可用术语：**stateful optimizer-transition sharding**，与 GradsSharding 的 **stateless gradient-aggregation sharding** 区分。

## 5. 最接近的 storage-native control plane：BatchWeave

BatchWeave 说明：client-side producers 可以写 immutable objects，再通过 conditional manifest commit 实现 atomic visibility、consistent ordering、failure recovery 和 checkpoint-driven lifecycle，而无需 server-side dispatcher。它是 DuraLoCo 必须认真对照的近期工作。

差异不在 storage primitive，而在所线性化的语义：

- BatchWeave 线性化 training-ready global batches 和 producer offsets；
- DuraLoCo 线性化有状态 outer optimizer transitions，包括参数、outer state、quorum、consumption、ownership 和 numerical identity。

因此 DuraLoCo 不应声称“首次用 immutable objects + conditional commit 构建无服务训练数据面”。更稳妥的主张是：将类似 storage-native transactional pattern应用到 asynchronous low-communication pretraining 的 optimizer authority，并解决 learner-hosted redundant computation 的状态一致性。

## 6. 创新强度分层

### 较弱，不能单独作为主贡献

- 把 syncer 放到 CPU；
- 把模型/gradient/optimizer 分片；
- 用共享文件系统或 object store交换更新；
- 让聚合任务按需启动；
- 同一任务配置 backup/hedge；
- 用日志或 checkpoint恢复；
- 让 worker 和 aggregator 共置。

### 中等，需要系统化证据

- 在 HPC GPU learner 节点复用附带 CPU，消除专用 syncer node allocation；
- fragment owner 通过 committed membership epoch 和 rendezvous hashing 弹性变化；
- direct fragment I/O、streaming reducer 和 bounded CPU interference；
- single global head 下 distributed prepare 与 bundle commit。

### 较强，适合组成核心贡献

1. **Storage-resident outer optimizer authority**：任何 executor 内存都不是不可替代状态。
2. **Roleless/replaceable sync execution**：syncer从常驻服务变成 learner hosts 上的临时任务。
3. **Stateful FWO/PFT protocol**：固定 parent、selection、numeric identity，并把参数与 outer state成对准备。
4. **At-least-once execution with at-most-once logical commit**：冗余执行但唯一 proposal consumption/optimizer trajectory。
5. **Ownership migration without optimizer-state transfer**：新 owner只读取 committed parent，无 server replica promotion/state copy。
6. **Failure-domain inversion**：主动把 executor放入 learner co-failure domain，再用存储和冗余恢复。
7. **Communication/checkpoint/replay unification**：proposal和transition同时是通信对象、optimizer input、checkpoint ancestry与审计证据。

## 7. 建议研究问题

- **RQ1 Correctness**：在 executor、committer或 whole learner node任意 crash，重复 prepare和ownership切换下，是否保持 paired state、at-most-once logical inclusion和deterministic replay？
- **RQ2 Resource efficiency**：D8相对C9是否减少allocated node-hours/GPU-hours，同时保持learner GPU goodput？
- **RQ3 Performance**：fragment parallelism、streaming reduce和bundling是否抵消Lustre metadata/data开销？
- **RQ4 Fault tolerance**：D8-R2相对P05 active/standby syncer的RTO、RPO、lost/repeated work和fault goodput如何？
- **RQ5 Algorithmic fidelity**：central reference和distributed path在matched proposal trace上是否产生相同trajectory，长训练是否保持matched-token model quality？
- **RQ6 Redundancy policy**：warm standby、fixed active-active和hedged execution在failure rate/straggler分布下的成本收益边界是什么？

## 8. Claim–evidence map

| 候选 claim | 必需证据 | 主要反例/威胁 |
|---|---|---|
| no dedicated syncer allocation | C9 vs D8 matched workload、node/GPU allocation logs | learner CPU interference导致总时间上升 |
| equivalent optimizer semantics | CRS/decomposed/LFE duplicate digest suites；long-run quality | floating point/order nondeterminism |
| executor failover without state transfer | kill owner；空local state接管；storage-only replay | hidden local cursor/cache authority |
| at-most-once logical inclusion | duplicate/response-loss/head-race state-machine tests | same proposal被不同work order消费 |
| redundancy improves fault goodput | D8 vs D8-R2 under controlled fault tapes | duplicate CPU/I/O cost超过收益 |
| storage growth bounded safely | reachability proof、dry-run/apply、restore after GC | listing omission、loser PFT premature deletion |
| controller co-optimizes system and algorithm | shadow replay、guarded enforced ablation | policy改变quality或无法复现 |

## 9. 建议贡献表述

较稳妥的四项贡献：

1. A dedicated-syncer-free architecture that executes sharded outer-optimizer tasks on learner-host CPUs while preserving a storage-resident authoritative trajectory.
2. A deterministic work-order/prepared-transition protocol that pairs every parameter fragment with its outer-optimizer state and separates at-least-once execution from a fenced logical commit.
3. A redundant ownership and failover mechanism that reassigns fragment execution without optimizer-state migration and contains learner–executor co-failures.
4. A Miyabi evaluation quantifying correctness, GPU interference, shared-filesystem load, resource allocation, recovery and model-quality trade-offs against central and active/standby baselines.

避免使用：`fully decentralized`、`coordinator-free`、`exactly-once delivery`、`checkpoint-free`、`first sharded syncer`。可使用：`dedicated-syncer-free`、`storage-mediated authority`、`learner-hosted fragment executors`、`redundant prepare`、`at-most-once logical commit`。

## 10. 参考文献与链接

1. Decoupled DiLoCo Team. *Decoupled DiLoCo for Resilient Distributed Pre-training*. arXiv:2604.21428, 2026. https://arxiv.org/abs/2604.21428
2. Li et al. *Scaling Distributed Machine Learning with the Parameter Server*. OSDI 2014. https://www.usenix.org/conference/osdi14/technical-sessions/presentation/li_mu
3. Ren et al. *ZeRO-Offload: Democratizing Billion-Scale Model Training*. USENIX ATC 2021 / arXiv. https://arxiv.org/abs/2101.06840
4. Jiang et al. *Towards Demystifying Serverless Machine Learning Training* (LambdaML). arXiv:2105.07806, 2021. https://arxiv.org/abs/2105.07806
5. Qi, Ramakrishnan, Lee. *LIFL: A Lightweight, Event-driven Serverless Platform for Federated Learning*. MLSys 2024. https://arxiv.org/abs/2405.10968
6. Jayaram et al. *Adaptive Aggregation For Federated Learning* (AdaFed). arXiv:2203.12163, 2022. https://arxiv.org/abs/2203.12163
7. Barrak. *Shard the Gradient, Scale the Model: Serverless Federated Aggregation via Gradient Partitioning*. arXiv:2604.22072, 2026. https://arxiv.org/abs/2604.22072
8. Chen et al. *Revisiting Distributed Synchronous SGD*. Backup workers analysis. https://arxiv.org/abs/1702.05800
9. *SWIFT: Expedited Failure Recovery for Large-Scale DNN Training*. https://arxiv.org/abs/2302.06173
10. *BatchWeave: A Consistent Object-Store-Native Data Plane for Large Foundation Model Training*. arXiv:2605.09994, 2026. https://arxiv.org/abs/2605.09994
11. Kale, Douillard, Donchev. *Eager Updates For Overlapped Communication and Computation in DiLoCo*. arXiv:2502.12996. https://arxiv.org/abs/2502.12996

提交论文前应再次检索 2026-07-11 之后发表的工作，并检查每项 claim 的优先权和术语。
