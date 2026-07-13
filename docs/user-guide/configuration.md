# 配置参考

配置由 `fs_diloco/config.py` 的 dataclass schema 解析。未知 section 或 key 直接报错；相对路径
相对 repository root 解析，`run.shared_root` 与 `data.cache_dir` 解析后必须仍位于项目根目录内。
运行时 `--run-id`、`--shared-root`、`--num-learners` 可覆盖相应字段；最终 resolved config 应随
artifact 一起保存。

## Section 总览

| Section | 主要字段 | 当前语义 |
|---|---|---|
| `run` | `name`, `run_id`, `shared_root`, `log_level` | run identity 与共享目录；run ID 未给定时生成 |
| `init` | `resume`, `resume_version`, `run_generation`, `allow_overwrite_existing_run` | 初始化/代际；generation 必须非负 |
| `model` | `name_or_path`, `dtype`, `compile`, synthetic sizes | Hugging Face 或 `synthetic-tiny` 模型 |
| `data` | dataset/split/block/cache/`streaming` | 数据输入；training block size最终与这里一致 |
| `sync` | learners、quorum、staleness、grace、stop gate | proposal 选择与全局 transition 终止条件 |
| `coordination` | lease TTL/renew/margin/skew/poll | fenced owner 的时间安全约束 |
| `liveness` | heartbeat/stale/dead/no-progress/quorum | 观测与故障判定参数 |
| `training` | inner steps、batch、accumulation、precision、seed | learner 本地训练 |
| `inner_optimizer` | AdamW 参数、scheduler、reset | learner 私有 optimizer |
| `outer_optimizer` | SGD/Nesterov/AdamW-style 参数 | committed global optimizer |
| `io` | tensor dtype、hash、retention、cleanup wait | payload 编码与旧路径保留设置 |
| `learner` | polling、adoption、inner-state policy | 新 frontier 的采用方式 |
| `fragments` | enabled/strategy/count/schedule/materialize | full 或 balanced-tensor fragment |
| `failure_sim` | jitter/skip/crash probability | 旧 smoke fault injection；不是 H0 chaos 证据 |
| `wandb` | enabled/mode/entity/group/tags | observational telemetry |

默认值直接以 `fs_diloco/config.py` 为准；实验配置应显式写出会影响 identity、数值和故障时序的
字段，避免默认值漂移。

## 强制校验

`resolve_config()` 当前强制：

- `sync.staleness_lambda == 0.2`；
- `sync.selection_policy == oldest_pending`；
- `coordination.enabled == true`；
- TTL、renew interval、renew margin 均为正，`renew_interval <= renew_margin < TTL`；
- `min(grace.fixed_seconds, grace.max_seconds) < TTL - renew_margin`；
- clock skew 非负，standby poll 为正；
- fragment 模式每次只允许 1 个 fragment，schedule 只允许 `round_robin_global`，strategy 只允许
  `full` 或 `balanced_tensor`；
- adoption policy 只允许 `reset_all`、`reset_updated_fragment`、`preserve`；
- retention count 非空时至少为 1，cleanup wait 非负。

这些校验是运行前的必要条件，不等于组合已经通过 Miyabi 资格验证。修改 lease/grace、quorum、
fragment layout、optimizer、dtype 或 redundancy policy 后，需要重新建立对应证据。

## D8-R2 合格基线

`configs/duraloco_milestone_gpt2_8node_50x10.yaml` 的关键值：

```yaml
model: {name_or_path: gpt2, dtype: bfloat16}
data: {dataset_name: wikitext, dataset_config_name: wikitext-2-raw-v1, block_size: 128}
sync:
  num_learners: 8
  quorum_min: 4
  quorum_max: 8
  max_staleness_versions: 2
  staleness_lambda: 0.2
  selection_policy: oldest_pending
  stop_after_outer_steps: 10
coordination:
  lease_ttl_seconds: 45.0
  renew_interval_seconds: 10.0
  renew_margin_seconds: 15.0
  max_clock_skew_seconds: 2.0
training: {inner_steps: 50, micro_batch_size: 1, gradient_accumulation_steps: 1}
outer_optimizer: {name: nesterov, lr: 0.7, momentum: 0.9}
io: {tensor_dtype: bfloat16, compute_sha256: true}
```

replication factor、execution mode (`warm_standby` / `active_active` / `hedged`) 和 hedge delay 是
distributed committer CLI 参数，不在 YAML 中。H0 D8-R2 使用 factor 2 和固定 6000 ms hedge。

## 容易误解的字段

- `data.streaming=true` 目前不能作为真正端到端 streaming reducer 或低内存训练的证据；P08
  才负责 profile 和实现对应数据路径。
- `io.keep_last_*` 属于早期 materialized output 保留设置；DuraLoCo authority 的 lifecycle
  retention 由 committed log、snapshot、pin/ack/capsule 和 reachability/GC 契约决定。
- `init.resume_version=latest` 不能使 `latest.json` 成为 authority。DuraLoCo resume 必须打开 head 并
  strict replay；跨 generation 只能显式 warm start，不能导入旧 consumption/sequence authority。
- `failure_sim` 的概率故障不是确定性 failure schedule，也不能替代阶段 fault matrix。
- W&B、CSV、JSONL、heartbeat 都是 observational；删除它们不能改变 committed state。
