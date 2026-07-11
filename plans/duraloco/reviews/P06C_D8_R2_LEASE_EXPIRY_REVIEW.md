# P06C D8-R2 lease-expiry workflow review / 租约过期工作流复盘

## Scope / 范围

- Failed job: `2363156.opbs`
- Run: `20260711_p06c_d8_r2_90cb9a9`
- Source commit: `90cb9a9d50dbe8b193e693a69a8836c905ed1de2`
- Preserved manifest: `artifacts/duraloco/P06C/20260711_p06c_d8_r2_90cb9a9/manifest.json`
- Preserved authority: `runs/P06C/20260711_p06c_d8_r2_90cb9a9/training/authority`

这是一次非瞬态D8-R2 terminal failure。失败后没有立即重提同一shape；作业在确认
Floating Committer已经终止且控制进程只会等待超时后由operator终止，完整manifest、日志、
failure tape和authority prefix均被保留。

## Phenomenon / 现象

前两个optimizer transition成功。随后primary learner host与active committer被注入whole-host
failure；standby正确取得fencing epoch 2并提交membership revision 1。第三个optimizer
transition也成功提交，但下一个loop入口的lease renewal以
`CoordinationConflict('expired lease cannot be renewed')`终止。此后没有存活committer，rank-0
chaos controller等待第10个transition，作业不可能自行达到terminal stop，因此operator执行
`qdel 2363156.opbs`，PBS EXIT trap保存了failure manifest。

## Confirmed timeline / 已确认时间线

All timestamps are from `logs/distributed_committer.jsonl` and use the same host wall-clock domain.

| Event | Timestamp | Duration/effect |
|---|---:|---:|
| Initial owner acquired epoch 1 | 1783777475.888 | lease sequence 1 |
| First fence commit + strict replay completed | 1783777478.571 | 2.681 s |
| Transition 1 committed | 1783777517.314 | 24.307 s publish-to-commit |
| Lease renewed | 1783777517.824 | sequence 2 |
| Transition 2 committed after primary executor loss | 1783777543.005 | 18.541 s |
| Whole primary learner host killed | 1783777543.328 | active committer lost |
| Standby acquired epoch 2 | 1783777564.857 | lease sequence 3 |
| Fence commit + strict replay completed | 1783777597.834 | 22.030 s measured stage |
| Membership revision 1 committed | 1783777612.150 | 14.316 s after replay completion |
| Transition 3 committed | 1783777643.529 | 23.502 s publish-to-commit |
| Renewal failed | immediately after transition 3 | acquired lease already expired |

## Root cause / 根因

The loop scheduled renewal relative to the time after activation replay, but did not renew immediately
before an expensive membership transition or work dispatch. On takeover, strict replay consumed about
22 seconds, membership publication/replay consumed another 14 seconds, and redundant prepare/commit
consumed about 24 seconds. The 45-second lease therefore expired across those consecutive authoritative
stages. The existing top-of-loop timer could not run while those synchronous stages were executing.

根因不是CAS、membership authority或prepared-result divergence。它是control-plane liveness
budget错误：代码把“循环入口定时续租”误当成了“昂贵authoritative stage之前仍有完整TTL”。

## Safety assessment / 安全评估

- Epoch 2 was committed before membership and optimizer mutations.
- Membership revision 1 is a single global-head control transition bound to strict failure evidence.
- Three optimizer transitions are present in committed ancestry; all prepared results referenced by
  those commits pass strict replay.
- No second head, mixed parameter/state pair, duplicate proposal consumption, or SQLite surface was
  observed.
- Lease expiry made the current owner unable to renew; it did not grant another writer or rewrite the
  committed prefix.

因此`committed_prefix_safe=true`，但D8 liveness与terminal acceptance失败。

## Repair / 修复

Introduce explicit lease stage guards that force a renewal:

1. immediately after activation/takeover replay (`post_activation`);
2. immediately before a membership control transition (`membership_transition`);
3. immediately before publishing an executable work dispatch (`work_dispatch`).

Each guard emits `lease_stage_guard` telemetry. The normal interval renewal remains as a fallback. This
gives each synchronous authoritative stage a fresh TTL instead of relying on a timer that cannot run
inside that stage. The fixed 6000 ms hedge policy and all numeric/work-order identities remain unchanged.

## Required proof and retry ladder / 必需证明与重试阶梯

Before one new D8 attempt:

1. login-node `py_compile`, `git diff --check`, and `bash -n scripts/miyabi/*.pbs`;
2. targeted 1-node compute gate proving all three guard sites renew and emit their stage identity;
3. full P06C 1-node unit gate;
4. D1-R2 real GPT-2 qualification on the same clean commit;
5. D2-R2 failure qualification on the same clean commit (or strict preserved-evidence reanalysis only
   if the runtime source is unchanged; here runtime source changes, so D2 must rerun);
6. exactly one new D8-R2 attempt.

No same-shape D8 resubmission is authorized before steps 1–5 pass.

## Resolution / 解决结果

The repair commit `cba9f487dcc697a6df7930b22280e4f0d512377b` passed targeted job
`2363213.opbs`, full unit job `2363218.opbs`, D1-R2 `2363228.opbs`, and D2-R2
`2363235.opbs` in order. The single authorized D8 retry `2363242.opbs` then passed ten
optimizer transitions, membership revision one, strict replay, and terminal stop in 528 seconds.
Its committer telemetry contains `post_activation`, `membership_transition`, and `work_dispatch`
lease-stage guards; no expired-renewal exception recurred.

修复提交完成完整的targeted→1-node→2-node阶梯后，唯一一次D8重试`2363242.opbs`通过；
因此本review的retry gate已解除，且没有跳过或重复同shape重试。
