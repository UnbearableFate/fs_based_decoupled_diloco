---
phase: "PXX"
status: "PASS|PASS_WITH_FOLLOWUPS|BLOCKED"
verified_commit: "<git sha>"
date: "YYYY-MM-DD"
topology_mode: "central_reference|distributed_r1|distributed_r2"
checker_verdict: "PASS|PASS_WITH_FOLLOWUPS|BLOCKED"
---

# DuraLoCo Phase Report / 阶段报告

## 1. Executive summary / 摘要

- Phase and branch:
- Verified clean commit:
- Dependency commit/digest:
- Topology: C1/C2/C9/D1/D2/D8/D8-R2
- Required gates passed:
- Required follow-ups:
- Final verdict:

## 2. Scope and changes / 范围与变更

- Implemented loops:
- Files/modules changed:
- Protocol/schema changes:
- Explicit non-goals preserved:
- ADRs created/closed:

## 3. Topology and role placement / 拓扑与角色

| Node/host | learner session | GPU/rank | LFE session | owned fragments | backup fragments | committer epoch | CPU affinity/NUMA |
|---|---|---|---|---|---|---|---|

- `dedicated_syncer_nodes`:
- CRS role: authoritative / shadow / offline / absent
- Membership epoch and digest:
- Ownership digest and replication factor:
- Controller mode/version:

## 4. Authority and capability audit / 权威与能力审计

- Current head and committed prefix digest:
- Head-CAS call sites:
- Committer lease/fencing evidence:
- Learner capability audit:
- Executor prepare-only audit:
- CRS no-write evidence for distributed generation:
- Local-state deletion/recovery evidence:
- SQLite/embedded-DB forbidden-surface scan:

## 5. Correctness and equivalence / 正确性与等价

| Evidence | CRS/reference | distributed/optimized | Result |
|---|---|---|---|
| selected proposal IDs/weights | | | |
| aggregate digest | | | |
| parameter digest | | | |
| outer-state digest | | | |
| transition/frontier digest | | | |
| replay digest | | | |

- Duplicate execution results:
- Same-FWO divergence tests:
- Proposal logical inclusion audit:
- Parameter/outer-state pairing audit:
- Learner boundary adoption audit:

## 6. Fault and recovery evidence / 故障与恢复

| Fault ID | injection point | expected | observed | RTO | RPO/lost work | artifact |
|---|---|---|---|---|---|---|

- Executor/committer/whole-node failures:
- Response-loss/CAS ambiguity:
- Epoch/head jump/stale owner:
- Snapshot/capsule/GC concurrency:
- False suspicion:
- Retry-lock lineage:

## 7. Performance and interference / 性能与干扰

- Workload and tokens:
- Wall time / useful-token goodput:
- GPU step time/MFU proxy:
- LFE CPU cores/utilization/RSS:
- NUMA and affinity verification:
- Lustre bytes/read/write/metadata ops:
- publish→plan→prepare→commit→adopt p50/p95/p99:
- Hedge/duplicate rate and wasted CPU/I/O:
- Node-hours and GPU-hours:
- C9 vs D8/D8-R2 comparison:

## 8. Lifecycle / 生命周期

- Snapshot IDs and covered heads:
- strict/memoized/snapshot+suffix equivalence:
- Reachability root summary:
- GC dry-run/apply summary:
- Learner capsule and restore points:
- Object/byte growth:

## 9. Acceptance evidence map / 验收证据

| Acceptance ID | status | command/run ID | artifact path | checker note |
|---|---|---|---|---|

## 10. Attempts and lineage / 尝试与谱系

Include pass, fail, inconclusive, queued-cancelled, deliberate termination and retry attempts. Record `parent_run_id`, commit, config digest, queue/job IDs and structured reason.

## 11. Known limitations and research interpretation / 限制与研究解释

- Supported claims:
- Bounded/conditional claims:
- Rejected/negative findings:
- Threats to validity:
- Related-work wording affected:

## 12. Checker report / 检查者报告

- Independent counterexample:
- Commands rerun:
- Evidence sampled independently:
- Findings:
- Verdict:

## 13. Next action / 下一步

- `STATE.yaml.next_action`:
- Next phase dependency digest:
- Blockers or approvals:
- Milestone commit created, not auto-merged: yes/no
