# P05 Coordination Timing and Safety Review

## English

### Safety boundary

The lease object is observational and affects only takeover liveness. It cannot
authorize an optimizer or stop mutation. The sole safety boundary is the
committed head: an owner becomes writable only after an epoch-bump control
transition wins the head CAS, and every later optimizer/stop transition binds
the exact owner ID, owner session, fencing epoch, parent head, request ID, and
request digest. A paused old owner therefore fails the parent-head/epoch check
even if its wall clock or cached lease still appears favorable.

### Initial production budget

The production defaults are a 45 s lease TTL, 10 s renewal interval, 15 s
renewal margin, 2 s maximum clock-skew liveness envelope, and 2 s standby poll.
They are based on the preserved M00 observations, not on an assumption that
replay is always fast:

- strict CPU replay: 6.177 s;
- strict GPU replay: 6.875 s;
- steady post-CAS replay: 4.835–4.940 s;
- head-CAS tail in the terminal baseline: 0.007–0.012 s;
- complete steady transition interval: 16.4–18.0 s.

The conservative renewal-margin comparison is `6.875 + 0.012 + 2.0 = 8.887
s`, below the 15 s margin by 6.113 s. The 10 s scheduler interval also leaves
35 s until nominal expiry after a successful renewal. These comparisons are
liveness engineering only: exceeding them can delay or forfeit a renewal, but
cannot let an old epoch commit.

The initial worst-case takeover target is bounded as an operational objective
by residual lease TTL plus skew, strict replay, and the observed head-CAS tail:
`45 + 2 + 6.875 + 0.012 = 53.887 s`, with a 75 s terminal assertion envelope
to cover polling and storage variation. This is not a safety proof and it does
not permit time-based commits.

### Current measured contract

PBS `2360251.opbs`, run
`20260711_p05_failover_2a8ab75_2node`, exercised real cross-node Lustre
coordination with a deliberately short 2.0 s test TTL and 0.1 s skew envelope.
The standby waited 1.689 s after observing the lease, completed an empty-cache
strict replay in 0.055 s, committed epoch 2, rejected the resumed epoch-1
optimizer and stop mutations, committed exactly one optimizer transition, and
replayed one authoritative stop. Both nodes reported identical committed-state
and runtime-view digests, zero split-brain commits, and zero double inclusion.

The short-TTL result validates the mechanism and stage measurement. It does not
replace the production GPT-2 replay baseline.

PBS `2360276.opbs`, run
`20260711_p05_impl_82dbec1_gpt2_9n_50x10`, supplied that production measurement.
The active renewed through lease sequence 3, was SIGKILLed after optimizer
transition 2, and the standby committed epoch 2 after 68.722 s. Its combined
fence-commit plus empty-cache strict-replay stage took 22.053 s. Steady post-CAS
replay after takeover remained 4.813–4.925 s and head CAS 0.008–0.020 s. The
authoritative stop stage took 49.380 s over the full 80-proposal prefix and
committed sequence 13 with optimizer count 10.

The takeover stayed inside the predeclared 75 s RTO envelope. The stop-stage
measurement exceeds the 45 s lease TTL, so the TTL is not presented as a bound
on every control operation. If another contender acquires during such a long
operation, the two epoch/control CAS attempts race on the same head and only one
wins; the loser strictly replays. Thus this tail can affect liveness and which
owner records stop, but not split-brain safety. The observed terminal result was
epoch 2 standby ownership, one stop control transition, 10 optimizer transitions,
zero split brain, and zero double inclusion.

### Independent Checker conclusion

PBS `2360301.opbs` independently confirmed this safety boundary and its timing
attribution. Its novel corrupt-observational-lease counterexample failed closed,
preserved committed epoch-1 authority, then allowed a valid epoch-2 takeover and
rejected the stale epoch-1 stop. The Checker verdict is `PASS` with no required
follow-up; this closes P05-A09 without turning any clock comparison into commit
authority.

## 中文

### 安全边界

lease 对象只是观测性对象，只影响接管活性，不能授权 optimizer 或 stop mutation。
唯一安全边界是 committed head：owner 只有在 epoch-bump control transition 赢得
head CAS 后才可写；之后每个 optimizer/stop transition 都绑定精确的 owner ID、
owner session、fencing epoch、parent head、request ID 与 request digest。因此，暂停后
恢复的旧 owner 即使本地时钟或缓存 lease 看似仍有利，也会在 parent-head/epoch 检查处
失败。

### 初始生产预算

生产默认值为 45 秒 lease TTL、10 秒续约间隔、15 秒续约 margin、2 秒最大时钟偏差
活性包络，以及 2 秒 standby poll。它们绑定 M00 保留的实测值，而不是假设 replay
总是很快：

- strict CPU replay：6.177 秒；
- strict GPU replay：6.875 秒；
- 稳态 post-CAS replay：4.835–4.940 秒；
- terminal baseline 的 head-CAS tail：0.007–0.012 秒；
- 完整稳态 transition interval：16.4–18.0 秒。

保守续约 margin 比较为 `6.875 + 0.012 + 2.0 = 8.887` 秒，比 15 秒 margin 少
6.113 秒。成功续约后，10 秒调度间隔距离名义过期仍有 35 秒。这些比较只用于活性
工程：超过预算可能延迟或失去续约，但不能让旧 epoch 提交。

初始最坏接管目标把剩余 TTL、skew、strict replay 和实测 head-CAS tail 相加：
`45 + 2 + 6.875 + 0.012 = 53.887` 秒；terminal assertion 使用 75 秒包络容纳
poll 与存储波动。它不是安全证明，也不允许基于时间直接提交。

### 当前实测 contract

PBS `2360251.opbs`、run `20260711_p05_failover_2a8ab75_2node` 在真实跨节点
Lustre 上使用 2.0 秒测试 TTL 和 0.1 秒 skew 包络。standby 在观察 lease 后等待
1.689 秒，以空 cache 完成 0.055 秒 strict replay，提交 epoch 2，拒绝恢复的 epoch-1
optimizer 与 stop mutation，恰好提交一个 optimizer transition，并重放一个权威
stop。两个节点的 committed-state/runtime-view digest 相同，split brain 与 double
inclusion 均为零。

短 TTL 结果验证了机制和分阶段测量，但不能替代生产 GPT-2 replay baseline。

PBS `2360276.opbs`、run `20260711_p05_impl_82dbec1_gpt2_9n_50x10` 给出了生产
测量。active 续约到 lease sequence 3，在 optimizer transition 2 后被 SIGKILL；
standby 在 68.722 秒后提交 epoch 2。其 fence commit 加空 cache strict replay 阶段
耗时 22.053 秒。接管后稳态 post-CAS replay 为 4.813–4.925 秒，head CAS 为
0.008–0.020 秒。覆盖完整 80-proposal prefix 的权威 stop 阶段耗时 49.380 秒，最终
提交 sequence 13，而 optimizer count 为 10。

takeover 满足预先声明的 75 秒 RTO 包络。stop 阶段实测超过 45 秒 TTL，因此 TTL
不被宣称为所有 control operation 的耗时上界。如果另一个 contender 在长操作期间
acquire，两个 epoch/control CAS 会在同一 head 上竞争，只有一个成功，失败方严格
replay。因此该 tail 会影响活性以及由哪个 owner 记录 stop，但不会破坏 split-brain
安全。terminal 实测最终为 epoch 2 standby owner、一个 stop control transition、
10 个 optimizer transition、零 split brain、零 double inclusion。

### 独立 Checker 结论

PBS `2360301.opbs` 独立确认了上述安全边界及 timing 归属。其新构造的观测性 lease
损坏反例 fail closed，保持 committed epoch-1 authority 不变；随后有效 epoch-2
takeover 成功，过期 epoch-1 stop 被拒。Checker verdict 为 `PASS`，没有 required
follow-up；因此 P05-A09 已关闭，且任何时钟比较都没有被提升为 commit authority。
