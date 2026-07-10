# 存储布局 / Storage Layout

## 中文

```text
<run-root>/
  authority/
    runs/<run-id>/generations/<generation>/
      control/run-manifest.json
      control/head.json
      immutable/proposals/
      immutable/fragments/
      immutable/commits/
      immutable/frontiers/
  control/latest.json
  control/stop.json
  control/param_index.json
  fragments/fragment_index.json
  weights/                     # derived materializations
  optim/                       # derived materializations
  updates/pending/             # discovery mailboxes
  quarantine/                  # immutable typed observations
  heartbeats/ logs/ metrics/   # observations
```

authority objects 由 P03 storage envelope 保护，读取时校验 size/hash/header。params 与
outer state 是 safetensors；commit/frontier/head 是 canonical JSON。backend opaque
version 只作为 CAS precondition，不进入逻辑 content identity。

只有 head 是可变 authority。所有其它权威对象不可变。普通 run exports 可安全删除并
从 committed prefix 重建。

## English

The authority subtree contains a run manifest, one mutable head, and immutable
proposal, fragment, commit, and frontier objects. Storage envelopes verify
size, hashes, and headers. Parameter and outer-state payloads are safetensors;
control objects use canonical JSON. Backend generation tokens are CAS
preconditions only and never enter logical identities.

Only head is mutable authority. Learner mailboxes, quarantine observations,
materialized checkpoints, heartbeats, logs, and metrics are non-authoritative.
