# 运维与排查 / Operations and Troubleshooting

## 中文

验证 run：

```bash
python -m fs_diloco.analysis summary runs/fs_diloco/<RUN_ID> --json
python scripts/agent/verify_baseline_evidence.py runs/fs_diloco/<RUN_ID>
python -m fs_diloco.log.inspect_cli verify \
  --root runs/fs_diloco/<RUN_ID>/authority --run-id <RUN_ID>
```

analysis 先验证 head/frontier/commit prefix，再 fold telemetry。若 latest 缺失或损坏，
authority 校验仍可成功；重新 resume syncer 会从 committed objects 重建 exports。

常见失败：

| 现象 | 检查 |
|---|---|
| `head conflict` | 确认只有一个 M00 syncer；保留 orphan，检查 replay 后是否已提交 |
| proposal 未进入 eligible | 检查 quarantine code、base commit/frontier、payload hash/finite |
| no progress | 检查 learner heartbeat、quorum、staleness 与 pending marker |
| latest 与 head 不同 | 删除 derived latest 后用 exact resume 重建 |
| replay integrity error | 保存 artifact；不要跳过损坏对象或从 listing 猜测状态 |

M00 不声明多 writer fencing、永久 provider loss、exact learner restart 或 authority GC。

## English

Use `analysis summary`, the evidence verifier, and `log.inspect_cli verify` to
validate a run. Analysis verifies the committed prefix before folding
telemetry. Missing or corrupt derived exports do not change authority; exact
resume regenerates them from committed objects.

For head conflicts, confirm the M00 single-writer assumption and replay before
retrying. For rejected proposals, inspect typed quarantine, causal base,
content hash, and finite-value checks. Never bypass a replay integrity error or
infer committed state from a directory listing.

M00 does not claim multi-writer fencing, permanent provider-loss survival,
exact learner restart, or authoritative garbage collection.
