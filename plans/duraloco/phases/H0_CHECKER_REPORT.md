# H0 Independent Checker Report

verdict: PASS
required_gate_followups: none

## Scope and result

PBS `2369726.opbs` independently checked runtime commit
`f167a07c49339ba42d14f8a5873fe2c8781884d4` using checker commit
`04e0a8634b0e9d7c4cd55c5593081a0ca969a060`. The machine-readable report and
checksums are in
`artifacts/duraloco/H0/20260713_014514_h0_checker_04e0a86/`.

The Checker overlaid the H0 acceptance tests on the P07 basis
`c099adc3c3a99127569a7d9bf38a58547022173c`. All 16 counterexamples failed on
the basis and all 16 passed on H0. They cover committer stop integrity and
cleanup masking, CAS replay, executor-wait lease renewal, bootstrap races,
multi-fragment metadata, grace/lease bounds, prefix/header-only storage,
corrupt discovery, cross-node lock capability, generation-scoped heartbeats,
typed dtype quarantine, and suffix-only mutation resolution.

A deterministic P07 tape produced identical proposal ID, commit IDs, frontier
digest, committed-state digest, and runtime-view digest before and after H0.
This proves the H0 runtime changes did not alter committed identities.

The Checker also audited the final one-node, D1, two-node lock, D2-R2, and
nine-node artifacts. D2's four lifecycle cycles would have read 3,291,023
payload bytes through legacy inventory heads; the new isolated inventory
counter records exactly zero. The two-node probe ran on distinct hosts and
proved exclusion plus post-release acquisition. The D8-R2 run completed ten
optimizer transitions and five lifecycle cycles in 752 seconds, with nine
executor-result-wait renewal heartbeats and a maximum recovery time of 89.440
seconds.

The Checker found no committed-identity drift, second optimizer authority,
embedded database, missing runtime gate, or required follow-up. H0-A01 through
H0-A09 pass and P08 may use `f167a07` as its runtime planning basis. This does
not authorize merging `main`.

## 中文结论

独立 Checker 作业 `2369726.opbs` 返回 `PASS`。16 个 H0 反例在 P07 基线
`c099adc` 上全部失败、在 H0 上全部通过；确定性 P07 tape 的 proposal、commit、frontier、
committed-state 与 view digest 前后完全一致。Checker 同时复核了最终 1 节点、D1、2 节点
锁探针、D2-R2 和 9 节点 50×10 运行。D2 四个 lifecycle cycle 的 inventory payload 读取均为
0；跨节点锁排他成立；9 节点运行完成 10 次 optimizer transition。无 required follow-up，
P08 可从 runtime commit `f167a07` 开始。
