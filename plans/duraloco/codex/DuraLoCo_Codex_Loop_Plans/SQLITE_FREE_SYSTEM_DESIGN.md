# DuraLoCo 无 SQLite 系统设计

## 1. 设计结论

DuraLoCo 从 M00 开始不得导入、调用、生成、备份、恢复或要求
SQLite。也不得用另一个嵌入式数据库替换 SQLite 来保留同样的双重状态
模型。系统只有一个持久化权威：P04 建立的、由单一 head CAS 线性化的
committed transition log。

所有查询结构、scanner cursor、pending/eligible set、learner liveness、调度中间状态
和 metrics summary 都必须是以下两类之一：

1. 进程内可丢弃的 immutable/replace-on-write 视图；
2. 从 committed log、不可变 objects、heartbeats 或 append-only telemetry 重建的导出物。

丢失任意本地目录后，新进程仍必须仅依赖 shared storage 中的权威 log 和
其可达 objects 恢复到同一 committed state digest。

## 2. 权威数据模型

### 2.1 唯一可变权威

`control/head.json` 是唯一可变权威指针。它通过 backend
`conditional_replace` 推进，并指向 checksum-verified frontier。一个 optimizer
transition 只能在 head CAS 成功时成为 committed。

### 2.2 不可变 objects

以下内容在 head CAS 之前按 content identity 不可变发布：

- proposal manifest 与 payload object；
- fragment/full-vector params object；
- outer optimizer state object；
- commit record；
- frontier；
- drop/supersession/stop/lease decision object（对应阶段引入后）；
- P07 引入的 snapshot、pin 与 learner capsule。

prepared 但不可从 head 达到的 objects 只是 orphan evidence，不能影响选择、
恢复或终止判定。

### 2.3 完整 frontier

frontier 必须记录恢复和下一次决策所需的全部权威事实：

- commit sequence 与 parent lineage；
- 每个 fragment 的 version、params ref 和 outer-state ref；
- 已消费 proposal IDs 或其等价的已验证 compact summary；
- 已提交 drop/supersession decisions；
- deterministic scheduler cursor；
- 后续阶段引入的 fencing epoch、stop state、controller state 和 snapshot refs。

任何上述事实都不得仅存在于本地索引、JSONL telemetry、CSV 或 heartbeat。

## 3. 进程内 RuntimeView

### 3.1 启动构建

syncer 启动时调用 `replay_log` 并构建一个不可变 `RuntimeView`：

```text
RuntimeView
  head/frontier/commit lineage
  fragment params + outer-state refs
  consumed proposal IDs
  committed drop/supersession decisions
  learner/session/fragment last committed sequence
  scheduler cursor
  stop/fencing/controller state when available
```

M00 先使用完整 prefix replay。P07 引入 snapshot + suffix replay 后可降低启动成本，
但 snapshot 本身也必须是 head-reachable 的权威事实，不得引入本地数据库依赖。

### 3.2 运行时更新

每次 head CAS 成功后，syncer 从已提交 commit/frontier 生成新的
`RuntimeView`，再原子替换进程内引用。不允许在 CAS 之前将 proposal 持久化为
`selected`。未提交选择只存在于当前调用栈/内存对象中。

进程崩溃会丢失该视图；新进程通过 replay 生成等价视图。视图不写入本地
持久化存储。

## 4. Proposal discovery 与选择

1. learner 先发布不可变 payload，再发布 Protocol v2 manifest；
2. scanner listing 只用于发现 candidate key，可以重复、漏项或重排；
3. syncer 对每个 candidate 执行 P01 full validation 和 immutable-byte snapshot；
4. 使用 `RuntimeView` 排除已消费、已 drop、错误 base、rollback 或超 staleness
   proposal；
5. 调用与 P02 reference/replay 共用的 deterministic selection kernel；
6. CAS conflict 后丢弃内存 selection，对新 head 完整 replay/revalidate/reselect。

scanner cursor 只能是内存 hint。重启时允许从头扫描；正确性不依赖 cursor 持久化。

## 5. 生产 tensor transition

M00 将现有 full-vector/fragment `safetensors` 与 outer optimizer state 发布接入
P04 transaction：

- payload 保持大对象编码，commit/frontier 只保存 ObjectRef 和实现 digest；
- reducer/outer-step 必须在 P02 numeric contract 内与 reference 等价；
- `latest.json`、materialized full weights 和人类可读 summaries 可保留为兼容导出，
  但它们必须从 committed frontier 生成，不参与权威判定；
- update 的 pending/selected/applied/dropped 状态通过“candidate 可见性 + committed
  selection/drop decisions”推导，不存在独立状态表。

## 6. 恢复、停止与 liveness

- **Global recovery**：从 head 完整 replay 或 P07 snapshot+suffix replay。
- **Response loss**：以 request identity 和 committed ancestry 识别原操作是否已成功。
- **Liveness**：heartbeat files 和进程内计时器只提供观测/调度信号，不是权威。
- **Stop**：M00 至少从权威 log 恢复 terminal fact；P05 完成 stop/lease/fencing
  state machine。
- **Learner recovery**：P06 提供 warm restart，P07 capsule 提供 exact learner restart。

任何恢复路径都不读取 DB dump、本地数据库或未受权威 log 绑定的状态快照。

## 7. Telemetry 与 analysis

- 运行事件以 append-only JSONL 记录，每条包含 run/actor/event/request/commit IDs；
- 高频 metrics 可使用 CSV/JSONL，并绑定 schema/version/config digest；
- analysis CLI 直接 fold committed log + telemetry + manifests；
- 生成的 summaries/plots 是可删除导出物，不得反向影响 protocol；
- P08 如需加速扫描，只能使用内存索引、key sharding 和 committed watermark，
  不引入本地数据库。

## 8. 旧 run 与配置迁移

旧 SQLite-backed run 保持不可变历史 artifact，但新代码不提供 DB reader、恢复或
就地转换。如需延续权重，必须在移除前的已验证 commit 上完成权重/外优化器
checkpoint 导出，然后使用 M00 `bootstrap-new-generation` 在新 run generation 中导入
这些不可变 objects。

该 bootstrap：

- 不读取旧 DB；
- 不保留 pending/selected/applied history；
- 不声称 exact continuation；
- 记录 source checkpoint digests、新 run/generation ID 和显式 warm-start 语义。

以下配置/CLI 字段必须删除并 fail closed：

```text
sqlite_local_dir
resume_db_dump
db_dump_every_versions
keep_last_db_dumps
--sqlite-local-dir
--db
```

## 9. 必须删除的代码和 artifacts

- `fs_diloco/sqlite_store.py`；
- `fs_diloco/schema.sql`；
- `fs_diloco/log/cache.py` 及 `rebuild-cache` CLI；
- Python `sqlite3` imports；
- `db_dumps/` path、retention、backup/restore 代码；
- SQLite-specific tests、PBS variables、shell helpers 和 evidence validators；
- 默认或隐式兼容的 SQLite config keys。

历史 phase reports/artifacts 可继续包含该词，但不得被当作当前 runtime 依赖。

## 10. 不变量

1. 除单一 head CAS 外没有 committed transition mutation。
2. 本地持久化状态全部删除后，committed state digest 不变。
3. 没有 durable `selected`、pending 或 applied 中间状态。
4. proposal 只能出现在一个 committed selection 中。
5. params 和 outer state 始终由同一 frontier 成对引用。
6. listing、heartbeat、JSONL、CSV、`latest.json` 和内存视图都不是权威。
7. 恢复、takeover、analysis 和 Checker 都不需要 SQLite 或其他本地数据库。
8. 旧 DB-backed run 不在新 generation 中静默恢复或混用权威。

## 11. 阶段边界

- **M00**：实现无数据库生产运行时，删除 SQLite 全部表面，重跑
  P00–P04 审核标准。
- **P05**：在 M00 运行时上增加 lease/fencing/failover/stop，不再负责数据库迁移。
- **P06**：完成 learner v2 publication/adoption/warm recovery。
- **P07**：以 head-reachable snapshot + suffix replay 提供有界恢复与 lifecycle。
- **P08/P10–P12**：只使用 committed log、内存视图、JSONL/manifests 和可达 snapshots。
- **可选 P09**：对象存储 backend 必须通过同一无数据库 contract。
