# DuraLoCo Transaction Log Contract / DuraLoCo 事务日志契约

## English

`authority/runs/<run>/generations/<generation>/control/head.json` is the only
mutable authority. Genesis uses create-if-absent; every later optimizer
transition becomes committed only through one conditional replacement of the
head. Proposal payloads/manifests, parameter tensors, outer-state tensors,
commit records, and frontiers are immutable preparations. An unreachable
preparation is an orphan and cannot affect recovery or selection.

Each frontier carries the complete fragment map, paired parameter and
outer-state ObjectRefs, their producing commits, cumulative consumed proposal
IDs, and the deterministic scheduler cursor. Replay starts at the verified
head and checks the entire parent-linked prefix, proposal causality and lineage,
canonical weights, content references, pairing, consumption, and scheduling.

The production codec stores flat float32 safetensors for each parameter
fragment and named safetensors for its outer state. Full-vector and fragment
runs use the same `ProductionTransactionalLog` and head-CAS commit path.
Candidate discovery is a repeatable full scan; omissions, duplicates, and
reordering cannot change committed state. A CAS conflict discards the tentative
selection and forces replay, validation, and reselection.

`RuntimeView` is immutable and process-local. Deleting a process working
directory or killing the syncer loses only hints. A new process opens the run,
replays the committed prefix, and obtains the same state digest. Human-readable
latest/stop files and telemetry are exports and may be deleted or corrupted
without changing authority.

Historical checkpoints can seed a fresh generation only through explicit warm
start. Proposal history, selection state, sequence authority, and exact-
continuation claims are never imported.

## 中文

`authority/runs/<run>/generations/<generation>/control/head.json` 是唯一可变
权威。Genesis 通过 create-if-absent 建立；之后每个优化器 transition 只有一次
head 条件替换成功后才成为 committed。proposal payload/manifest、参数张量、外
优化器状态、commit 与 frontier 都是不可变 prepare 对象；head 不可达的对象是
orphan，不能影响恢复或选择。

每个 frontier 包含完整 fragment map、成对的参数/outer-state ObjectRef、产生它们
的 commit、累计 consumed proposal IDs 与确定性 scheduler cursor。Replay 从校验
后的 head 开始，验证完整 parent prefix、proposal 因果与 lineage、规范权重、内容
引用、配对、消费集合和调度状态。

生产 codec 为每个参数 fragment 保存 flat float32 safetensors，并以具名
safetensors 保存 outer state。full-vector 与 fragment run 共用
`ProductionTransactionalLog` 和同一 head-CAS 路径。候选发现可从头重扫；listing
漏项、重复或重排不改变 committed state。CAS 冲突后丢弃 tentative selection，
重新 replay、validate 和 select。

`RuntimeView` 是进程内不可变视图。删除进程工作目录或 kill syncer 只会丢失 hint；
新进程从 committed prefix 恢复同一 state digest。latest/stop 与 telemetry 是可删除
导出物，不能成为权威。

历史 checkpoint 只能显式 warm-start 新 generation；不得导入 proposal history、
selection/sequence authority，也不得声称 exact continuation。
