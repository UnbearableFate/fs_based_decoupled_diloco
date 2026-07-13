# DuraLoCo Safety Invariants

这些 ID 是跨阶段稳定的验收接口。下表描述当前实现的含义，并给出至少一个活跃测试 owner；阶段
report/Checker 提供 Miyabi 证据，测试路径本身不等于 PBS 已运行。

| ID | 当前不变量 | 测试 owner |
|---|---|---|
| I-001 | head/frontier/commit/FWO/PFR/capsule 等权威引用的对象必须存在，并通过 canonical key、size 与 digest 验证；坏对象不能静默参与 transition。 | `tests/log/test_replay_prefix.py`, `tests/protocol/test_validation_matrix.py` |
| I-002 | committed head 只命名一条 parent-linked、commit-sequence 连续的 chain；CAS conflict 不能产生两个 committed tip。 | `tests/reference/test_reference_transitions.py`, `tests/log/test_cas_conflict.py` |
| I-003 | 一个 proposal 最多进入一个 committed selected set；consumed、dropped 和 selected terminal state 互斥，learner interval/lineage 不重复。 | `tests/reference/test_double_inclusion.py`, `tests/log/test_commit_crash_matrix.py` |
| I-004 | selected proposal 的 causal base 必须是当前 generation 的 committed ancestor，fragment/version 对应且在 frozen staleness bound 内。 | `tests/protocol/test_validation_matrix.py`, `tests/reference/test_reference_transitions.py` |
| I-005 | 每个 fragment 的 params 和 outer-optimizer state 由同一 commit 产生、共同递增，并与 replay frontier 一致。 | `tests/reference/test_reference_transitions.py`, `tests/log/test_commit_happy_path.py` |
| I-006 | head CAS 是唯一 committed-transition linearization point；prepared、orphan、lost response 和 derived file 都不能单独改变 authority。 | `tests/reference/test_crash_prefixes.py`, `tests/log/test_commit_crash_matrix.py` |
| I-007 | fencing epoch 单调不减；epoch bump/takeover 后旧 owner、旧 membership 或旧 work order 不能推进 head。 | `tests/coordination/test_production_fencing.py`, `tests/distributed_syncer/test_ownership_r2.py` |
| I-008 | recovery 必须等于一个完整 head-reachable committed prefix 的 fold；empty-cache strict、memoized 与 valid snapshot+suffix 的 state/identity 相同。 | `tests/log/test_production_runtime.py`, `tests/lifecycle/test_snapshot_suffix_replay.py` |
| I-009 | 相同 canonical parent/input/decision/optimizer/backend 产生相同 transition identity 和 reference numeric result。 | `tests/reference/test_reference_outer_optim.py`, `tests/reference/test_model_checker_mutants.py` |
| I-010 | head ancestry、retained snapshots、active distributed evidence、pins/acks/capsules、eligible/grace/quarantine/unknown roots 在 GC 中不可回收。 | `tests/lifecycle/test_gc_concurrency.py`, `tests/lifecycle/test_distributed_reachability.py` |
| I-011 | 每个 protocol identity 只映射一个 canonical body/content digest；冲突、不同 redundant result 或自相矛盾 marker fail closed。 | `tests/protocol/test_identities.py`, `tests/distributed_syncer/test_duplicate_equivalence.py` |
| I-012 | proposal/payload key 留在 run namespace，并精确匹配声明 key、ObjectRef、shape、dtype、layout 与 finite-value contract。 | `tests/protocol/test_validation_matrix.py`, `tests/protocol/test_schema_roundtrip.py` |

任何无法解释的 I-003、I-005、I-006、I-007、I-008 或 I-010 违反都是 stop condition；性能、质量和
后续 phase gate 必须关闭，先保存 authority/failure evidence 并执行独立 root-cause review。
