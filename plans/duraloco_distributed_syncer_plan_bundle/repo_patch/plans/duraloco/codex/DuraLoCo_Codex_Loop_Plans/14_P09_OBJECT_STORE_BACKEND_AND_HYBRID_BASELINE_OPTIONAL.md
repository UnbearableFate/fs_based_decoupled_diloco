---
plan_id: "P09"
title: "Optional Object-Store Backend for Distributed Syncer and Hybrid Baseline"
status: "optional_deferred"
date: "2026-07-11"
repository: "https://github.com/UnbearableFate/fs_based_decoupled_diloco"
planning_basis_branch: "resolve_from_P12_completed_commit"
planning_basis_commit: "resolve_only_after_explicit_user_opt_in"
target_branch: "codex/duraloco-p09-distributed-object-store"
depends_on:
  - "P12"
  - "explicit_user_opt_in"
required_skill: "miyabi-development"
execution_mode: "single-writer maker + independent checker"
automatic_progression: false
agent_decision_gates: []
human_approval_gates:
  - "启动本阶段"
  - "真实public cloud credentials/cost"
---

# P09 — Optional Object-Store Backend for Distributed Syncer and Hybrid Baseline

## 1. 阶段使命

在用户显式选择后，将P06B–P12的FWO/PFT、membership/ownership、floating commit、lifecycle和D8主路径移植到S3-compatible storage，并与POSIX/Lustre和hybrid placement做一致性/性能比较。本阶段不是required route，也不能回退到1S+8L中心式架构作为主实现。

## 2. 必须保持的分散式契约

- D8/D8-R2仍无专用syncer；
- LFE prepare-only，Floating Committer fenced conditional commit；
- object store listing只discovery；
- immutable objects + conditional head/manifest是authority；
- same FWO duplicate determinism和at-most-once logical commit；
- membership/ownership committed；
- snapshot/reachability/GC/capsule适配；
- empty local state recovery；
- CRS只作reference baseline。

## 3. 范围

### 3.1 必须完成（仅在启动后）

- [ ] S3 semantic backend与capability probe；
- [ ] conditional head/manifest update；
- [ ] multipart marker-last publication；
- [ ] request identity/response-loss/multipart recovery；
- [ ] FWO/PFT/final transition D1/D2/D8；
- [ ] R2 duplicate/reconfiguration；
- [ ] snapshot/reachability/GC semantics；
- [ ] MinIO local E2E；
- [ ] POSIX vs object-store state/digest equivalence；
- [ ] hybrid payload/control placements；
- [ ] provider cost/request/latency telemetry；
- [ ] optional public-cloud probe only after approval。

### 3.2 明确不做

- 不用ETag替代content SHA；
- 不依赖strong listing correctness；
- 不引入metadata database；
- 不在无approval时使用真实credentials或付费资源；
- 不因object store特性创建第二authority；
- 不自动启动本阶段。

## 4. 执行循环

### Loop 1 — Backend contract

实现immutable put/get/range/list-discovery、conditional head、marker-last和typed errors；与POSIX通用contract对照。

### Loop 2 — Multipart与response loss

覆盖payload complete before marker、abort/cleanup、SDK setup/publish failures、same ID conflict和idempotent retries。

### Loop 3 — Distributed protocol on MinIO

D1/D2验证FWO/PFT/floating committer/R2/fencing/listing omission/empty local recovery；状态digest与POSIX一致。

### Loop 4 — D8 object/hybrid baseline

8 learner nodes、0 dedicated syncer、50×10；比较POSIX、object-control+object-payload、POSIX-control+object-payload等预注册placements。

### Loop 5 — Lifecycle与optional public cloud

snapshot/GC/capsule和cost metrics；public cloud仅经approval、最小probe、secrets redaction。

## 5. 验收标准

- [ ] P09-A01：S3 backend通过通用storage contract；
- [ ] P09-A02：conditional head competing writers单winner；
- [ ] P09-A03：listing omission不影响correctness；
- [ ] P09-A04：multipart/marker crash-response-loss可恢复；
- [ ] P09-A05：mutation request identity正确区分重试/独立请求；
- [ ] P09-A06：ETag不被当作SHA；
- [ ] P09-A07：MinIO D1/D2 distributed path通过；
- [ ] P09-A08：POSIX/object state和core digests一致；
- [ ] P09-A09：R2 duplicate/reconfiguration通过；
- [ ] P09-A10：snapshot/reachability/GC/capsule通过；
- [ ] P09-A11：D8 8 learner nodes、0 dedicated syncer、50×10 terminal；
- [ ] P09-A12：hybrid baselines独立配置测量；
- [ ] P09-A13：bytes/requests/cost/latency/GPU interference完整；
- [ ] P09-A14：active surface无SQLite/metadata DB；
- [ ] P09-A15：empty local directory replay/takeover严格；
- [ ] P09-A16：cloud dependency为optional pinned extra；
- [ ] P09-A17：无approval/credentials时安全skip；
- [ ] P09-A18：non-transient D8 failure遵守retry discipline；
- [ ] P09-A19：Checker审核secrets/cost/list assumptions；
- [ ] P09-A20：report/checksums/clean commit一致。

## 6. 启动规则

仅在用户明确选择P09后创建分支。未启动时所有A项标记not-applicable，不影响P12 required route完成。
