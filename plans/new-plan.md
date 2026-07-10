# 结论

**技术上可以实现，但按当前 idea v1 的表述和现有代码状态，尚不足以达到顶级会议发表标准。**

更准确的判断是：

| 维度 | 评估 |
|---|---|
| 工程可实现性 | 高 |
| idea v1 的独立新颖性 | 中等偏低 |
| 当前项目作为论文 artifact 的成熟度 | 低 |
| 重新聚焦后的研究潜力 | 中高 |
| 更适合的投稿方向 | MLSys、FAST、EuroSys、SC；NSDI/OSDI 属于高门槛目标 |
| NeurIPS/ICML/ICLR 适配度 | 除非增加新的优化算法或理论，否则较弱 |

截至 2026 年 7 月 10 日，该分支仍为 6 个提交，最新提交是 `011e180`。README 仍主要把系统描述为单 GPU learners、一个 syncer、safetensors/JSON 文件交换、syncer-local SQLite 和 `latest.json` 指针。它目前更接近一个 filesystem transport 与 fragment merge 的机制原型，而不是一个完整的 storage-native training system。

按审稿视角：

- **当前 v1 文本直接投稿：倾向 Weak Reject。**
- **只把现有代码接上 MinIO/S3：仍然倾向 Reject。**
- **重构成 event-sourced optimizer、完成严格故障语义、两类真实存储后端和完整对照实验：可以成为有竞争力的系统论文。**

---

# 一、为什么这个方向在工程上可行

这个方向成立的基础不是“文件系统足够快”，而是 Decoupled DiLoCo 给出了足够大的通信隐藏窗口。

原始系统让 learners 独立执行本地优化，syncer 根据 quorum 拉取 parameter fragments；通信在后台进行，adaptive grace window 用来吸收 learner 速度差异。原论文还进行了 12B 模型的美国多区域实验，报告非共置训练与共置版本速度接近，而跨区域数据并行严重变慢。

真正需要验证的条件应写成尾延迟约束，而不是平均延迟约束：

\[
P_{99}\left(
T_{\mathrm{publish}}
+T_{\mathrm{select}}
+T_{\mathrm{read}}
+T_{\mathrm{merge}}
+T_{\mathrm{commit}}
\right)
\leq
H\cdot T_{\mathrm{local\ step}}-\epsilon
\]

其中：

- \(H\) 是一个 fragment 两次有效同步之间的 local compute interval；
- \(T_{\mathrm{commit}}\) 包括 manifest CAS、outer optimizer 状态发布和 head 更新；
- \(\epsilon\) 是防止 pipeline 被尾延迟击穿的安全余量。

同时还必须满足 syncer 的长期服务率高于 proposal 到达率，否则即使单次 I/O 可以被隐藏，队列仍会无限增长。

现代对象存储也提供了实现协议所需要的基本原语。S3 提供强 read-after-write consistency，并支持 `If-Match`、`If-None-Match` 条件写；GCS 的对象读写和对象列表也是强一致的。它们使“小型 manifest 上的条件更新 + 不可变 tensor objects”成为可行实现。

但这些原语只证明“可以构建协议”，不代表对象存储自动提供：

- 多对象事务；
- exactly-once optimizer update；
- fragment 与 outer state 的原子可见性；
- syncer failover；
- 安全 GC；
- 因果一致的 learner recovery。

这些正是论文必须解决的问题。

---

# 二、idea v1 当前最大的障碍是新颖性边界

## 1. 原始 Decoupled DiLoCo 已经包含 replay、checkpoint 和 recovery

你们目前列出的第五项贡献“replayable chaos engineering”不能作为主要新意。原论文已经记录包含 vector clock、token counters 和 failure/recovery events 的 event tape，并声称可以按相同 quorum、参与者集合和权重进行 bitwise-identical replay。

原论文还实现了：

- 基于 vector clock 的状态协调；
- Chandy–Lamport 一致性分布式 checkpoint；
- syncer model parameters 与 outer optimizer state checkpoint；
- learner model parameters 与 inner optimizer state checkpoint；
- in-flight messages 的保存和恢复；
- 从健康 peer learner 获取模型和 inner optimizer state 的 learner recovery。

因此以下表述不再足够：

> 持久化 parameter fragments 可以支持 checkpoint、replay 和 learner recovery。

审稿人会直接问：

> 原 Decoupled DiLoCo 已经有一致性 checkpoint、event tape 和 recovery。你们除了把 transport 改成 storage，还增加了什么新的系统性质？

## 2. “通信 artifact 就是 checkpoint”已经出现了直接相邻工作

NSDI 2026 的 Checkmate 已经提出：数据并行训练中创建 checkpoint 所需的信息已经以 gradients 的形式存在于网络中，因此可以把 gradients 同时复制给 CPU shadow cluster，由后者持续维护模型 checkpoint。论文报告 per-iteration checkpoint、与无 checkpoint 基线接近的训练吞吐，以及明显降低的失败重算工作量。

LowDiff 则把同步后的 compressed gradients 直接复用为 differential checkpoints，并增加 batched writes 和 checkpoint frequency 调优。

所以以下宽泛主张也已经不够新：

> 训练通信中的更新信息可以同时用作增量 checkpoint。

你们真正可能独有的是：

> **异步、fragment-level、two-level optimizer 的更新流能否成为全局训练状态的权威 durable log。**

这是比“communication artifact is checkpoint”更具体、更困难，也更有发表价值的问题。

## 3. 对象存储、manifest、exactly-once 和 checkpoint-driven GC 也已有相邻工作

2026 年的 BatchWeave 已经构建了 object-store-native training data plane，使用 versioned manifests 和 conditional writes，实现 batch publication、recovery、checkpoint-aligned lifecycle management 和 end-to-end exactly-once semantics；它还把 durable producer state、watermark 和 GC 结合起来，并在 64 GPU 工作负载上评估。

BatchWeave 处理的是训练数据 batch，不是 model update，因此它并没有覆盖你们的问题。但它会消耗以下通用新颖性：

- immutable object + manifest；
- conditional update；
- durable producer sequence；
- exactly-once consumption；
- watermark-based GC；
- object-store-native training data plane。

你们的贡献必须说明：

> 为什么 optimizer fragment commit 比 batch commit 更难，以及为此引入了哪些 training-specific abstraction。

例如：

- merge 是非幂等操作；
- outer optimizer state 与参数 fragment 必须一致演进；
- 一个 proposal 依赖特定 base fragment version；
- quorum 可能选择 proposal 的任意子集；
- update 可能 stale、重复、乱序或 superseded；
- 不同 fragments 可以拥有不同版本；
- learner 使用的是版本向量，而非单一全局 step。

## 4. “异构、异步、跨集群 LLM 训练”本身也已不是空白

NSDI 2026 的 Di-PS 已经是异构、异步、容错的 cross-cluster LLM training system，并报告最多 9 个集群、超过 10,000 个 NPU 和 100B 参数模型的生产部署。

所以不能把论文主要卖点写成：

> 我们首次支持跨区域、异构和易失资源上的异步 LLM 训练。

你们的差异必须是：

> **不依赖一个网络常驻参数服务作为权威状态，而以 durable optimizer log 作为权威状态和恢复边界。**

---

# 三、必须修正一个核心概念：parameter fragment 不是完整 checkpoint

当前 idea v1 把 learner update、incremental checkpoint 和 learner recovery 混在了一起。

一个 parameter fragment 或 pseudo-gradient 通常不包含：

- inner optimizer momentum/Adam moments；
- scheduler state；
- AMP GradScaler；
- Python、NumPy、CPU、CUDA RNG state；
- dataloader shard、sample cursor 和 token offset；
- learner 的 fragment adoption history；
- 尚未提交的 local interval base；
- local update sequence。

因此，“每个 communication artifact 都是 checkpoint”在严格意义上不成立。

论文应定义至少三种恢复保证。

### G1：全局状态恢复

恢复：

- committed global parameter fragments；
- per-fragment outer optimizer state；
- committed proposal IDs；
- global fragment-version frontier。

目标是：

> syncer 重启后，恢复状态严格等于 durable commit log 的某个已提交前缀。

这是你们最应该首先完成、也最容易形成强贡献的保证。

### G2：learner warm restart

learner 从最新 global frontier 重建模型，重新初始化 inner optimizer 和数据迭代状态，丢弃尚未提交的 local work。

这种恢复不等于原训练轨迹，但可能在 Decoupled DiLoCo 中具有可接受的模型质量。必须通过故障频率 ablation 实证验证。

### G3：learner exact restart

除了 global fragments，还恢复：

- learner inner optimizer；
- RNG；
- dataloader cursor；
- scheduler/scaler；
- local fragment bases 和未决 proposal。

这需要单独的 learner capsule 或一致性分布式 snapshot。parameter fragment 本身做不到。

因此更准确的论文措辞应是：

> Communication artifacts are recoverable global-state contributions, while committed fragment transitions form incremental global checkpoints.

而不是：

> Every learner update is a complete checkpoint.

一个合理设计是：

- **global checkpoint 完全由 fragment log 派生；**
- **learner exact recovery 使用低频 learner capsules；**
- **不需要 periodic full global checkpoint。**

这样仍然实现了重要的 checkpoint–communication fusion，同时避免过度声明。

---

# 四、建议把 idea 升级为 ver.2

推荐的核心定位是：

## DuraLoCo：An Event-Sourced Storage-Native Optimizer for Decoupled LLM Training

建议使用如下论文主张：

> In low-communication asynchronous training, the committed optimizer-update stream can serve as the authoritative durable global state. By transactionally committing fragment proposals together with outer-optimizer transitions, DuraLoCo unifies synchronization and global checkpointing, supports stateless syncer failover, and enables prefix-consistent recovery across POSIX and object-storage backends.

关键变化是：

- 不再强调“文件系统替代 RPC”；
- 不再笼统强调“通信消息也是 checkpoint”；
- 强调 **event-sourced optimizer**；
- durable log 是 source of truth；
- 参数和 optimizer state 是 materialized views；
- checkpoint 是 log frontier，而不是另一套独立数据副本。

## 建议的四项主要贡献

### 1. Transactional Fragment Commit

定义一个训练专用的原子逻辑提交：

```text
proposal object:
  learner_session_id
  monotonic_seq
  fragment_id
  base_fragment_version
  base_frontier_digest
  tokens_since_base
  payload_kind
  payload_hash
  payload_shape/dtype

commit manifest:
  commit_id
  parent_commit_id
  fragment_id
  selected_proposal_ids
  merge_weights
  output_fragment_hash
  outer_state_hash
  fencing_epoch
  resulting_fragment_version
```

发布过程：

```text
write immutable proposal/output/state objects
        ↓
write PREPARED commit manifest
        ↓
CAS fragment head from parent_commit_id to commit_id
        ↓
commit becomes visible
```

物理传输采用 at-least-once，系统提供：

> **exactly-once logical inclusion of each learner contribution**

这比直接声称“exactly-once delivery”更准确，也更容易证明。

### 2. Event-sourced global optimizer

将以下状态定义为 commit log 的 materialized view：

- global parameter fragments；
- outer momentum/Adam state；
- per-fragment step；
- proposal consumption watermarks；
- global frontier vector。

周期性 compaction snapshot 只用于减少 replay 时间，不再是一套独立 checkpoint 协议。

恢复结果应满足：

\[
\operatorname{Recover}(\text{log prefix})
=
\operatorname{Fold}(\text{committed transitions})
\]

这才是“通信与 checkpoint 融合”的强形式。

### 3. Stateless syncer failover 与 fencing

syncer-local SQLite 只能作为：

- scan cache；
- materialized index；
- metrics cache。

不能继续作为权威状态。

新的 syncer 实例应当仅凭 durable log 恢复，并通过：

- lease；
- monotonically increasing fencing epoch；
- parent-head CAS；
- idempotent commit replay；

避免两个 syncer 同时推进 fragment head。

### 4. Storage-aware algorithm–system co-design

只实现正确协议仍可能被认为是已知分布式存储技术的组合。论文还需要一个针对 Decoupled DiLoCo 的系统—算法协同机制。

建议联合控制：

- fragment size；
- local interval \(H\)；
- quorum；
- grace window；
- in-flight depth；
- object bundling；
- compaction frequency；
- eager 或 selected-only payload materialization。

控制目标可以定义为：

\[
\max \ \text{useful tokens/sec}
\]

subject to：

\[
P_{99}(T_{\mathrm{storage\ pipeline}})
<
H T_{\mathrm{step}}
\]

\[
\mathbb{E}[\text{staleness}]
\leq S_{\max}
\]

\[
\text{object/request budget}
\leq C_{\max}
\]

这种 storage-latency-aware scheduling 比“固定 fragment + 固定 grace + S3 backend”更可能构成新的技术贡献。

---

# 五、当前项目需要的是架构反转，而不是简单增加一个 S3 backend

现有组件中可以保留：

- learner/syncer 进程解耦；
- safetensors payload；
- parameter index 和 balanced fragmentation；
- explicit outer optimizer；
- synthetic end-to-end 测试；
- 基础 telemetry 和 failure injection。

但以下部分需要重构：

| 当前项目 | Storage-native paper system |
|---|---|
| POSIX `Path`、glob、rename | `StorageBackend` 抽象 |
| syncer-local SQLite 维护状态 | durable commit log 为权威，SQLite 为缓存 |
| `latest.json` 单指针 | per-fragment commit chain + global frontier |
| 单 syncer 假设 | lease、fencing、CAS 和 failover |
| update status 的多步本地事务 | immutable objects + transactional manifest |
| fragment update 缺少严格因果边界 | session、sequence、base digest、version vector |
| learner resume 不完整 | warm restart 或 learner capsule |
| 按文件数量保留 | ack/watermark/compaction-based GC |
| whole-model flatten/scatter | direct fragment gather/scatter |
| 一次载入全部 quorum tensors | streaming weighted reduction |
| 只有 filesystem transport | network、POSIX、object-store 三类 backend |
| 只验证 job 能跑完 | crash-prefix correctness 和 model-quality validation |

前述代码审查中已经复现的 P0 问题，包括 future-version update 被接受、弱 metadata 验证、syncer 在 `selected` 状态崩溃后 update 永久卡住、没有 fencing、fragment resume 缺失和 retention 不完整，都属于新协议必须先消除的基础问题。

## 最小 backend contract

不要用统一的 POSIX 文件 API去模拟对象存储。建议定义语义级接口：

```text
put_immutable(key, bytes, expected_hash)
put_if_absent(key, bytes)
conditional_replace(key, expected_version, bytes)
get(key)
head(key)
range_get(key, offset, length)
delete_batch(keys)
```

正确性不能依赖目录 listing。Listing 可以用于发现和 GC，但 commit 可见性必须由显式 head/manifest 决定。

至少实现：

- `PosixBackend`：rename、fsync parent、O_EXCL/lock；
- `S3CompatibleBackend`：immutable PUT、ETag/conditional PUT、multipart；
- 一个真正的公共对象存储 backend。

MinIO 适合协议开发，但不能单独证明：

- 公有云尾延迟；
- API throttling；
- request cost；
- 跨区域传输；
- provider failure behavior。

---

# 六、必须正面处理 storage I/O amplification

对象存储不是“没有网络的通信”。

假设：

- \(K\) 个 learners；
- quorum 为 \(q\)；
- fragment 大小为 \(S\)。

如果所有 learners 都提前上传 proposal，syncer 读取 \(q\) 个，随后写一个 global fragment，所有 learners 再拉取它，那么每次 fragment commit 的数据移动量近似为：

\[
K S + qS + S + KS
\]

分别对应：

- learner proposal writes；
- syncer reads；
- committed output write；
- learner output reads。

这可能比直接 learner→syncer→learner 传输具有更大的存储和网络放大。

论文必须研究至少两种模式：

### Eager durability

所有 proposal payload 立即持久化。

优点：

- recovery 和审计最完整；
- learner 崩溃后 proposal 仍可使用；
- 协议简单。

缺点：

- \(K/q\) 越大，未被选中 proposal 的写放大越严重。

### Selected-only materialization

learner 先发布小型 availability manifest，syncer 选定 quorum 后，只有入选 learners 上传 payload。

优点：

- 降低无效 payload writes。

缺点：

- 增加一次控制往返；
- learner 必须保留对应 local snapshot；
- learner 在入选后、上传前失败会影响 quorum；
- 不再是“所有 proposal 都天然持久化”。

这本身可以成为有价值的 design-space study。论文不需要证明 storage 在所有场景都更好，而应给出明确的 break-even region。

---

# 七、实验必须采用因子化对照，而不是只比较 FS 版本

最重要的实验设计是把“transport”和“checkpoint fusion”分开。

建议使用 2×2 对照：

| 系统 | Transport | Checkpoint |
|---|---|---|
| A | ephemeral network | periodic distributed checkpoint |
| B | ephemeral network | update-log-derived checkpoint |
| C | persistent storage | separate periodic checkpoint |
| D | persistent storage | fused durable optimizer log |

由此才能分别回答：

1. storage transport 本身造成多少开销；
2. checkpoint fusion 节省多少 I/O 和恢复工作；
3. D 的收益来自 storage、fusion，还是二者共同作用。

另外加入：

- metadata RPC + object payload 的 hybrid baseline；
- Lustre、MinIO 和真实 S3/GCS backend；
- 普通 global checkpoint + whole-job restart；
- 原始或近似的 Decoupled DiLoCo network implementation。

没有 network Decoupled baseline 时，审稿人无法判断结果究竟证明了 storage-native 的价值，还是只证明当前 Python RPC 实现不够好。

## 工作负载层次

### Correctness 层

使用 tiny deterministic model，验证：

- full-vector 与 fragment-count=1 数值等价；
- replay 后 global state digest 相同；
- 每个 proposal 至多被逻辑应用一次；
- 任意 commit 阶段 kill 后恢复到合法前缀；
- GC 不删除任何可达状态。

### End-to-end quality 层

至少需要：

- 多个模型规模，而不是只用 tiny GPT-2；
- 非平凡训练 token budget；
- 至少 3 个 seeds；
- matched tokens 和 matched compute；
- validation loss/perplexity；
- 下游 evaluation；
- failure-free 和 failure-injected 两种训练。

WikiText-2 可以保留作 smoke test，但不能作为核心 ML 证据。

### 系统扩展层

现有 8 learner + 1 syncer 规模可以验证真实训练机制，但不足以单独支撑“大规模跨云 LLM 训练”的普遍主张。原 Decoupled DiLoCo 已经报告 2B/5B 级训练和 12B 多区域实验；Di-PS 已报告 100B 和超过 10,000 个 NPU 的生产规模。

合理方案是：

- 在现有 GPU 上做真实小中型模型训练；
- 对 7B、13B、70B-equivalent fragment sizes 做 tensor-only I/O 和 merge benchmark；
- 使用真实存储 latency traces 做 trace replay；
- 明确区分“真实 end-to-end 结果”和“模拟扩展结果”。

顶会不机械要求 100B 训练，但论文不能把 9 GPU 的结果直接外推为 frontier-scale 结论。

## 故障矩阵

至少覆盖：

```text
learner 在 proposal 发布前/后崩溃
syncer 在 PREPARED、CAS 前、CAS 后崩溃
两个 syncer 同时运行
重复 manifest
乱序和 stale proposal
future-base proposal
截断或 checksum 错误 payload
对象写成功但客户端超时
storage throttling / transient error
网络分区
compaction 中途崩溃
GC 与 restore 并发
恢复到旧 frontier
磁盘或 bucket quota 耗尽
```

对每个 failpoint，需要自动验证 safety invariants，而不仅是“进程最终退出”。

## 指标

除 loss 和 perplexity 外，至少报告：

- useful tokens/sec；
- ML goodput；
- learner GPU idle fraction；
- syncer utilization；
- P50/P95/P99 publish-to-commit latency；
- quorum wait 和 grace wait；
- proposal selected/drop/superseded ratio；
- storage read/write amplification；
- object/file operations per commit；
- additional checkpoint bytes；
- compaction 和 GC 成本；
- recovery time objective；
- recovery point objective；
- lost、repeated 和 duplicate-applied tokens；
- API request 和跨区域传输成本；
- peak object count 和 steady-state footprint。

---

# 八、建议设置明确的内部 go/no-go 标准

这些不是会议统一规定，而是判断是否值得正式投稿的最低结果目标。

## 正确性

- 所有 crash points 后都恢复到 committed-log 的合法前缀；
- 零 double logical apply；
- stale、future、corrupt proposals 的接受率为零；
- 双 syncer 场景没有 split-brain；
- GC 压力测试中没有删除可恢复状态；
- 固定 event schedule 下 replay 结果满足预定义数值容差。

## 性能

- 在目标 low-communication 区间，failure-free goodput 相对网络版下降不超过约 5%–10%；
- storage pipeline 的 P99 延迟能够被 local compute interval 隐藏；
- 存储占用经过 compaction/GC 后保持有界；
- streaming merge 的内存复杂度接近 \(O(S)\)，而不是 \(O(qS)\)。

## 恢复收益

至少出现一个真实且重要的工作区间，使 storage-native 版本：

- 明显降低恢复时间；
- 明显减少 failure 后重复训练 token；
- 相比 separate checkpoint 减少总 durable write volume；
- 在相同 failure schedule 下提高 end-to-end goodput。

理想结果应是成倍改善，而不只是几个百分点，否则很难抵消协议复杂度和对象存储请求成本。

## ML quality

在 matched tokens/FLOPs 下：

- failure-free storage-native 与 network Decoupled 基线统计上接近；
- failure-injected 条件下没有系统性 degradation；
- warm learner restart 和 exact learner capsule 的质量差异得到量化。

---

# 九、投稿方向判断

## MLSys

这是当前最匹配的主目标。

需要同时具备：

- storage/system design；
- Decoupled DiLoCo-specific co-design；
- 真实模型质量；
- goodput、故障和成本结果；
- 完整 artifact。

仅有存储 microbenchmark 不够。

## FAST

当论文重点放在以下内容时很合适：

- transactional fragment log；
- object/metadata layout；
- crash consistency；
- compaction 和 GC；
- I/O amplification；
- POSIX/object-store portability；
- checkpoint elimination。

需要弱化“我们提出新训练算法”，强化训练状态存储语义。

## NSDI / OSDI / SOSP

并非不可能，但要求明显更高。NSDI 2026 已有：

- Checkmate：复用网络 gradients 实现近零训练开销的 per-iteration checkpoint；
- Di-PS：大规模异步跨集群 LLM 训练；
- ByteCheckpoint 等工业级 checkpoint 系统也已经提供多 backend、resharding 和全栈性能优化。

要进入这一档，DuraLoCo 需要表现为一种可推广的系统抽象，而不是“DiLoCo 的 S3 实现”：

- 清晰的一致性模型；
- 形式化 safety invariants；
- 多 backend；
- 无状态 failover；
- 显著性能或恢复收益；
- 足够强的规模证据；
- 对其他 asynchronous optimization workflow 的潜在适用性。

## NeurIPS / ICML / ICLR

只做 storage protocol 通常不够。

需要额外增加例如：

- storage-delay-aware asynchronous optimization；
- 对 variable delay、drop、replay 的收敛分析；
- 新的 staleness/durability weighting；
- fragment scheduling 对样本效率的理论或算法贡献；
- 显著优于原 Decoupled DiLoCo 的模型质量或稳定性。

否则应优先选择系统会议。

---

# 最终判断

这个研究方向应当继续，但必须从 idea v1 收缩和强化为：

> **不是 filesystem-backed communication，而是一个以 durable fragment commit log 为唯一权威状态的 event-sourced distributed optimizer。**

最有价值且仍然存在的研究空白是：

1. 对异步、quorum-based、fragment-level outer optimization 定义 transactional commit；
2. 使 global parameters 和 outer optimizer state 可以完全由 committed log 恢复；
3. 在 syncer crash、重复 proposal、乱序、split-brain 和 GC 下提供可证明的 prefix consistency；
4. 消除独立的 full global checkpoint 数据路径；
5. 通过 storage-aware scheduling 隐藏对象存储尾延迟；
6. 证明这种融合在特定 failure rate、local interval 和存储性能区域内能提高总训练 goodput。

因此：

- **作为工程项目：可以实现。**
- **作为当前 v1 论文主张：不够。**
- **作为 DuraLoCo/event-sourced optimizer 方向：具有顶级系统会议潜力。**
- **当前代码可以作为起点，但核心状态管理、恢复协议和 backend 层需要架构级重构，而非增量添加 S3 支持。**

在继续扩展代码前，应先冻结一份 research contract：

```text
Primary guarantee:
  committed global optimizer state is prefix-recoverable
  with exactly-once logical proposal inclusion.

Primary benefit:
  periodic full global checkpoints are eliminated or greatly reduced.

Performance boundary:
  storage overhead is hidden in the intended low-communication regime.

Non-claims:
  does not beat NCCL for frequent synchronization;
  does not provide exact learner recovery without learner capsules;
  does not improve all model sizes, intervals, or storage backends.
```

这份边界能同时避免与 Decoupled DiLoCo、Checkmate、LowDiff、BatchWeave 和 Di-PS 的主要贡献发生正面重叠。