# 故障模型与恢复语义

## 覆盖的故障窗口

当前 fault matrix 覆盖 immutable payload/marker 发布前后 crash、write/CAS/delete response loss、短读/
corruption、delayed listing、committer crash、executor process loss、whole learner-host loss、standby
takeover、membership revision、lifecycle substage failure、snapshot 损坏和 GC 并发重保护。

底层允许 at-least-once request/observation、timeout ambiguity 和 listing omission/reordering。系统依赖
canonical identity、marker-last publication、ObjectRef verification、request ID、strict replay、fencing 和
single head CAS 获得 exactly-once logical inclusion；不假设 exactly-once delivery。

## Fencing 与 takeover

lease 是协调 hint，不能独立授予 optimizer authority。新 owner 必须在 lease 安全失效后取得更高 epoch，
并把 epoch bump 提交到 head chain。旧 epoch owner 的后续 CAS 被拒绝。

H0 参数 `TTL=45s`、`renew interval=10s`、`max clock skew=2s`。若故障发生在任意续租相位，安全
接管等待通常约 37–47 秒。新 owner 随后执行 empty-cache strict replay、membership/selection 重建、
PFR 计算与下一次 CAS，所以端到端最大观测值为 89.44 秒。该值不是 heartbeat detection 时间，也
不是单独 replay benchmark。

缩短 recovery 应优化 expiry 之外的 scan/read/validation/materialization/prepare；任何低于时钟和 lease
安全预算的 takeover 都会破坏 fencing，不能作为性能优化接受。

## Recovery 层级

| 层级 | 恢复内容 | 当前状态 |
|---|---|---|
| Global exact recovery | head-reachable params、outer state、scheduler、membership、consumption | 已实现并由 strict replay/Checker 验证 |
| Snapshot+suffix | 与 strict replay 相同的 global state，减少 covered-prefix reads | 已实现；无效 snapshot 回退 |
| Warm learner restart | 最新 frontier + 新私有 state/session | 支持，明确非 trajectory-exact |
| Exact learner restart | capsule 的完整私有 state + frontier consistency | schema/roundtrip/synthetic continuation 已验证 |
| Automatic failed-member reintegration | D8 whole-member loss 后自动 restore/rejoin | 当前没有该端到端主张 |

## Fail-closed 情况

- ObjectRef size/hash/key、schema/identity、numeric transition 或 parent chain 不一致；
- 同 ID 不同 body，或同 backend 的 duplicate prepared result 不同 digest；
- lease expired、renewal 失败、owner/session/epoch/membership 与 FWO 不匹配；
- CAS 结果不明确而 strict replay 无法证明 committed outcome；
- snapshot/capsule 缺失、损坏、frontier/session 不一致；
- cross-node lock capability 未验证；
- reachability 遇到 unknown/corrupt object 或 GC apply 时 root 已变化。

错误路径应提交 authoritative terminal `error` control transition（仍能持有合法 owner 时），保存 primary
exception，并让 wrapper 失败。derived stop file 只在观察到 committed stop/error 后生成。

## 不覆盖的威胁

不覆盖 Byzantine participant、恶意共享存储、永久丢失已确认 durable object、任意网络分区下可用性、
跨不兼容 backend 的 numeric identity、GPU hardware failure 后自动 exact reintegration 或 operator 手改
authority。这些场景不能通过现有测试推断安全。
