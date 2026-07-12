# DuraLoCo 持久事务日志

## 唯一提交点

```text
authority/runs/<run>/generations/<generation>/control/head.json
```

genesis 通过 create-if-absent 建立。之后每次 optimizer、membership、snapshot pin、fencing epoch bump
或 stop/error control transition 都先发布不可变对象，最后以一次 head conditional replace 提交。
成功 CAS 前的任何对象都不是 committed state；response loss 后必须通过 strict replay 判断 CAS 是否
生效，不能根据本地返回/缓存猜测。

## Transition 顺序

一个 optimizer transition 的逻辑步骤是：

1. 从当前 head 执行 strict replay，得到 immutable RuntimeView；
2. 全量验证 catalog observation，按 frozen policy 选择 proposals；
3. 固化 canonical weights、membership/ownership/fencing 并发布 FWO/input bundle；
4. LFE 发布 marker-last PFR；
5. committer 验证 work order、attempt、outputs 与当前 owner；
6. 写新 params、outer state、commit 和 frontier；
7. 以 expected head version + unique request ID 做 CAS；
8. CAS 成功后才更新 derived `latest.json`/telemetry，失败则丢弃 tentative view。

params fragment 与 outer state 必须由同一个 commit 产生并在 frontier 中配对。scheduler cursor、
consumed proposals、learner lineage、membership revision 和 fencing epoch 也由 prefix fold 重建。

## Strict replay

replay 从 verified head 沿 parent chain 检查连续 commit sequence、frontier digest、ObjectRef 完整性、
proposal causality/lineage/staleness、canonical selection/weight、numeric output、paired state、consumption、
membership/ownership、snapshot/control transition 和 committed state digest。

以下边界必须 `force_full`/empty-cache：fresh open、owner takeover、显式 verify、CAS ambiguity、head jump、
corruption suspicion。一次完整成功 replay 后可在当前进程/owner/session 使用完整 ObjectRef key 的
verified-object memoization；缓存不得跨 owner、序列化或被当成 authority。

CAS conflict 的正确处理是 reload head、strict replay、重新观察/验证/选择并重新计算。不能把旧
selection/PFR 直接套到新 parent，也不能仅修改 identity 伪装成新 transition。

## Snapshot+suffix

snapshot 是 immutable projection，不是第二 head。只有 committed snapshot-pin transition 且 snapshot
的 covered head/frontier/state digest、causal bases 和 embedded objects 全部验证后才可使用。恢复从
snapshot fold suffix，结果必须与完整 strict replay 相同；缺失/损坏/过期/owner mismatch 直接回退。

系统保留两个独立 valid restore base；在第二个 base 出现前，旧 committed prefix object 仍受保护。
snapshot 只减少 covered-prefix 读取，不能省略 suffix 或新 ObjectRef 的完整验证。

## Inspection

```bash
python -m fs_diloco.log.inspect_cli verify \
  --root <shared-root>/authority --run-id <run-id> --generation 0
python -m fs_diloco.log.inspect_cli replay \
  --root <shared-root>/authority --run-id <run-id> --generation 0
python -m fs_diloco.log.inspect_cli orphans \
  --root <shared-root>/authority --run-id <run-id> --generation 0
```

`latest.json`、materialized checkpoint、heartbeat、CSV/JSONL/W&B 和 process-local selection 是派生或
观测数据。删除或损坏这些对象不能改变 replay；若它们与 head 不一致，以 head chain 为准。
