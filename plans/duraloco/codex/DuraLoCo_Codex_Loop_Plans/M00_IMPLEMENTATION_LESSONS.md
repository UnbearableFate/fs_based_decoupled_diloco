# M00 实施经验与后续强制约束

本文件从 M00 双语阶段报告、八次 9-node 失败历史、production replay workflow
review、最终 Maker ladder、独立 Checker 反例和当前实现中提取后续阶段必须执行的
工程约束。它不是背景总结；P05 及之后每个阶段都必须把相关条目映射到 acceptance
ID、测试和 artifact。

## 1. 已验证基线

- 路线基线：M00 corrected archival tip `89ae48aae5956b09fc6685074d3ea0eaea36b816`；
- verified implementation：`c052438a3cfe5e16c3b154fc842f32dcd61ec6ff`；
- corrected persistence/checker commit：`c4753d4eea0be58f68b3f888c83212778fff3a3f`；
- final Checker：PBS `2359355.opbs`，`PASS`，`required_gate_followups: none`；
- terminal baseline：GPT-2/WikiText-2，1 syncer node + 8 learner nodes，50×10，
  7m24s；strict CPU replay 6.177s，strict GPU replay 6.875s，process-local
  memoized replay 0.013s，steady-state post-CAS replay 4.835–4.940s。

这些值是 observed baseline，不是永久阈值。后续 phase 必须在相同 workload shape
下报告相对变化，不得把 M00 的通过直接复用为新功能的通过。

## 2. Schema、identity 与语义一致性

M00 发现并修复了三类“局部实现看似合理、组合后违反协议”的错误：

1. outer optimizer state 合法包含 `I64` step tensor，而 proposal payload 仍只能使用
   冻结的浮点 dtype；parser 必须按对象语义验证，不能用一个 dtype allowlist 覆盖所有对象；
2. 缺失的 optional identity field 必须从 canonical body 中省略，不能写成 `null`；
3. same-base interval overlap 必须在 reference、catalog、production prepare 和 replay
   全部执行同一语义，不能只在事后 replay 才发现。

因此后续阶段必须：

- schema change 同时覆盖 absent/null/unknown/conflicting 字段和对象类型特定 dtype；
- identity-bearing optional field 使用唯一 canonical omission 规则；
- reference/runtime/prepare/replay/recovery 调用共享 policy kernel，或用 adversarial
  digest/mutant 证明等价；
- cheap committed interval/epoch/base rejection 必须发生在大 payload 读取之前，prepare
  时再次验证，CAS conflict/epoch change 后完整 revalidate/reselect。

## 3. Learner publication 与 backpressure

真实 9-node 运行证明，小型 fixture 会隐藏 proposal flood 和 multi-GB payload 延迟。
learner 在提交一个 interval 后若只等待一次短 scan，会从同一 committed base 连续产生
proposal。正确约束是：

- learner 可先发布 content-addressed immutable payload，再发布 discovery marker；marker
  是 publication 的最后一步；
- learner 不得拥有 `conditional_replace`、head key 或任何 head-CAS 能力；测试应检查这条
  权限边界，而不是禁止 learner 使用 storage backend；
- publication 后必须等待 committed successor、authoritative stop 或明确 no-progress policy，
  不得因为一次空 listing/短 timeout 就开始重叠 interval；
- M00 的 bfloat16 proposal transport 与 float32 aggregation/committed params 是已验证组合；
  改变 dtype 必须有新 implementation identity、numeric evidence 和 I/O 对照；
- P07 GC 必须把“payload 已发布、marker 尚未发布”的对象视为 in-flight/grace candidate，
  不能立即删除。

## 4. 大对象验证与 replay

M00 的主要性能失败不是算法，而是同一 immutable tensor 被反复读取、hash、finite-check、
重新发布和 replay。后续不得回退到这种路径：

- bounded/reference fixture 可用 dependency-free scalar validator；production tensor 必须走
  vectorized validator。路由依据 workload/object type，不只依据文件扩展名；
- 每个 candidate 的 read/SHA/structural/finite validation 应产生 typed validated result，
  scan/load/publish 在一次事务尝试中复用它，不得重复读取；
- 独立 candidate 可并发验证，但 quarantine 写入和最终 selection order 必须确定；
- learner-side immutable publication 已经是合法 authority preparation；syncer 对同一
  ObjectRef 只验证/观察，不得串行重写和 fsync 新副本；
- process-local memoization key 必须是完整 ObjectRef `(key, sha256, size)`，只在完整 replay
  成功后更新，永不序列化、永不成为 authority；
- fresh open、takeover、explicit verify、CAS conflict/response ambiguity、head jump、cache
  清空或 corruption suspicion 必须从 empty cache 做 strict replay；
- memoized 与 strict replay 对每个 prefix 必须 digest 相等。corruption test 必须创建新的
  content-addressed ObjectRef，不能原地修改已缓存 identity 来制造不可能场景。

## 5. Coordination 对 M00 replay 的约束

P05 引入 lease/fencing 时，不能把 verified-object cache 或未提交 selection 跨 ownership
边界继承。standby takeover 的第一步必须是 empty-cache strict replay；只有完成 head、完整
manifest/causal chain 和所有新 ObjectRef 验证后，才可进入 memoized steady state。

TTL/renew/takeover 预算必须显式考虑 M00 observed strict replay（约 6–7s）、steady-state
post-CAS replay（约 5s）和真实 storage tail；这些值只能用于初始测量假设，不能替代 clock
skew/safety proof。fencing safety 必须来自单调 epoch 和 head-CAS，不得依赖“通常 replay
比 TTL 快”。

## 6. Telemetry 与昂贵重试纪律

单一 `global_interval_seconds` 曾把 catalog、validation、publication、CAS、replay 和 export
混在一起，导致连续局部猜测。后续每次 transaction/coordination 必须至少记录：

- catalog/cheap rejection；
- proposal observation/read/SHA/validation；
- aggregation 与 outer step；
- successor immutable publication；
- lease acquire/renew/fence/control transition；
- head CAS；
- strict/memoized post-CAS replay；
- materialized export/adoption/stop observation。

任何必需 9-node terminal attempt 因非 transient 根因失败后，不得立即用另一处局部修改
重提同 shape 作业。必须先：

1. 保留 authority timeline、stage timing、qstat 和完整失败 manifest；
2. 写 workflow/root-cause review，区分 confirmed 与 unknown；
3. 用最小 1-node benchmark 或 preserved-prefix replay 证伪/证实瓶颈；
4. 在同一 clean commit 重新通过 1-node 和 2-node 资格验证；
5. 只提交一次新的 9-node terminal retry。

若新 retry 再次失败，重复 review，而不是扩大并发重试。所有 deliberate operator
termination 也必须记录真实 exit status、有效 committed prefix 和 `parent_run_id`。

## 7. 后续阶段映射

| 经验 | 强制落地阶段 |
|---|---|
| head jump 后 empty-cache strict replay、cache 不跨 owner | P05、P11 |
| committed-successor backpressure、same-base interval | P05、P06 |
| marker-last immutable publication 与 in-flight grace | P06、P07 |
| strict/memoized/snapshot+suffix digest 等价 | P05、P07、P08、P11 |
| typed validated result、无重复大对象 I/O | P05、P06、P08 |
| object-type dtype 与 canonical optional identity | P05–P08、可选 P09 |
| 分阶段 telemetry 与 terminal retry review | P05–P12、可选 P09 |
| distinct ObjectRef corruption fixture | P05、P07、P11 |
| bfloat16 transport/float32 committed state non-regression | P06、P08、P10、P12 |

## 8. Checker 必须保留的 M00 反例

后续 Checker 至少选择与本阶段相关的一项重放：

- writer 在 immutable publication 中被 kill，下一次 listing omission，恢复后 proposal
  仍恰好 logical inclusion 一次；
- stale process 持有旧 verified cache，观察 head jump 与损坏 successor 时 fail closed，
  cache 不被污染，恢复后 strict/memoized digest 相等；
- same-base proposal flood 在 payload read 前被拒绝；
- absent optional identity field 与显式 `null` 不产生相同 canonical identity；
- learner 可 immutable publish，但无法调用 head CAS；
- distinct successor outer-state corruption 在 fresh strict replay 中被检测。
