# Reference Model 与 Production 对照

## 作用

`fs_diloco/log/model.py`、`fs_diloco/testing/reference_simulator.py` 和
`fs_diloco/testing/model_checker.py` 构成小状态、确定性的协议 oracle。它们枚举 proposal、decision、
commit、crash/restart/CAS conflict 和 lineage 状态，检查 I-001–I-009，并用 deliberate mutants 证明
关键不变量能杀死错误实现。

reference model 的价值是把“期望的 committed state”与 POSIX、PyTorch、MPI launcher、telemetry 等
工程细节分开。它不是 production storage，也不提供性能或 Miyabi/Lustre 证据。

## Production 对照

`ProductionTransactionalLog` 使用相同 canonical manifests、selection/weight/numeric oracle 和
head-CAS transition。production codec 把 params/outer state 编码为 safetensors；strict replay 将实际
ObjectRef 读回并与 reference fold/state digest 比较。

distributed path 在 reference transition 前增加 FWO/input bundle、LFE PFR/attempt envelope、membership、
ownership/fencing 和 redundancy validation，但只有最终 commit/frontier/head 进入 global optimizer chain。
prepared result 不是第二套 state machine。

## Evidence 层级

1. pure reference/model checker：不变量与 counterexample；
2. memory/POSIX fault tests：storage/commit crash windows；
3. 1-node compute：真实 runtime、codec、GPU/model 或 focused lifecycle；
4. 2-node compute：Lustre cross-node locking、visibility、failover；
5. 8-node/D8-R2：完整 topology、workload、fault schedule 和 lifecycle；
6. independent checker：RED-on-base、GREEN-on-feature、identity/checksum audit。

较低层 PASS 不能替代较高层，较高层也不能追溯性地使未运行的 gate 变成 PASS。

## Identity-preserving change

性能/工程改动若不改变 canonical input、decision、numeric backend 和 committed schema，应在固定 tape 上
证明 old/new committed IDs、prefix digests 和 final state 相同。若确实需要改变 identity，则必须采用
显式 protocol/schema/generation boundary，并记录 ADR/Checker 兼容性结论，不能原地改写历史对象。
