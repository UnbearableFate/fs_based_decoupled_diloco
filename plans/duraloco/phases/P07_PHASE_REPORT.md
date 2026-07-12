# P07 Milestone Report (in progress)

## English

P07 started from the completed P06C persistence commit
`6a528cbe26a9209720325ce031937c30d970b977` on branch
`codex/duraloco-p07-distributed-lifecycle`. Loop P07.1 is in progress. D-0701
chooses immutable snapshot side objects that become replay roots only through a
fenced `snapshot_pin` transition in the single global ancestry. Snapshot
absence, corruption, or staleness cannot block empty-cache strict replay.

No P07 runtime acceptance is claimed yet. Miyabi runtime tests, D1, D2-R2,
D8-R2, lifecycle soak, destructive synthetic GC, and independent Checker are
all unrun.

## 中文

P07从已完成的P06C固化提交
`6a528cbe26a9209720325ce031937c30d970b977`开始，分支为
`codex/duraloco-p07-distributed-lifecycle`。当前正在执行P07.1。D-0701选择
immutable snapshot side object；只有被唯一global ancestry中的fenced
`snapshot_pin` transition引用后，它才成为可用replay root。snapshot缺失、损坏或过期
不得阻塞empty-cache strict replay。

当前不声称任何P07 runtime验收通过。Miyabi runtime、D1、D2-R2、D8-R2、lifecycle
soak、synthetic destructive GC和独立Checker均尚未运行。
