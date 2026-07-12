# H0 Run and Failure Ledger

This ledger is the persistent operational record for H0. A passing run is not
silently substituted for a failed or superseded attempt. Raw logs, manifests,
JUnit, stage reports, and qstat snapshots remain under `artifacts/duraloco/H0/`.

## Failed runs

| PBS job | Commit | Shape | Result | Root cause and disposition |
|---|---|---|---|---|
| `2369364.opbs` | `cdba623` | one-node static/focused/full | FAIL | Focused 116 passed; full had 467 passed, 1 failed, 1 skipped. The failure was a stale P07 acceptance-count fixture missing A20–A24. Fixture corrected before another qualification. |
| `2369366.opbs` | `edf1761` | one-node static/focused/full | FAIL | Focused 116 passed; full had 467 passed, 1 failed, 1 skipped. The remaining failure was a stale P08 acceptance-count fixture missing A17–A24. Fixture corrected before the first clean qualification. |
| `2369715.opbs` | `df41623` | independent checker | FAIL | Fifteen RED cases failed on `c099adc`, but the original response-loss test passed because the replay still exposed the full commit tuple. The checker also used unsupported manifest purpose `checker`, so this failed attempt has raw/qstat/PBS logs but no manifest. The test was strengthened to inject a suffix-only commit tuple; manifest purpose was changed to `contract`. `2369726.opbs` then passed all 16 RED/GREEN pairs. |

No failed H0 job advanced optimizer authority. The two unit failures were
one-node test-envelope failures. The Checker failure was read-only.

## Superseded passing runs

| PBS job | Commit | Shape | Why superseded |
|---|---|---|---|
| `2369380.opbs` | `173471a` | one-node, 468 passed/1 skipped | Later observational lifecycle byte counters changed the runtime commit. |
| `2369394.opbs` | `173471a` | real GPT-2 D1 | Same reason. |
| `2369417.opbs` | `173471a` | two-node Lustre lock probe | Repeated on final runtime commit. |
| `2369420.opbs` | `173471a` | D2-R2 failover | Repeated on final runtime commit with counter evidence. |
| `2369428.opbs` | `173471a` | nine-node GPT-2/WikiText 50x10 | PASS, but lifecycle reports did not yet archive isolated inventory counters; repeated on `f167a07`. |
| `2369602.opbs` | `ca4fb52` | one-node, 468 passed/1 skipped | Counter isolation was refined after D1 exposed lease-renewal bytes in the inventory window. |
| `2369609.opbs` | `ca4fb52` | real GPT-2 D1 | PASS, but `inventory_payload_bytes_read=988` included the post-inventory lease renewal. The measurement boundary was moved before renewal; no authority behavior changed. |

## Final qualification ladder

| PBS job | Commit | Nodes | Evidence | Result |
|---|---|---:|---|---|
| `2369617.opbs` | `f167a07` | 1 | ruff; forbidden-DB scan; 116 focused; 468 passed/1 skipped full suite | PASS |
| `2369625.opbs` | `f167a07` | 1 | real GPT-2 D1; one optimizer transition; exact capsules; lifecycle inventory payload read 0 | PASS |
| `2369628.opbs` | `f167a07` | 2 | distinct-host Lustre `flock`; blocked while held; acquired after release | PASS |
| `2369629.opbs` | `f167a07` | 2 | D2-R2 executor/committer/host failover; four transitions/four lifecycle cycles; inventory payload read 0 in every cycle | PASS |
| `2369634.opbs` | `f167a07` | 9 | eight learners/LFEs, GPT-2/WikiText-2, 50 local steps × 10 global transitions, two injected recoveries, five lifecycle cycles | PASS |
| `2369726.opbs` | `04e0a86` | 1 | independent 16-case RED/GREEN audit, identity tape, artifact/checksum audit | PASS |

The terminal run took 752 seconds. It completed ten optimizer transitions,
five snapshot/lifecycle cycles, eight exact capsules, 19 committed-lineage
prepared attempts, nine duplicate attempts, and authoritative stop. Maximum
fault recovery was 89.440 seconds. There was no dedicated syncer node and no
error, traceback, or expired-lease terminal event.

## 提要

H0 保留了所有失败与被替代运行，而不是只记录最终成功结果。两个单节点失败均由验收计数
测试夹具陈旧导致；首次 Checker 失败暴露了 RED 用例不够强以及 manifest purpose 配置错误。
修复后，最终同一 runtime commit `f167a07` 按 1 节点、2 节点、9 节点顺序全部通过，独立
Checker `2369726.opbs` 也通过。完整原始证据位于 `artifacts/duraloco/H0/`。
