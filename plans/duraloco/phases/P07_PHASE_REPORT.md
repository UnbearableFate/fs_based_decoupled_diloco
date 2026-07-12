# P07 Milestone Report (in progress)

## English

P07 started from the completed P06C persistence commit
`6a528cbe26a9209720325ce031937c30d970b977` on branch
`codex/duraloco-p07-distributed-lifecycle`. Loop P07.1 is in progress. D-0701
chooses immutable snapshot side objects that become replay roots only through a
fenced `snapshot_pin` transition in the single global ancestry. Snapshot
absence, corruption, or staleness cannot block empty-cache strict replay.

Miyabi 1-node job `2365797.opbs` on clean commit `03ed1392` passed 53 focused
snapshot, fencing, and production-log tests. It proves P07-A02 and P07-A03:
missing/corrupt/stale snapshots leave strict replay available, and a usable
snapshot is pinned through the single global head rather than a second mutable
authority. Snapshot+suffix equivalence remains in progress. D1, D2-R2, D8-R2,
lifecycle soak, destructive synthetic GC, and independent Checker are unrun.

## 中文

P07从已完成的P06C固化提交
`6a528cbe26a9209720325ce031937c30d970b977`开始，分支为
`codex/duraloco-p07-distributed-lifecycle`。当前正在执行P07.1。D-0701选择
immutable snapshot side object；只有被唯一global ancestry中的fenced
`snapshot_pin` transition引用后，它才成为可用replay root。snapshot缺失、损坏或过期
不得阻塞empty-cache strict replay。

Miyabi 1-node作业`2365797.opbs`在干净提交`03ed1392`上通过53项snapshot、fencing和
production-log测试，证明P07-A02与P07-A03：snapshot缺失/损坏/过期时strict replay仍可用，
且可用snapshot通过唯一global head固化，而非引入第二mutable authority。snapshot+suffix
等价仍在实现中；D1、D2-R2、D8-R2、lifecycle soak、synthetic destructive GC与独立Checker
均未运行。
