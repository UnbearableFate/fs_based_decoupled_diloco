# Plan 02 - Fragment-level Decoupled DiLoCo Pipeline

## 1. 目标

基于当前项目的实际状态，实现 Decoupled DiLoCo for Resilient Distributed Pre-training 所需的 fragment feature：把现有 `fragment_id = 0` 的 full-model filesystem DiLoCo 原型，升级为真正的 parameter-fragment Decoupled DiLoCo 原型。

当前项目已经具备 milestone 1 的核心能力：

- learners 把完整 trainable flat parameter vector 当作单一 logical fragment 上传；
- syncer 使用 SQLite、quorum、grace window、token/staleness weighting、显式 flat-vector outer optimizer 和 `control/latest.json`；
- Miyabi PBS 脚本只把 MPI 当作跨节点 process launcher，不把 MPI/NCCL 用作训练数据面。

本阶段必须在保留这些约束的基础上增加 fragment pipeline：

- 不引入 `torch.distributed`、NCCL、RPC、Ray、DeepSpeed、FSDP 或 PCCL 数据面；
- 继续使用 shared filesystem + `safetensors`；
- full-model mode 必须保持兼容，现有 configs/tests 不应被破坏；
- Miyabi login node 只做控制面工作，runtime validation 必须在 PBS compute/debug 或 batch 节点上执行。

最终验收不再只是 4 个 merge event 的 smoke。最终必须能够提交正式的 9-node GPT-2/WikiText-2 fragment run：8 learners + 1 syncer，每个 learner 训练 5000 local optimizer steps，并且通过日志、metrics、SQLite、analysis 观察到训练正常进行。

## 2. 参考语义

参考资料：

- Decoupled DiLoCo paper: <https://arxiv.org/abs/2604.21428> and <https://arxiv.org/html/2604.21428v1>
- Google DeepMind blog: <https://deepmind.google/blog/decoupled-diloco/>
- PCCL Async DiLoCo docs: <https://pccl.primeintellect.ai/DiLoCo%20-%20Distributed%20Low-Communication/AsyncDiloco>
- PCCL async example: <https://github.com/PrimeIntellect-ai/pccl/blob/main/python/examples/nanogpt_diloco/async_diloco.py>
- Miyabi skill: <https://github.com/UnbearableFate/miyabi-development>

需要保留的设计点：

1. learners 相互独立、异步运行；慢 learner 或失败 learner 不能阻塞其他 learners。
2. learners 与 central syncer 交换 parameter fragments，而不是 full-model all-reduce。
3. syncer 基于 minimum quorum 和 grace window 前进。
4. merge weight 必须考虑 tokens 和 staleness。
5. outer pseudo-gradient 符号保持当前项目语义：

```text
grad[f] = theta_syncer[f] - weighted_average_i(p_i[f])
theta_syncer[f] = outer_optimizer_f.step(theta_syncer[f], grad[f])
```

6. 每个 fragment 独立 versioning。fragment merge 的 staleness 必须基于该 fragment 的 version，而不能只基于 global merge event。
7. PCCL async example 只作为 separate outer params、pseudo-gradients 和 overlap 的概念参考。本项目不引入 PCCL transport。

阶段性简化：

- RDA 不是本 fragment milestone 的默认要求。先保持当前 direct pseudo-gradient merge，但实现 merge-method 接口，后续可无侵入添加 RDA。

## 3. 旧版计划的问题

旧版 `02_fragment_level_decoupled_diloco_plan.md` 不应原样实现，主要问题如下：

1. 直接把 `latest.json` 改成 `format_version = 2`，没有兼容层。当前 `FORMAT_VERSION = 1` 同时用于 param index 和 update metadata，不能全局改含义。
2. 配置片段包含当前 dataclass 不认识的 key。当前 loader 会静默忽略 unknown key，因此 `sync.mode`、顶层 `fragments`、`training.reset_on_global_update` 不会可靠生效。
3. 没有明确保留 full mode。
4. syncer 伪代码把 `target_fragment` 放在 loop 外，如果照写会固定 merge 同一个 fragment。
5. 写了 `analysis assert-fragment-smoke`，但当前 `analysis.py` 没有 subcommand。
6. 没有定义 fragment state 如何 materialize 成 full checkpoint，影响 analysis、lm-eval export 和后续工具链。
7. 没有把最终正式验收定为 5000-step GPT-2/WikiText-2 job；现有 full-mode 5000-step run 曾经能看到训练推进，但最终是 `no_progress_timeout`，这不能作为 fragment feature 的 clean acceptance。

## 4. 兼容性契约

full mode 保持默认可用：

```yaml
fragments:
  enabled: false
```

full mode 保持当前 `latest.json` 结构：

```json
{
  "format_version": 1,
  "run_id": "...",
  "version": 47,
  "weight_path": ".../weights/global_v000047.safetensors",
  "optim_path": ".../optim/outer_v000047.safetensors",
  "param_index_path": ".../control/param_index.json",
  "total_seen_tokens": 588185600
}
```

fragment mode 使用 discriminated payload，不复用 `FORMAT_VERSION` 表达 latest layout 语义：

```json
{
  "format_version": 1,
  "latest_kind": "fragment",
  "latest_layout_version": 2,
  "run_id": "...",
  "version": 50,
  "global_merge_event": 50,
  "param_index_path": ".../control/param_index.json",
  "fragment_index_path": ".../fragments/fragment_index.json",
  "materialized_weight_path": ".../weights/global_v000050.safetensors",
  "total_seen_tokens": 655360000,
  "fragments": {
    "0": {
      "version": 13,
      "weight_path": ".../fragments/weights/fragment_000/v000013.safetensors",
      "optim_path": ".../fragments/optim/fragment_000/v000013.safetensors",
      "updated_at_global_merge_event": 49
    },
    "1": {
      "version": 13,
      "weight_path": ".../fragments/weights/fragment_001/v000013.safetensors",
      "optim_path": ".../fragments/optim/fragment_001/v000013.safetensors",
      "updated_at_global_merge_event": 50
    }
  }
}
```

兼容规则：

1. `latest_kind` 缺失或为 `"full"` 时，按当前 full mode 解释。
2. `latest_kind == "fragment"` 时，learner 按 fragment pointers apply，并用 `global_merge_event` 判断是否有新发布。
3. fragment latest 中保留 `version`，作为 `global_merge_event` 的兼容 alias，避免现有 summary 工具完全失效。
4. fragment mode 必须定期和最终 materialize full checkpoint，使现有 export/eval 工具能读取最终模型。

## 5. 范围

必须实现：

1. 从现有 `param_index.json` 构建 `fragment_index.json`。
2. fragment strategies：
   - `full`：一个 fragment 覆盖完整 trainable vector，用于兼容；
   - `balanced_tensor`：按 tensor numel 降序，把完整 tensor greedily 分配到当前最小 fragment。
3. per-fragment upload tensor 和 metadata。
4. per-fragment SQLite metadata。
5. syncer 按 fragment 独立 selection、quorum、staleness、merge、outer optimizer state。
6. learner-side fragment adoption。
7. 第一版采用保守策略：apply 任意 fragment 后重置整个 inner optimizer/scheduler。
8. fragment-aware metrics 和 analysis assertions。
9. Miyabi 1-node debug、2-node debug、9-node short smoke、9-node 5000-step 正式脚本和配置。

本阶段不做：

1. 默认 RDA merge。
2. 只重置被更新 fragment 对应的 AdamW state。
3. sub-tensor fragmentation。
4. MoE expert fragmentation。
5. 网络 tensor transport。
6. `torch.distributed`、NCCL、FSDP 或 PCCL 数据面集成。

## 6. Fragment Index

路径：

```text
shared_root/fragments/fragment_index.json
```

schema：

```json
{
  "format_version": 1,
  "strategy": "balanced_tensor",
  "num_fragments": 4,
  "total_numel": 124439808,
  "source_param_index_path": ".../control/param_index.json",
  "fragments": [
    {
      "fragment_id": 0,
      "numel": 38597376,
      "size_bytes_float32": 154389504,
      "slices": [
        {
          "param_name": "transformer.wte.weight",
          "param_offset": 0,
          "param_numel": 38597376,
          "flat_start": 0,
          "flat_end": 38597376,
          "shape": [50257, 768],
          "dtype": "torch.float32"
        }
      ]
    }
  ]
}
```

规则：

1. `full` 输出一个覆盖所有 trainable slices 的 fragment。
2. `balanced_tensor` 将 trainable tensors 按 `numel` 降序排序，每次放入当前总 numel 最小的 fragment。
3. 本阶段不切分单个 tensor。切 tensor 属于 sub-tensor fragmentation，后续再做。
4. 验收 configs 中每个 fragment 必须非空。
5. slices 必须不重叠，并且精确覆盖所有 trainable numel。
6. analysis 报告 fragment min/max/mean size 和 imbalance ratio。

新增文件：

```text
fs_diloco/fragment_index.py
tests/test_fragment_index.py
```

## 7. 文件布局

full mode 路径保持不变。

fragment mode 新增：

```text
shared_root/
  fragments/
    fragment_index.json
    weights/
      fragment_000/v000000.safetensors
      fragment_000/v000001.safetensors
      fragment_001/v000000.safetensors
      ...
    optim/
      fragment_000/v000000.safetensors
      fragment_001/v000000.safetensors
  updates/
    pending/
      learner_000/
        update_<uuid>_fragment_000.params.safetensors
        update_<uuid>_fragment_000.meta.json
  weights/
    global_v000000.safetensors
    global_v000050.safetensors
  control/
    param_index.json
    latest.json
    stop.json
```

第一版不需要 per-learner mailbox。learner 只 poll `control/latest.json`，保留当前项目契约。只有当 `latest.json` poll 成为可测瓶颈时再增加 mailbox。

atomicity：

1. tensor 文件通过现有 atomic writer helper 写入。
2. metadata JSON 仍然是 commit marker。
3. syncer 只 ingest metadata 已提交且 tensor 文件存在的 update。
4. fragment weight 和 optimizer state 持久化后，才 atomic publish `latest.json`。

## 8. Config 变更

在 `fs_diloco/config.py` 增加：

```python
@dataclass
class FragmentSection:
    enabled: bool = False
    strategy: str = "full"
    num_fragments: int = 1
    schedule: str = "round_robin_global"
    fragments_per_update: int = 1
    reset_inner_optimizer_on_fragment_adopt: bool = True
    materialize_full_every_events: int | None = None
```

在 `Config` 增加：

```python
fragments: FragmentSection = field(default_factory=FragmentSection)
```

同时收紧 config parsing：

1. unknown top-level section 应该 `ValueError`。
2. known section 中的 unknown key 也应该 `ValueError`。
3. 更新或验证现有 YAML，确保 strict parsing 不破坏当前 configs。

重要修正：

- 保留 `inner_optimizer.reset_on_global_update`。
- 不新增 `training.reset_on_global_update`。
- 不新增 `sync.mode`；fragment mode 由 `fragments.enabled` 控制。

新增/更新 configs：

```text
configs/fs_diloco_tiny_fragment_local.yaml
configs/fs_diloco_gpt2_wikitext2_1l_fragment_debug.yaml
configs/fs_diloco_gpt2_wikitext2_8l_fragment_50x4.yaml
configs/fs_diloco_gpt2_wikitext2_8l_fragment_5000steps.yaml
```

最终 5000-step config 应镜像现有 full-mode 5000-step config，关键差异如下：

```yaml
run:
  name: fs_diloco_gpt2_wikitext2_8l_fragment_5000steps
sync:
  num_learners: 8
  quorum_min: 4
  quorum_max: 8
  max_staleness_versions: 2
  stop_after_outer_steps: 50
training:
  inner_steps: 100
  max_local_steps: 5000
fragments:
  enabled: true
  strategy: balanced_tensor
  num_fragments: 4
  schedule: round_robin_global
  fragments_per_update: 1
  reset_inner_optimizer_on_fragment_adopt: true
  materialize_full_every_events: 10
```

## 9. Fragment Codec

新增：

```text
fs_diloco/fragment_codec.py
```

核心函数：

```python
extract_fragment(flat: torch.Tensor, fragment_index: dict, fragment_id: int) -> torch.Tensor
scatter_fragment(flat: torch.Tensor, fragment_index: dict, fragment_id: int, fragment_tensor: torch.Tensor) -> torch.Tensor
load_fragment_into_model(model, fragment_tensor, param_index, fragment_index, fragment_id)
save_fragment_update(path, fragment_tensor, dtype)
load_fragment_update(path, device)
save_fragment_weight(path, fragment_tensor)
load_fragment_weight(path, device)
materialize_full_from_fragments(fragment_tensors, fragment_index, total_numel)
```

fragment safetensors 使用单一 key：

```text
fragment_params
```

full-mode update 文件继续使用：

```text
local_params
```

测试覆盖：

1. full flat vector -> fragments -> full flat vector round trip；
2. fragment update safetensors read/write 一致；
3. loading one fragment 只更新该 fragment 对应的 flat slices。

## 10. Scheduler

新增：

```text
fs_diloco/fragment_scheduler.py
```

第一版 scheduler：

```text
round_robin_global:
  event/update index 0 -> fragment 0
  event/update index 1 -> fragment 1
  event/update index 2 -> fragment 2
  event/update index 3 -> fragment 3
  event/update index 4 -> fragment 0
```

规则：

1. learner 用 local update index 选择上传 fragment。
2. syncer 必须在每个 merge loop 内基于当前 `global_merge_event` 计算 target fragment。
3. 对 `num_fragments = 4` 且 `stop_after_outer_steps = 50`，初始化后预期最终版本为：

```text
fragment 0: v0 -> v13
fragment 1: v0 -> v13
fragment 2: v0 -> v12
fragment 3: v0 -> v12
```

## 11. SQLite Schema

现有 tables 保留给 full mode。fragment mode 新增 tables：

```sql
CREATE TABLE IF NOT EXISTS fragments (
    fragment_id INTEGER PRIMARY KEY,
    strategy TEXT NOT NULL,
    numel INTEGER NOT NULL,
    size_bytes INTEGER NOT NULL,
    slices_json TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS fragment_versions (
    fragment_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    global_merge_event INTEGER NOT NULL,
    weight_path TEXT NOT NULL,
    optim_path TEXT NOT NULL,
    created_at REAL NOT NULL,
    num_updates INTEGER NOT NULL,
    total_update_tokens INTEGER NOT NULL,
    total_seen_tokens INTEGER NOT NULL,
    outer_optimizer TEXT NOT NULL,
    status TEXT NOT NULL,
    notes TEXT,
    PRIMARY KEY (fragment_id, version)
);

CREATE TABLE IF NOT EXISTS fragment_updates (
    update_id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL,
    hostname TEXT,
    fragment_id INTEGER NOT NULL,
    base_fragment_version INTEGER NOT NULL,
    base_global_merge_event INTEGER NOT NULL,
    local_step_start INTEGER NOT NULL,
    local_step_end INTEGER NOT NULL,
    inner_steps INTEGER NOT NULL,
    tokens_this_update INTEGER NOT NULL,
    tokens_since_fragment_load INTEGER NOT NULL,
    num_examples_this_update INTEGER,
    train_loss REAL,
    grad_norm REAL,
    param_norm REAL,
    fragment_norm REAL,
    file_path TEXT NOT NULL,
    file_size_bytes INTEGER,
    sha256 TEXT,
    created_at REAL NOT NULL,
    committed_at REAL NOT NULL,
    ingested_at REAL,
    selected_at REAL,
    applied_at REAL,
    status TEXT NOT NULL,
    selected_by_run TEXT,
    applied_fragment_version INTEGER,
    applied_global_merge_event INTEGER,
    staleness_fragment_versions INTEGER,
    staleness_global_events INTEGER,
    effective_weight REAL,
    drop_reason TEXT,
    UNIQUE(learner_id, fragment_id, local_step_end, base_fragment_version)
);

CREATE INDEX IF NOT EXISTS idx_fragment_updates_status
  ON fragment_updates(status);
CREATE INDEX IF NOT EXISTS idx_fragment_updates_target
  ON fragment_updates(fragment_id, status, base_fragment_version);
CREATE INDEX IF NOT EXISTS idx_fragment_versions_event
  ON fragment_versions(global_merge_event);
```

store 行为：

1. full mode 继续使用 `updates` 和 `global_versions`。
2. fragment mode 使用 `fragment_updates` 和 `fragment_versions`。
3. superseded dropping 必须 fragment-aware：只 drop 同一个 learner、同一个 fragment 的更旧 pending update，不能 drop 其他 fragment 的 pending update。
4. staleness filtering 使用：

```text
current_fragment_version - base_fragment_version <= max_staleness_versions
```

5. `global_merge_event` 用于排序和 analysis，不作为 fragment staleness 的主计数。

## 12. Learner 行为

full mode 保持当前行为。

fragment mode 伪代码：

```text
wait for param_index.json
wait for fragment_index.json
load latest.json
if latest_kind == fragment:
  load all fragment v0 weights
  materialize or scatter into local model
  last_loaded_fragment_versions = latest.fragments[*].version
reset inner optimizer

local_update_index = 0
while not stopped:
  train config.training.inner_steps local optimizer steps
  fragment_id = schedule(local_update_index, num_fragments)
  base_fragment_version = last_loaded_fragment_versions[fragment_id]
  base_global_merge_event = last_loaded_global_merge_event
  fragment_tensor = extract_fragment(flatten_trainable_params(model), fragment_id)
  write fragment update tensor
  write fragment update metadata
  poll latest.json
  apply every fragment with version > last_loaded_fragment_versions[fragment_id]
  if any fragment applied:
    reset entire inner optimizer and scheduler
  local_update_index += 1

before final stopped heartbeat:
  poll latest.json one last time
  apply available fragments
```

fragment update metadata：

```json
{
  "format_version": 1,
  "update_kind": "fragment",
  "run_id": "...",
  "update_id": "learner_000_00000100_f000_...",
  "learner_id": "learner_000",
  "fragment_id": 0,
  "base_fragment_version": 3,
  "base_global_merge_event": 12,
  "local_step_start": 0,
  "local_step_end": 100,
  "inner_steps": 100,
  "tokens_this_update": 1638400,
  "tokens_since_fragment_load": 6553600,
  "train_loss": 3.9,
  "fragment_norm": 123.4,
  "file_path": ".../update_<uuid>_fragment_000.params.safetensors",
  "file_size_bytes": 154389504,
  "created_at": 0.0,
  "committed_at": 0.0
}
```

heartbeat 增加：

```json
{
  "last_loaded_global_version": 50,
  "last_loaded_global_merge_event": 50,
  "last_loaded_fragment_versions": {"0": 13, "1": 13, "2": 12, "3": 12},
  "last_adopted_fragments": [0, 1]
}
```

如果本阶段不扩展 `learners` SQLite table，analysis 可以直接读取 heartbeat JSON 做 fragment adoption assertions。

## 13. Syncer 行为

full mode 保持当前行为。

fragment mode initialization：

```text
load model
build param_index
build fragment_index
flatten theta_0
for each fragment:
  theta_f = extract_fragment(theta_0, fragment_id)
  outer_state_f = init_outer_state(theta_f)
  write fragment weight v0
  write fragment outer state v0
  insert fragments and fragment_versions rows
publish latest_kind=fragment, global_merge_event=0
materialize full global_v000000.safetensors
```

merge loop：

```text
global_merge_event = latest event
while not stop:
  target_fragment = schedule(global_merge_event, num_fragments)
  current_fragment_version = fragment_versions[target_fragment]

  ingest heartbeats
  ingest fragment metadata

  eligible = pending fragment_updates where:
    fragment_id == target_fragment
    current_fragment_version - base_fragment_version <= max_staleness_versions

  selected = most_recent_per_learner(eligible)
  wait until quorum_min or grace deadline
  cap selected to quorum_max

  load selected fragment tensors p_i[f]
  alpha_i = normalize(tokens_this_update_i / (1 + staleness_lambda * fragment_staleness_i))
  p_bar = sum_i alpha_i * p_i[f]
  grad = theta_f - p_bar
  theta_f, outer_state_f = outer_optimizer_step(theta_f, grad, outer_state_f)

  new_fragment_version = current_fragment_version + 1
  new_global_merge_event = global_merge_event + 1
  write fragment weight/state
  insert fragment_versions row
  mark selected fragment_updates applied
  drop superseded pending updates for same learner and same fragment
  drop stale pending updates for this target fragment
  publish latest_kind=fragment
  materialize full checkpoint when configured
  global_merge_event = new_global_merge_event
```

terminal behavior：

1. `stop_after_outer_steps = 50` 表示 50 个 global fragment merge events，不是每个 fragment 50 次。
2. 达到 target 时 syncer 应 clean stop，`reason = "stop_after_outer_steps"`。
3. 如果 finite learners 已结束但 target 未达成且不能 quorum，只有显式配置 terminal drain 时才允许 lower-quorum final step。最终验收不应依赖 terminal drain。

## 14. Analysis 和 Metrics

扩展 `syncer_metrics.csv`：

```text
global_merge_event
fragment_id
fragment_version
selected_count
total_update_tokens
fragment_staleness_min
fragment_staleness_mean
fragment_staleness_max
fragment_read_seconds
fragment_aggregation_seconds
outer_step_seconds
publish_seconds
materialize_full_seconds
stale_updates_dropped
```

扩展 `learner_metrics.csv`：

```text
fragment_id
base_fragment_version
last_loaded_fragment_versions_json
fragment_norm
fragment_adopt_count
```

扩展 `update_manifest.csv`：

```text
update_kind
fragment_id
base_fragment_version
base_global_merge_event
```

保持现有 analysis 用法：

```bash
python -m fs_diloco.analysis "$RUN_ROOT" --json
```

新增 subcommands，同时保留旧 positional form：

```bash
python -m fs_diloco.analysis summary "$RUN_ROOT" --json
python -m fs_diloco.analysis assert-fragment-smoke \
  --run-root "$RUN_ROOT" \
  --expected-learners 8 \
  --expected-global-merge-events 4 \
  --expected-fragment-ids 0,1,2,3 \
  --min-selected-count 4
python -m fs_diloco.analysis assert-fragment-5000 \
  --run-root "$RUN_ROOT" \
  --expected-learners 8 \
  --expected-local-steps 5000 \
  --expected-global-merge-events 50 \
  --expected-fragment-ids 0,1,2,3 \
  --min-selected-count 4
```

JSON summary 必须包含：

```json
{
  "latest_kind": "fragment",
  "global_merge_event": 50,
  "fragment_versions": {"0": 13, "1": 13, "2": 12, "3": 12},
  "fragment_sizes": {"min": 0, "max": 0, "mean": 0, "imbalance_ratio": 0.0},
  "fragment_merge_counts": {"0": 13, "1": 13, "2": 12, "3": 12},
  "selected_count_distribution": {},
  "fragment_staleness_distribution": {},
  "learner_local_steps": {},
  "learner_fragment_adoption": {},
  "loss_summary": {},
  "stop_reason": "stop_after_outer_steps"
}
```

## 15. PBS 脚本

新增：

```text
scripts/miyabi/run_1node_fragment_debug.pbs
scripts/miyabi/run_2node_fragment_debug.pbs
scripts/miyabi/run_9node_fragment_gpt2_wikitext2_50x4.pbs
scripts/miyabi/run_9node_fragment_gpt2_wikitext2_5000steps.pbs
```

沿用现有 MPI launcher pattern：

```bash
mpirun \
  --mca mpi_abort_print_stack 1 \
  --report-bindings \
  --bind-to core \
  -np "$NNODES" \
  /usr/bin/env "${MPI_ENV_ARGS[@]}" \
  bash -lc '...'
```

不要把 `mpirun -x` 与 `OMPI_MCA_mca_base_env_list` 混用。

提交修改过的 PBS 脚本前，在 login node 只运行 shell syntax check：

```bash
bash -n scripts/miyabi/*.pbs
```

不要在 `miyabi-g*` login nodes 上运行 training、pytest、torch imports、transformers imports、data preprocessing、`torchrun` 或 `mpirun`。

最终 5000-step script：

```bash
#PBS -N fsdiloco_frag_gpt2_5k
#PBS -q regular-g
#PBS -W group_list=xg24i002
#PBS -l select=9:mpiprocs=1
#PBS -l walltime=02:00:00
```

rank layout：

```text
rank 0: syncer
rank 1-8: learner_000 ... learner_007
```

`mpirun` 结束后脚本必须运行：

```bash
"$PYTHON_BIN" -m fs_diloco.analysis summary "$SHARED_ROOT" --json \
  | tee "$LOG_ROOT/summary.json"

"$PYTHON_BIN" -m fs_diloco.analysis assert-fragment-5000 \
  --run-root "$SHARED_ROOT" \
  --expected-learners 8 \
  --expected-local-steps 5000 \
  --expected-global-merge-events 50 \
  --expected-fragment-ids 0,1,2,3 \
  --min-selected-count 4
```

## 16. 测试

新增或更新：

```text
tests/test_config.py
tests/test_fragment_index.py
tests/test_fragment_codec.py
tests/test_fragment_scheduler.py
tests/test_fragment_store.py
tests/test_fragment_merge.py
tests/test_fragment_analysis.py
tests/test_fragment_pipeline_smoke.py
```

覆盖：

1. unknown config keys 会失败，而不是静默忽略。
2. `full` fragment strategy 与当前 full-vector 行为一致。
3. `balanced_tensor` 生成指定数量的非空 fragments。
4. fragment slices 精确覆盖所有 trainable numel。
5. fragment extraction/scatter round trip。
6. fragment safetensors read/write。
7. per-fragment outer optimizer state 可保存/恢复。
8. selection 按 target fragment 过滤。
9. supersession dropping 只影响 same learner + same fragment。
10. fragment staleness 使用 per-fragment versions。
11. learner adoption 只 apply 新 fragment version，不重复 apply。
12. analysis assertions 能拒绝缺失 fragment、低 quorum、corrupt applied update、缺失 materialized checkpoint 和 `no_progress_timeout`。

runtime tests 不能在 Miyabi login nodes 上运行。

## 17. Validation Ladder

在 `miyabi-g*` login node：

1. 静态文件审查。
2. `bash -n scripts/miyabi/*.pbs`。
3. 仅可做不 import torch/transformers/datasets 的 syntax checks。

在 1-node PBS compute/debug：

1. focused unit tests（如果环境可运行）；
2. tiny synthetic fragment smoke；
3. 1 learner + syncer GPT-2/WikiText-2 small-step debug。

在 2-node PBS compute/debug：

1. launcher validation；
2. one syncer + one learner distributed placement；
3. 确认 logs 显示两个节点参与且 run 完成。

在 9-node PBS batch：

1. short fragment smoke：

```text
8 learners + 1 syncer
GPT-2 / WikiText-2
inner_steps = 50
stop_after_outer_steps = 4
fragments = 4
```

2. final formal run：

```text
8 learners + 1 syncer
GPT-2 / WikiText-2
training.max_local_steps = 5000
training.inner_steps = 100
sync.stop_after_outer_steps = 50
fragments.enabled = true
fragments.strategy = balanced_tensor
fragments.num_fragments = 4
```

## 18. 最终验收条件

fragment feature 只有在正式 5000-step job 通过后才算完成。

命令：

```bash
qsub scripts/miyabi/run_9node_fragment_gpt2_wikitext2_5000steps.pbs
```

必须满足：

1. PBS job 使用 9 个 Miyabi-G nodes：1 syncer + 8 learners。
2. job shell exit code 为 0。
3. `stop.json.reason == "stop_after_outer_steps"`。
4. `latest.json.latest_kind == "fragment"`。
5. `latest.json.global_merge_event == 50`。
6. `latest.json.fragments` 包含 fragment ids `0,1,2,3`。
7. 对 4 fragments、50 events 的 round-robin，fragment versions 符合预期：两个 fragments 到 `v13`，两个 fragments 到 `v12`，且都从 `v0` 初始化。
8. `fragment_versions` 表每个 fragment 都有 committed rows。
9. `fragment_updates` 表中没有 corrupt update 被标为 `applied`。
10. 每个 merge event 的 `selected_count >= 4`。
11. 8 个 learners 都写过 heartbeat。
12. 8 个 learners 都达到 `local_step >= 5000`。
13. failure simulation 关闭时，8 个 learners 都产生 fragment updates。
14. learner heartbeats 或 logs 能证明 learners 在 fragment 发布后发生过 fragment adoption。
15. learner training losses 全程 finite。
16. 最后 10 个 learner update losses 相比最初 10 个 update losses 没有明显发散；analysis 应报告这个比较，不能只靠手动看日志。
17. syncer logs 中无 `error`、`no_progress_timeout` 或 uncaught exception。
18. `analysis_summary.json` 存在，且包含 fragment sizes、merge counts、selected-count distribution、fragment-staleness distribution、learner local steps、learner adoption summary 和 loss summary。
19. 最终 global merge event 对应的 materialized full checkpoint 存在。
20. 现有 full-mode configs 和 tests 仍然可用。

4-event smoke 只是正式验收前的 gate，不能单独算 fragment feature 完成。

## 19. 实施顺序

1. 增加 config 支持：
   - `FragmentSection`；
   - unknown-key validation；
   - 更新 configs。
2. 增加 `RunPaths` fragment paths。
3. 实现 `fragment_index.py` 和测试。
4. 实现 `fragment_codec.py` 和测试。
5. 实现 `fragment_scheduler.py` 和测试。
6. 扩展 schema/store，增加 fragment tables 和测试。
7. 扩展 merge selection：fragment filtering、fragment staleness、fragment-aware supersession。
8. 修改 syncer：
   - full vs fragment mode 分支；
   - 初始化 fragment weights/states；
   - 在 loop 内计算 target fragment；
   - 发布 fragment latest；
   - materialize full checkpoints。
9. 修改 learner：
   - full vs fragment mode 分支；
   - 上传 scheduled fragment；
   - adopt newer fragments；
   - adoption 后重置 inner optimizer；
   - 写 fragment-aware heartbeat/metrics。
10. 扩展 analysis：
    - backward-compatible summary；
    - `assert-fragment-smoke`；
    - `assert-fragment-5000`。
11. 增加 tiny local 和 Miyabi debug configs/scripts。
12. 增加 9-node 50x4 smoke config/script。
13. 增加 9-node 5000-step config/script。
14. 在 login node 运行 static checks。
15. 在 1-node compute/debug 验证。
16. 在 2-node compute/debug 验证。
17. 提交 9-node 50x4 smoke。
18. 提交 9-node 5000-step formal acceptance。
19. 审查 logs、DB dumps、metrics 和 W&B/offline summaries。
20. 所有 gate 通过后只报告 ready to merge；没有用户明确授权不要 merge 到 `main`。
