# P06 Terminal Wrapper Failure Review

## English

### Failure

PBS `2360503.opbs`, run
`20260711_p06_impl_696babe_gpt2_9n_50x10`, received nine compute nodes but
exited with status 127 after one second. No syncer, learner, model, dataset, or
authority process started. The P06 PBS wrapper delegated to the P05 terminal
script using a relative path before changing from PBS `jobdir` to
`PROJECT_ROOT`; the delegated path therefore did not exist. The failure is a
non-transient workflow error, not algorithm, CUDA, NCCL, storage, or training
evidence.

### Repair and retry discipline

The wrapper now resolves and changes to the explicit clean checkout before any
delegation. A targeted one-node benchmark must reproduce an arbitrary PBS
jobdir and prove delegated-script resolution. After that benchmark, the same
clean repair commit must rerun the full P06 one-node gate and then the two-node
warm-restart gate. Only those three passing same-commit qualifications authorize
one new nine-node attempt. The failed manifest and `qstat -H` allocation record
remain immutable evidence; the failed run supplies no authority head or runtime
timing claim.

## 中文

### 失败

PBS `2360503.opbs`、run
`20260711_p06_impl_696babe_gpt2_9n_50x10` 已获得九个 compute node，但在一秒后
以状态 127 退出。syncer、learner、model、dataset 和 authority 进程均未启动。P06 PBS
wrapper 在从 PBS `jobdir` 切换到 `PROJECT_ROOT` 之前就用相对路径委托 P05 terminal
脚本，因此找不到被委托路径。该失败是非 transient workflow 错误，不构成 algorithm、
CUDA、NCCL、storage 或 training 证据。

### 修复与重试纪律

wrapper 现在先解析并切换到显式干净 checkout，再执行任何委托。必须先用 targeted
单节点 benchmark 从任意 PBS jobdir 证明委托脚本可解析；随后在同一干净修复 commit
上重新运行完整 P06 单节点 gate，再运行双节点 warm-restart gate。只有这三项同 commit
资格全部通过后，才授权一次新的九节点尝试。失败 manifest 与 `qstat -H` allocation
记录保持不可变；失败 run 不提供 authority head 或 runtime timing 主张。
