# DuraLoCo Research Contract

状态：M00–P07 与 H0 已实现并验证；P08/P10/P11 的 roadmap 不属于当前保证。本契约区分已经由
测试/PBS/Checker 支持的 safety claim、只在特定证据范围内成立的 operational result，以及尚未
实现的目标。

## Terms

- **Proposal**：learner 从命名 causal base 和不重叠 local interval 产生的一次不可变 fragment
  contribution；identity 同时绑定 payload 内容与协议上下文。
- **Commit**：确定性的 optimizer/control transition。只有 single global head 条件替换成功后，
  commit 才进入权威轨迹。
- **Frontier**：某一 committed sequence 上全部 parameter fragment、配对 outer state、scheduler、
  membership 和 consumption 状态的完整视图。
- **Head**：最新 committed frontier 的唯一 mutable authority pointer。不可变对象存在不代表已提交。
- **Logical inclusion**：proposal 对 committed optimizer trajectory 的一次逻辑贡献。传输和观察可
  at-least-once，但同一 proposal ID 最多出现在一个 committed selected set。
- **Global exact recovery**：从 head 可达 prefix 恢复完全相同的 global params、fragment outer state、
  scheduler/membership 和 proposal-consumption state。
- **Warm learner restart**：从最新 global frontier 创建新 learner session，并重新初始化私有 optimizer、
  RNG、scheduler/scaler 与 data cursor；它不是 trajectory-exact。
- **Exact learner restart**：从完整、验证过且与 frontier 一致的 learner capsule 恢复私有 optimizer、
  RNG、scheduler/scaler、data cursor、interval 和 pending state，再以新 session 继续。

## 已实现的安全保证

1. committed transition log 与一个 head CAS 是唯一持久 optimizer authority。
2. params 和 outer state 同 commit 配对；prepare/orphan 不影响 replay。
3. strict replay 验证完整 head-reachable parent chain、ObjectRef、identity、causality、selection、numeric
   transition、consumption、membership 和 fencing。
4. at-least-once observation 下保持 exactly-once logical proposal inclusion，而不是 exactly-once delivery。
5. lease takeover 通过 committed monotonically increasing fencing epoch 隔离旧 owner。
6. fresh open、takeover、verification/ambiguity/corruption boundary 从 empty-cache strict replay 开始；
   verified-object memoization 仅限成功 replay 后的同一进程 owner/session。
7. committed snapshot pin 可加速为 snapshot+suffix replay，但结果必须等于 strict replay；失败则回退。
8. reachability 保护 committed ancestry、active distributed evidence、snapshot、pin/ack、capsule、eligible
   proposal、grace/loser/divergence/quarantine roots 和未知 future-schema object。
9. exact capsule marker-last 发布并验证完整私有状态；缺组件、frontier/session mismatch fail closed。
10. error/stop 终止事实由 committed control transition 表达；derived stop file 不能单独结束 authority。

详细不变量见 [invariants.md](invariants.md)，故障边界见 [failure_model.md](failure_model.md)。

## 证据范围

H0 的历史 terminal 结果绑定 runtime commit `f167a07c49339ba42d14f8a5873fe2c8781884d4`：
9-node allocation、8 GPT-2/WikiText-2 learners、50 local × 10 global、factor-2 LFEs、两个故障注入、
10 committed transitions、752 秒、最大恢复 89.44 秒。它是该配置和 Miyabi/Lustre 环境的结果，
不是任意模型规模、后端、故障率或 lease 参数的普遍结论，也不再定义 forward topology。
当前及后续实验严格使用 8-node allocation；历史 C9/H0 不得被重新提交为新证据。

Synthetic/in-memory 单元测试证明协议性质，不可表述成 Lustre/GPU/model-quality 证据。所有实验
主张必须绑定 commit、dirty-tree 状态、config/environment/backend/seed、命令、PBS ID、raw artifact
和 checksum，并同时保留失败或 superseded attempt。

## 非主张

DuraLoCo 当前不声称：

- exactly-once transport、Byzantine learner 容错或永久 durable object 丢失后的恢复；
- 每个 proposal 都是完整 checkpoint，或 warm restart 等于 Exact learner restart；
- full-training bitwise replay、任意 GPU/driver/backend 间 bitwise numeric identity；
- 用共享文件系统替代所有高频 NCCL/RDMA collective；
- real namespace destructive GC 已获生产授权；
- 自动把 D8 中被移除的 whole learner 恢复并无缝 reintegrate；
- 当前已有 true range I/O、streaming reducer、bounded materialization 或线性 proposal catalog；
- 在所有 local interval、模型、failure rate、quorum 和存储条件下提高质量或 goodput。

## 研究方向

P08 负责 profile-first 的 direct fragment I/O、validation reuse、streaming/bounded reducer、telemetry
和数据结构复杂度；P10 负责更高层研究评估；P11 负责长期运行与工程清理。后续优化不得引入
第二 authority、跨 owner 持久缓存、弱化 payload validation、绕过 fencing 或把多次 transition
隐藏在未经定义的新提交语义中。
