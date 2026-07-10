# 配置 / Configuration

## 中文

关键字段：

| 字段 | 语义 |
|---|---|
| `run.run_id` | 逻辑 run 身份 |
| `run.shared_root` | 所有共享 authority、proposal 与 exports 的根 |
| `init.resume` | 从当前 committed head 精确恢复 syncer |
| `init.resume_version` | M00 仅允许 `latest` |
| `init.run_generation` | protocol generation；warm start 必须使用新 generation |
| `sync.quorum_min/max` | 每次 transition 的 learner quorum |
| `sync.max_staleness_versions` | global/fragment causal staleness 上限 |
| `sync.staleness_lambda` | 冻结为 `0.2` |
| `sync.selection_policy` | 冻结为 `oldest_pending` |
| `sync.stop_after_outer_steps` | committed transition 目标数 |
| `fragments.enabled/strategy/num_fragments` | full 或 balanced fragment layout |
| `io.keep_last_global_versions` | derived checkpoint retention；不影响 authority |

未知 key 一律 fail closed。所有相对路径解析到 project root 内；data cache 也不得越界。

## English

`run_id` and `run_generation` identify the authority namespace. Exact resume
opens the current head and only accepts `resume_version: latest`. A warm start
must use a fresh generation. Quorum and staleness bounds are explicit;
`staleness_lambda` is frozen at `0.2` and selection at `oldest_pending`.
Retention fields apply only to derived checkpoints. Unknown keys fail closed,
and configured project paths may not escape the project root.
