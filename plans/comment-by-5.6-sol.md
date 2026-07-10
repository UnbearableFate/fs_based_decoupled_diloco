# 审查结论

审查基线固定为提交 `011e180980e90c500bcd479a594ba47e507bb5d1`，即 2026 年 7 月 9 日的 “Implement fragment-level filesystem DiLoCo”。我检查了核心源码、配置、测试、设计文档，并进行了编译、outer optimizer 对照、full-vector/fragment synthetic E2E 及若干针对性故障复现。没有在 Miyabi 的 9 节点 H100/Lustre 环境执行正式实验，因此下面关于并行文件系统扩展性的结论属于代码路径分析，不是集群基准结果。

总体判断：

> 当前分支是一个有价值的 Milestone-2 工程骨架和机制演示，但还不是 research-grade 的 Filesystem-backed Decoupled DiLoCo prototype。

它已经能演示独立 learner、独立 syncer、filesystem 消息交换、SQLite 状态、full/fragment merge 和 outer optimizer；但尚不能可靠支持以下研究结论：

- 算法上等价或接近论文中的 Decoupled DiLoCo；
- 崩溃后不会丢失、重复或永久卡住更新；
- learner/syncer 重启后能恢复相同训练轨迹；
- 多 syncer 或节点故障时不存在 split-brain；
- 在 Lustre 上具有可控的 metadata 压力、磁盘占用和通信效率；
- 实验结果可复现、可审计、可与基线公平比较。

README 和 `docs/design.md` 仍主要描述 milestone 1 的“整个参数向量作为单一逻辑 fragment”，而当前代码已经进入 fragment-level milestone 2，文档、配置和实现已经明显漂移。

## 已经做得较好的部分

当前实现不是空壳，以下部分可以继续保留：

- learner 和 syncer 进程真正解耦，没有依赖 `torch.distributed`、NCCL、RPC 或 Ray；
- 使用 safetensors payload、JSON commit marker、本地 SQLite 和 `latest.json` 建立了清晰的基础协议；
- 参数索引和 whole-tensor balanced fragmentation 是确定性的；
- outer SGD、momentum、Nesterov 和 AdamW 的显式状态管理结构合理；
- full-vector 和 fragment 两条路径均已存在；
- 有 metrics、JSONL 日志、analysis、failure simulation、LM evaluation 接口及多种启动脚本；
- 原子发布使用同目录临时文件和 `os.replace`，能够避免普通进程并发下读取半写文件。README 描述的总体单 GPU learner、单 GPU syncer、filesystem commit-marker 架构与实现基本一致。

本地验证结果：

| 项目 | 结果 |
|---|---|
| 核心 Python 模块编译 | 通过 |
| 自定义 SGD/momentum/Nesterov 对照 `torch.optim` | 数值一致 |
| 自定义 AdamW 对照 `torch.optim` | 最大差约 `2.98e-8` |
| 2 learner full-vector synthetic E2E | 正常完成 2 个 outer step |
| fragment synthetic E2E | 能产生 4 个 global merge event 和有效全局模型 |
| fragment 终止 | merge 成功，但 learner 没有按照全局 stop 正确退出 |

因此基础计算逻辑可以复用，主要问题集中在协议正确性、故障恢复、算法语义和系统扩展性。

# 一、P0：进入真实多节点实验前必须修复

## 1. 更新协议没有建立完整性边界

`validate_update_metadata` 当前只验证少量字段和文件是否存在。尤其是路径验证逻辑在 `relative_to(shared_root)` 失败时直接忽略异常，因此指向 shared root 之外的绝对路径也会被接受。验证器也没有可靠检查：

- 完整 schema、字段类型和取值范围；
- payload 文件大小；
- SHA-256；
- safetensors key；
- tensor shape、dtype；
- NaN/Inf；
- fragment ID 与参数索引是否一致；
- metadata 中的 run/config/model/fragment digest 是否匹配。

这意味着损坏文件、错误 shape、恶意或陈旧路径、错误 run 产生的文件都可能进入 syncer；轻则 syncer 整体崩溃，重则 NaN 被合并进全局模型。

本地最小复现：

| 输入 | 当前结果 |
|---|---|
| payload 路径位于 shared root 之外 | 验证通过 |
| metadata 声明错误 SHA-256 和 size | 验证通过 |
| safetensors 中含 NaN | 可进入聚合路径 |
| metadata 缺少关键字段 | 在后续代码触发 `KeyError`，不是被隔离 |

需要增加统一的 Protocol v2 validator，并将失败更新移动到 quarantine，而不是让异常穿透并终止 syncer。

## 2. “来自未来”的更新会被当作零陈旧更新

当前 SQLite eligibility 条件主要检查：

```text
current_version - base_version <= max_staleness
```

但没有检查：

```text
base_version <= current_version
```

因此，当当前版本为 3、更新的 base version 为 4 时，负的版本差仍满足上界条件。后续 staleness 又通过 `max(0, ...)` 截断为 0，最终这个逻辑上不可能存在的更新会获得最优权重。

本地复现结果：

```text
current fragment version = 3
update base fragment version = 4
eligible = true
computed staleness = 0
```

所有 full 和 fragment eligibility 都应强制：

```text
0 <= current_version - base_version <= max_staleness
```

同时还应验证 `base_global_merge_event`、run generation 和 fragment-version vector 的因果关系。

## 3. 文件发布与 SQLite 状态不是一个可恢复事务

fragment merge 的实际顺序大致是：

1. 把 update 标记为 `selected`；
2. 读取 tensors 并计算 merge；
3. 写 fragment weights；
4. 写 outer optimizer state；
5. 更新 SQLite fragment version；
6. 发布 `latest.json`；
7. 清理文件；
8. 最后把 update 标记为 `applied`。

这些步骤分别提交 SQLite 或发布 filesystem 文件，不属于一个原子事务。任意一步被 kill 都可能产生以下状态：

- update 已经是 `selected`，但尚未应用；
- 新 weights 已发布，但 SQLite 还认为是旧版本；
- SQLite 已更新，但 `latest.json` 尚未发布；
- `latest.json` 已发布，但 updates 仍是 `selected`；
- optimizer state、fragment weight 和 materialized full weight 版本不一致。

代码没有在启动时系统性 reconcile 这些中间状态。

本地故障复现：

```text
restart 前 update status = selected
restart 后 update status = selected
restart 后 eligible updates = []
```

即该 update 会永久搁置，既不会重新应用，也不会自动回滚。

需要引入显式 merge journal/redo log，例如：

```text
discovered
→ validated
→ selected
→ computed
→ payload_published
→ head_published
→ applied
→ acknowledged
```

每个阶段必须是幂等的。syncer 启动时应根据 journal、commit marker、fragment state 和 `latest.json` 自动 roll-forward 或 rollback，而不是依赖“正常退出”。

## 4. 没有 single-writer lease 和 fencing

设计假设只有一个 syncer，但代码没有强制这一假设。两个 syncer 同时启动时，可以各自拥有本地 SQLite，各自选择相同 updates，并竞争写：

- fragment version；
- outer optimizer state；
- `latest.json`；
- stop marker；
- cleanup 操作。

原子 rename 只能保证单个文件不半写，不能防止逻辑 split-brain。

filesystem-only 方案至少需要：

- shared-root syncer lease；
- 单调递增的 fencing epoch；
- 每个 global/fragment manifest 都携带 epoch；
- learner 和 syncer 拒绝低 epoch 发布物；
- lease takeover 前进行状态 reconciliation；
- 在目标 Lustre 环境验证 `mkdir`、`O_EXCL`、rename 和 advisory locking 的实际语义。

仅用本地 SQLite 无法协调不同节点上的两个 syncer。

## 5. fragment stop 和 resume 语义不完整

当设置 `max_local_steps` 时，fragment learner 的停止判断优先只看本地 step，不再检查全局 `stop.json`。因此 syncer 已经达到目标并发布 stop 后，learner 仍可能继续训练到自己的本地上限。

此外，fragment resume 路径明确抛出 `NotImplementedError`。

当前也没有恢复 learner 的：

- inner optimizer；
- scheduler；
- AMP scaler；
- local step；
- local update index；
- tokens-since-fragment-load；
- fragment base vector；
- RNG states；
- dataset cursor。

因此 learner 重启不是 resume，而是从一个不完整的全局状态重新启动另一条训练轨迹。

需要把以下终止条件分开定义：

```text
global_stop_requested
local_budget_exhausted
fatal_protocol_error
no_progress_timeout
operator_shutdown
```

并明确优先级。通常全局 stop 应高于本地预算。

## 6. retention 没有消费确认协议

full 模式的 learner 主要根据“保留最近 N 个本地 update”删除旧文件，而不是根据 syncer acknowledgment 删除。慢 syncer 或长 grace window 下，尚未消费的 update 可能被 learner 删除。

fragment 模式则基本不清理 learner updates，因此：

- metadata 文件数量持续增长；
- safetensors 持续增长；
- fragment weight versions 持续增长；
- outer optimizer state 持续增长。

配置中存在 `keep_processed_updates`、`cleanup_applied_after_versions` 等字段，但没有形成完整的实际状态机。

需要建立：

```text
published → ingested → selected → applied/dropped → acknowledged → gc-safe
```

learner 只能删除已 acknowledged 或低于安全水位的更新。syncer 需要持久化 per-learner/per-fragment watermark。

## 7. update 没有严格的因果贡献边界

当前 learner 上传的是绝对参数快照。以下两个场景会产生不清晰甚至重复的贡献：

第一，开启 inner-step 期间轮询 global latest 后，一次 local interval 可能由多个不同 global base 共同产生，但 metadata 仍只记录 interval 开始时的 base。

第二，在 learner 尚未采用新 global model 前，它可以连续产生多个基于同一 base 的嵌套快照。如果这些快照先后被应用，后一个快照可能再次包含前一个快照已经表达的局部训练进展。

协议应强制：

- 一个 update interval 只能有一个不可变 base；
- global adoption 只能发生在 interval 边界；
- update 必须包含 `learner_session_id + monotonic_seq`；
- 明确 payload 是 absolute snapshot 还是 delta；
- 对同一 learner/base 的 superseding update 定义清晰规则；
- 已应用 contribution segment 不得再次进入 merge。

对研究实现，更稳妥的是发布相对于明确 base digest 的 delta。

## 8. 原子写入没有给出完整持久性保证

当前实现对临时文件执行 flush/fsync，再执行 `os.replace`，但没有在 rename 后 fsync 父目录。因此它能很好地防止普通进程读取半写文件，但没有建立“节点掉电或文件系统故障后目录项一定持久”的保证。实际行为还取决于 Lustre 和挂载配置。

需要：

- rename 后可配置地 fsync 父目录；
- 启动时探测目标文件系统能力；
- 明确 failure model：仅考虑 process kill，还是同时考虑 node crash、MDS 故障和短暂 I/O error；
- 对每个发布阶段进行 kill/restart 测试；
- 对 `EIO`、`ESTALE`、短读、延迟可见和暂时不存在进行重试与隔离。

# 二、算法上尚未完整实现 Decoupled DiLoCo

论文所描述的 decoupled 方案不仅是“把 tensor 放到 filesystem”。其关键组成包括 fragment-wise 异步同步、minimum quorum、动态 learner 权重、自适应 grace window、RDA、向量时钟/event tape 和一致性 checkpoint。

当前实现状态如下：

| 能力 | 当前状态 | 评价 |
|---|---|---|
| 独立 learner/syncer | 已实现 | 可用 |
| Fragment-wise merge | 已实现 | 基础路径可运行 |
| Minimum quorum | 基础实现 | 缺动态策略和公平性 |
| Staleness weighting | 部分实现 | 版本定义和因果约束不足 |
| Token/step weighting | 部分实现 | 使用的计数与论文语义不完全一致 |
| Adaptive grace window | 未真正实现 | 配置存在，但实际仍接近固定窗口 |
| RDA | 未实现 | 计划中明确暂不纳入 |
| Per-fragment causal vector | 不完整 | 有局部版本字段，但非完整向量时钟 |
| Event tape/replay | 未实现 | 无法审计和确定性重放 |
| Consistent checkpoint | 未实现 | learner 与 syncer 不能形成一致快照 |
| Peer-assisted recovery | 未实现 | 可延后 |
| Sub-tensor fragmentation | 未实现 | 初版可延后，但影响负载均衡 |

项目计划本身也把 RDA、sub-tensor fragmentation、MoE、网络 transport 和部分 optimizer-state 语义列为当前 milestone 的非目标。因此这些不完全是实现疏漏，但必须限制论文复现声明的范围。

具体算法问题如下。

## 1. Grace window 配置名义上支持模式，实际主要是固定时间

当前 deadline 基本由固定 seconds/max seconds 决定。配置中的 adaptive mode、EMA、slack 等没有形成真正根据到达率和 learner latency 调整的窗口。

需要记录每个 fragment 的：

- quorum 到达时间；
- inter-arrival distribution；
- learner latency；
- estimated additional gain；
- EMA 和 bounded slack；

然后基于明确公式确定 grace deadline，而不是只保留配置字段。

## 2. 权重语义不足

当前主要类似：

```text
weight = tokens_this_update /
         (1 + staleness_lambda * fragment_staleness)
```

但没有充分利用：

- 自 learner 加载该 fragment 以来的 steps/tokens；
- learner 期间是否再次采用过其他 fragment；
- `base_global_merge_event`；
- 每个 fragment 的因果版本向量；
- update 中实际新增而非重复包含的 token contribution。

因此“token 多的 update 权重大”不等于论文中的动态贡献估计。

## 3. quorum 选择存在稳定的 learner ID 偏置

候选 update 排序后，在达到 `quorum_max` 时直接截断。满足条件的 learner 超过上限时，低字典序的 learner ID 会持续更容易入选。

本地复现中，三个同时 eligible 的 learner、`quorum_max=2` 时稳定选择：

```text
learner_000
learner_001
```

需要采用：

- oldest-first 加公平轮转；
- deficit/credit scheduling；
- 基于最近入选率的补偿；
- 或确定性 hash rotation；

并记录每个 learner 的 selected/dropped/aged-out 比率。

## 4. learner 的 fragment adoption 会重建整个 inner optimizer

一个 fragment 更新后，当前简化方案会重建整个模型的 optimizer/scheduler，而不是只重置或更新对应 fragment 的 optimizer state。这会导致未更新 fragment 的 momentum、Adam moments 和 scheduler 状态也被丢弃，成为严重实验混杂因素。

初始工程验证可以保留这一简化，但正式实验至少需要以下 ablation：

```text
reset-all
reset-updated-fragment-only
preserve-all
```

并将该策略写入 checkpoint 和实验 manifest。

## 5. learner 和 syncer 使用的 fragment 时钟不一致

learner 主要按本地 `local_update_index` 选择下一个 fragment，syncer 主要按 `global_merge_event` 选择目标 fragment。learner 重启后本地索引又会重置。

在异构速度、learner 重启或 update 丢失情况下，可能出现：

- syncer 等待 fragment A；
- 大部分 learner 正在产生 fragment B；
- A 永远达不到 quorum；
- 最终触发 no-progress timeout。

应把 fragment schedule 变成协议的一部分，例如：

- syncer 发布当前可接受 fragment set；
- learner 从该 set 选择；
- 或使用全局 deterministic schedule 加持久化 learner cursor；
- 支持多个 fragment 同时处于 collecting 状态，而不是单一全局目标。

## 6. 缺少 RDA、event tape 和一致性 checkpoint

RDA 可以作为可配置算法而非唯一实现，但若目标是忠实复现论文，需要至少支持论文定义的 RDA 路径。论文还用 event tape/vector clocks 记录因果顺序，并用一致性 checkpoint 支持重放和恢复。

缺少这些能力时，可以把当前方法称为：

> filesystem-backed asynchronous fragment DiLoCo variant

不宜直接声称是完整的 Decoupled DiLoCo 复现。

# 三、性能和 Lustre 扩展性问题

这些问题目前未必会在小 synthetic test 中暴露，但会直接影响 9 节点和更大模型实验。

## 1. fragment 操作仍频繁处理整个模型

learner 上传一个 fragment 时，会先把整个模型 flatten 到 CPU，再切出一个 fragment。采用一个 fragment 时，也会 flatten/scatter 整个模型。

`materialize_full_from_fragments` 还可能对每个 fragment 重复 clone/散射完整向量，复杂度接近：

```text
O(number_of_fragments × total_parameters)
```

这削弱了 fragment 化本来应带来的通信和内存优势。

需要：

- 根据 parameter index 直接 gather 目标参数；
- 直接对目标 parameter slices 原位 scatter；
- 使用 pinned CPU buffers；
- 使用独立 CUDA stream 和 event；
- 缓存 fragment layout；
- 禁止每次 fragment 操作重新构造完整 flat vector。

## 2. syncer 一次性载入 quorum 的所有 tensors

当前聚合倾向于将所有候选 payload 同时读入内存。内存复杂度约为：

```text
O(quorum × fragment_size)
```

full 模式则接近：

```text
O(quorum × model_size)
```

应改为 streaming weighted accumulator：

```text
accumulator += weight_i * tensor_i
weight_sum += weight_i
```

每次只保留一个输入 tensor、累加器和少量工作空间。

## 3. whole-tensor fragmentation 不能切分巨型 tensor

当前 balanced whole-tensor 策略与论文的主要方案一致，因此初版可以接受；但单个大型 embedding 或 output projection 仍可能独占一个 fragment，造成严重负载不均。论文也讨论了 sub-tensor fragmentation 的均衡优势及额外复杂度。

建议先保留 whole-tensor 作为稳定基线，再将 sub-tensor 作为性能阶段的独立 feature，不应在 P0 阶段增加协议复杂度。

## 4. filesystem metadata 路径会随运行时间退化

当前存在以下扩展风险：

- 反复 glob 和 sort 整个 pending 目录；
- 大量小 JSON commit marker；
- JSONL 每条事件 open/append/flush/fsync；
- 多进程写共享 CSV 时没有锁或单写者；
- update、fragment version、outer state 无界增长；
- 没有目录分片；
- 没有持久化 scan cursor；
- 没有 batching；
- 没有 backoff/jitter；
- 没有统计 metadata operations。

在 Lustre 上，应把通信目录设计为分层结构，例如：

```text
updates/
  run_generation/
    fragment_0007/
      learner_004/
        bucket_000123/
```

scanner 使用 watermark 或 SQLite cursor 做增量发现，而不是重复遍历历史目录。

## 5. 数据的 streaming 实际上仍会整体物化

`hf_data` 的 streaming 路径仍将 shard 文本、token stream 和 blocks 聚合为 Python list。这会：

- 失去真正 streaming 的内存优势；
- 每个 learner 重复大量 preprocessing；
- 无法精确保存 dataset cursor；
- 重启后容易重复读取开头数据。

应改成 lazy iterator/IterableDataset，并把 shard、sample index、token offset 和 shuffle RNG 纳入 learner checkpoint。

# 四、配置、可复现性和测试问题

## 1. 多个配置项只是声明，没有形成有效行为

在该提交中，以下字段存在明显的“配置已暴露、代码未完整消费”现象：

```text
sync.upload_mode
grace_window.mode
liveness.quorum_policy
inner_optimizer.reset_on_global_update
io.atomic_write
io.keep_processed_updates
io.cleanup_applied_after_versions
data.validation_split
data.num_proc
data.synthetic_num_batches
```

配置模型虽然能拒绝部分未知 key，但缺少系统的类型、范围和交叉约束验证。

应在启动前拒绝：

- `inner_steps <= 0`；
- quorum min/max 关系错误；
- 负 timeout、负 staleness；
- 非法 beta、epsilon、概率；
- fragment count 大于可分配 tensor 数；
- 不支持的 precision；
- full/fragment 模式冲突配置。

所有未实现字段应删除、标记 experimental，或启动时明确报错，不能静默忽略。

## 2. 环境不可复现

`pyproject.toml` 中核心依赖没有精确版本或 lockfile，也未看到固定 container、CI matrix 或环境 manifest。

正式实验至少要保存：

- Git commit；
- dirty-tree 状态；
- Python、PyTorch、CUDA、cuDNN、transformers、datasets、safetensors 版本；
- GPU 型号和驱动；
- model revision；
- tokenizer revision；
- dataset revision；
- config digest；
- parameter index digest；
- fragment layout digest；
- Lustre mount/stripe 参数；
- hostname、SLURM job ID 和 rank mapping。

## 3. 随机状态控制不完整

当前主要设置 PyTorch seed，但 failure simulation 使用 Python random，其他 NumPy、CUDA、dataset shuffle 和 worker RNG 也没有形成统一、可恢复的 seed tree。

应使用：

```text
master_seed
├── model_init_seed
├── data_seed_per_learner
├── failure_seed
├── fragment_schedule_seed
└── evaluation_seed
```

并把所有 RNG states 写入 checkpoint。

## 4. 混合精度路径不完整

bf16 有 autocast 路径，但 fp16 没有完整的 `GradScaler` 和 scaler checkpoint。使用 fp16 时容易出现 underflow/overflow，重启后也无法恢复 scaler 状态。

要么正式支持 fp16 autocast + GradScaler，要么在配置验证阶段明确只允许 bf16/fp32。

## 5. token accounting 不够精确

当前 token 计数倾向于统计输入 token 数，但 causal LM 中实际产生监督预测的位置通常少于输入长度，并可能受 padding、mask、最后一个 token 等影响。

研究比较应明确使用：

- input tokens；
- non-masked target tokens；
- optimizer-consumed tokens；
- unique dataset tokens；

其中哪一个作为训练预算和 weighting 依据。

## 6. 测试集中在 happy path

现有测试覆盖了基础 atomic write、config、fragment round trip、outer optimizer 和若干 merge 行为，但缺少真正的故障状态机矩阵。测试目录已有一定规模，但不足以验证 research system 的一致性。

必须补充：

- 每个发布阶段 kill；
- payload 截断；
- 错误 safetensors key/shape/dtype；
- hash/size mismatch；
- NaN/Inf；
- future base version；
- update metadata 重复及冲突；
- 两个 syncer；
- learner session 重启和 seq 重用；
- SQLite 损坏或丢失；
- `latest.json` 比 DB 新或旧；
- fragment weight 与 optimizer state 版本不一致；
- payload 发布后延迟可见；
- no-progress 与 late update；
- GC 和 scanner 并发；
- 磁盘满、权限错误、短暂 `EIO`；
- deterministic event replay。

# 五、实现 research prototype 所需的建设顺序

## Phase 0：Protocol v2 与崩溃一致性

首先定义不可含糊的 update manifest：

```text
protocol_version
run_id
run_generation
config_digest
model_revision
param_index_digest
fragment_layout_digest

learner_id
learner_session_id
update_seq
update_id

fragment_id
base_fragment_version
base_global_merge_event
base_version_vector_digest
base_payload_digest

local_steps_since_base
target_tokens_since_base
payload_kind        # snapshot | delta
tensor_key
shape
dtype
payload_size
payload_sha256

created_at_monotonic
commit_marker_version
```

发布顺序应为：

```text
write payload.tmp
fsync payload
rename payload
fsync payload parent
write manifest.tmp
fsync manifest
rename manifest as commit marker
fsync manifest parent
```

scanner 只发现 commit marker，不扫描裸 payload。

同时实现：

- 严格 schema validator；
- path containment；
- shape/dtype/finite/hash/size 检查；
- invalid quarantine；
- syncer lease/fencing；
- merge journal；
- startup reconciliation；
- idempotent apply；
- ack 和 GC watermark；
- 明确 stop state machine。

这是所有后续算法实验的前提。

## Phase 1：明确且可验证的算法语义

需要做出并固化以下选择：

1. payload 是 delta 还是 absolute snapshot；
2. 一个 update 对应哪一段不重叠的 local work；
3. interval 内是否允许采用 global update；
4. late update 是 drop、rebase 还是降权；
5. quorum 是 per-fragment 还是 per-event；
6. 同一 learner 多个候选 update 的 supersession 规则；
7. staleness 是 scalar、fragment scalar 还是 vector-clock distance；
8. outer optimizer state 是 global、per-fragment 还是 parameter-wise；
9. learner inner optimizer state在 fragment adoption 时如何处理。

随后实现：

- per-fragment version vector；
- 禁止 future update；
- interval base freeze；
- fair quorum selection；
- adaptive grace；
- steps/tokens-since-base weighting；
- 可配置 RDA；
- per-fragment optimizer-state policy；
- deterministic event tape。

## Phase 2：真正的恢复能力

learner checkpoint 至少包含：

```text
model or recoverable fragment state
inner optimizer
scheduler
GradScaler
local step
local update sequence
fragment scheduler cursor
per-fragment base vector
tokens/steps since each base
Python/NumPy/Torch/CUDA RNG
dataset shard and cursor
last acknowledged update
```

syncer checkpoint/journal 至少包含：

```text
global merge event
per-fragment versions
per-fragment weights digest
per-fragment outer optimizer state
selected/applied update IDs
fencing epoch
latest manifest digest
GC watermarks
```

需要明确实现哪一种保证：

- exactly-once logical apply；
- at-least-once delivery + idempotent apply；
- 或允许 bounded lost work。

推荐采用第二种，因为 filesystem transport 更容易实现“至少一次发现 + 幂等应用”。

## Phase 3：性能和 PFS 工程

按优先级实施：

1. direct fragment gather/scatter；
2. streaming weighted reducer；
3. pinned buffers 和 CUDA stream；
4. incremental directory scanner；
5. directory sharding；
6. SQLite 批量事务；
7. bounded retention；
8. shared metrics 单写者；
9. filesystem capability probe；
10. metadata/throughput profiler。

至少记录：

```text
payload bytes per trained token
metadata operations per update
publish latency
visibility latency
quorum wait
grace wait
merge compute time
disk read/write throughput
GPU idle time
scanner CPU time
directory entry count
peak RSS/VRAM
```

## Phase 4：研究实验设计

至少需要以下基线：

1. 单 learner AdamW；
2. 同 token 预算的同步数据并行；
3. 原始 synchronous DiLoCo；
4. full-vector decoupled average；
5. fragment decoupled average；
6. fragment decoupled + adaptive grace；
7. fragment decoupled + RDA。

原始 DiLoCo 的核心是较大的 local inner interval、inner AdamW 和 outer Nesterov，并以显著降低通信为目标；因此通信量、token budget 和 outer-step 频率必须与基线严格对齐。

必须做的 ablation：

- fragment count/size；
- quorum min/max；
- grace fixed/adaptive；
- staleness lambda；
- local interval；
- learner 数量；
-速度异构；
- update drop/late rate；
- learner/syncer crash rate；
- reset-all 与 reset-fragment-only；
- averaging 与 RDA。

核心结果不应只报告“job 跑完、loss 有限、无异常”。现有实验文档和计划中的验收标准偏向运行成功，需要加入算法正确性和统计比较。

应报告：

- validation loss/perplexity 对 tokens；
- validation loss/perplexity 对 wall clock；
- goodput 和 GPU utilization；
- bytes/token；
- staleness 分布；
- quorum wait 分布；
- learner selection fairness；
- dropped/superseded update 比率；
- crash recovery time；
- lost/repeated token work；
- disk footprint；
- 至少 3 个 seed 的均值和置信区间。

# 六、最低 Definition of Done

在称为“Filesystem-backed Decoupled DiLoCo research prototype”前，建议满足以下硬性门槛：

1. `fragment_count=1` 与 full-vector 路径在同一 event tape 下数值一致；
2. 单 learner、quorum 1 的结果与串行 reference implementation 一致；
3. future、corrupt、wrong-run、wrong-shape、NaN update 的接受率为零；
4. 在每个 merge 阶段 kill syncer，重启后没有 update 永久卡在 `selected`；
5. 同一 update 不会被逻辑应用两次；
6. 同时启动两个 syncer 时，只有持有有效 fencing epoch 的实例能发布；
7. learner 重启后能够恢复数据 cursor、RNG 和 optimizer 状态；
8. 在固定 event tape 下重放结果满足定义好的数值容差；
9. 运行时间增长时，磁盘占用和目录项数量保持有界；
10. fragment merge 的峰值内存接近 `O(fragment_size)`，而不是 `O(model_size × fragment_count)`；
11. 在目标 Lustre 上通过 rename/visibility/kill/GC 压力测试；
12. 9 节点实验同时报告收敛、goodput、通信量、staleness 和故障恢复指标，而不仅是成功退出。

# 最终优先级

建议严格按以下顺序推进：

1. **严格更新验证、future-version 拒绝、quarantine；**
2. **merge journal、启动 reconciliation、幂等 apply；**
3. **single-syncer lease 和 fencing；**
4. **冻结 update base、补充 learner session/sequence 和 contribution lineage；**
5. **fragment resume、完整 learner checkpoint、stop state machine；**
6. **ack-based retention 和有界 GC；**
7. **adaptive grace、正确 weighting、公平 quorum、可选 RDA；**
8. **direct fragment I/O、streaming reducer 和 Lustre metadata 优化；**
9. **event tape、确定性 replay、chaos test matrix；**
10. **token-matched baselines、ablation 和多 seed 正式实验。**

在前六项完成前，不建议投入大规模 H100 训练；那样最可能得到的是昂贵但无法判断是否受重复更新、状态漂移、重启偏差或文件系统竞态影响的实验结果。