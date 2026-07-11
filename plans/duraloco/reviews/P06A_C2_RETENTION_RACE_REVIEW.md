# P06A C2 Retention/Publication Race Review

## English

PBS `2362087.opbs`, run `20260711_p06a_final_fce378f_c2`, executed the
decomposed CRS on `fce378fcc6d8438045d4a3f54ef78e36d0d50fc8`. The authority path
successfully committed two optimizer transitions and an authoritative stop after
the injected learner SIGKILL/restart. The job nevertheless failed because the
restarted learner began a final interval while the syncer entered terminal
retention cleanup.

`write_update` had atomically published a uniquely named tensor file and was about
to record its size and write the discovery metadata. Concurrent
`cleanup_learner_update_artifacts` classified every tensor without an existing
metadata file as an orphan and deleted it immediately. The learner then failed at
`file_size(tensor_path)` with `FileNotFoundError`. The committed prefix remained
valid, but the runtime exit was correctly treated as failure.

The repair gives unpaired tensor/temp files an explicit default grace interval.
Metadata-bound old pairs remain subject to `keep_last`; only fresh marker-less
objects are protected. This implements the P06A/P07 marker-last lifecycle rule:
absence of a marker during a concurrent scan does not prove an object is an
abandoned orphan. A focused regression creates a fresh unmarked tensor and proves
cleanup leaves it intact; the historical immediate-orphan cleanup test opts into
zero grace.

Qualification order is focused one-node tests, C1, C2, then C9 on the same repaired
clean implementation commit. No C9 job was submitted from the failed candidate.

## 中文

PBS `2362087.opbs`、run `20260711_p06a_final_fce378f_c2` 在提交
`fce378fcc6d8438045d4a3f54ef78e36d0d50fc8` 上运行 decomposed CRS。注入 learner
SIGKILL/restart 后，权威路径已成功提交两个 optimizer transition 与 authoritative stop；
但 job 仍因终止期 retention 与 learner publication 竞争而失败。

`write_update` 已原子发布唯一命名的 tensor 文件，随后正准备读取 size 并写 discovery
metadata。并发的 `cleanup_learner_update_artifacts` 把所有暂时没有 metadata 的 tensor
立即当作 orphan 删除，learner 因而在 `file_size(tensor_path)` 得到
`FileNotFoundError`。committed prefix 保持有效，但 runtime 非零退出被正确判为失败。

修复为未配对 tensor/temp 文件增加显式默认 grace；已有 metadata 的旧 pair 仍按
`keep_last` 清理，只保护新鲜的 marker-less object。这落实 P06A/P07 marker-last 生命周期
规则：并发扫描时 marker 缺失不能证明 object 已废弃。定向回归会创建新鲜未标记 tensor，
证明 cleanup 不删除它；历史“立即删 orphan”测试显式使用零 grace。

同一修复后 clean commit 的资格顺序是 focused one-node、C1、C2、最后 C9。失败 candidate
没有提交 C9 作业。
