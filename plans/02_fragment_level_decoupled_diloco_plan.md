# Plan 02 — Fragment-level Decoupled DiLoCo Pipeline

## 1. 目标

将当前 `fragment_id = 0` 的 full-model 更新路径升级为真正的 parameter-fragment Decoupled DiLoCo pipeline。该阶段必须实现 per-fragment update、per-fragment version、per-fragment outer optimizer state、per-fragment syncer merge、learner-side fragment adoption，以及可在 Miyabi 上提交的 8 learners + 1 syncer 训练作业。

验收训练规模固定为：

```text
8 learner nodes + 1 syncer node
GPT-2 / WikiText-2
50 local inner optimizer steps per learner update
4 committed global/fragment merge events
PBS wall-time <= 20 minutes
```

## 2. 范围

必须实现：

1. `fragment_index.json`：将 trainable flat parameter vector 切分成多个 fragments。
2. 至少两种 fragment strategy：`full` 和 `balanced_tensor`。
3. 验收配置使用 `num_fragments = 4`，确保 4 次 global merge 覆盖 4 个 fragment。
4. learner 每 50 local steps 上传当前 scheduled fragment 的 local parameter value 或 delta。
5. syncer 按 `fragment_id` 独立 selection、quorum、merge、outer optimizer step。
6. syncer 为每个 fragment 单独维护 version 和 outer optimizer state。
7. learner 能拉取并应用 syncer 发布的 fragment weights。
8. 应用 fragment update 后，第一版保守地重置整个 inner optimizer。
9. SQLite schema 支持 fragment metadata。
10. analysis 输出 fragment-level metrics。

暂不强制实现：

1. fine-grained AdamW state reset，仅重置被更新 fragment 的 optimizer state。
2. MoE expert-level fragmentation。
3. FSDP/ZeRO 参数 sharding。
4. 网络传输 tensor；本阶段仍使用 filesystem + safetensors。

## 3. 核心语义

当前 full-vector merge 可以看作：

```text
fragment_id = 0
fragment_size = full_trainable_numel
```

本阶段把它推广为：

```text
flat trainable parameter vector theta
  -> fragment_index: fragment_id -> list of flat slices
  -> fragment local parameter theta[f]
  -> fragment local learner parameter p_i[f]
  -> fragment pseudo-gradient g[f] = theta_syncer[f] - weighted_average_i(p_i[f])
  -> outer_optimizer[f].step(g[f])
```

每个 fragment 独立推进：

```text
fragment_versions(fragment_id=0): 0 -> 1 -> ...
fragment_versions(fragment_id=1): 0 -> 1 -> ...
...
```

全局 `latest.json` 不再只表示一个 monolithic checkpoint，而应能描述每个 fragment 的 latest version：

```json
{
  "format_version": 2,
  "global_merge_event": 4,
  "fragments": {
    "0": {"version": 1, "weight_path": "..."},
    "1": {"version": 1, "weight_path": "..."},
    "2": {"version": 1, "weight_path": "..."},
    "3": {"version": 1, "weight_path": "..."}
  }
}
```

## 4. 新增/修改文件

新增：

```text
fs_diloco/fragment_index.py
fs_diloco/fragment_codec.py
fs_diloco/fragment_scheduler.py
fs_diloco/fragment_mailbox.py
fs_diloco/fragment_merge.py
fs_diloco/schema_migrations.py
configs/fs_diloco_gpt2_wikitext2_8l_fragment_50x4.yaml
scripts/miyabi/run_9node_fragment_gpt2_wikitext2_50x4.pbs
tests/test_fragment_index.py
tests/test_fragment_codec.py
tests/test_fragment_scheduler.py
tests/test_fragment_merge.py
tests/test_fragment_pipeline_smoke.py
```

修改：

```text
fs_diloco/learner.py
fs_diloco/syncer.py
fs_diloco/store.py
fs_diloco/outer_optim.py
fs_diloco/tensor_codec.py
fs_diloco/analysis.py
fs_diloco/config.py
fs_diloco/schema.sql
README.md
docs/design.md
docs/experiments.md
```

## 5. Fragment index 设计

`fragment_index.json` 应写入 shared root：

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
  "fragments": [
    {
      "fragment_id": 0,
      "numel": 31109952,
      "slices": [
        {"param_name": "transformer.wte.weight", "start": 0, "end": 1000, "flat_start": 0, "flat_end": 1000}
      ]
    }
  ]
}
```

`balanced_tensor` 的第一版可以使用 greedy bin packing：

1. 按参数 tensor numel 从大到小排序。
2. 每次把当前 tensor 或 tensor slice 放入当前总 numel 最小的 fragment。
3. 对特别大的 tensor 允许切成多个 contiguous flat slices。
4. 输出每个 fragment 的 total numel。
5. analysis 中报告 max/min/mean fragment size。

验收配置使用 `num_fragments = 4`，因为最终测试只有 4 次 global merge，需要覆盖每个 fragment 一次。

## 6. 文件布局

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
  mailbox/
    learner_000/
      fragment_000_v000001.safetensors
      fragment_000_latest.json
  control/
    latest.json
```

写入规则：

1. tensor 文件仍使用 `safetensors`。
2. learner 先写 `.tmp`，再 atomic rename 为 `.safetensors`。
3. metadata JSON 是 commit marker。
4. syncer 只处理 metadata 已提交且 tensor 文件存在的 update。
5. syncer 发布 fragment weight 时同样使用 tmp + atomic rename。

## 7. SQLite schema 扩展

新增表：

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
    fragment_id INTEGER NOT NULL,
    base_fragment_version INTEGER NOT NULL,
    base_global_merge_event INTEGER NOT NULL,
    local_step_start INTEGER NOT NULL,
    local_step_end INTEGER NOT NULL,
    inner_steps INTEGER NOT NULL,
    tokens_this_update INTEGER NOT NULL,
    train_loss REAL,
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
    staleness_versions INTEGER,
    effective_weight REAL,
    drop_reason TEXT,
    UNIQUE(learner_id, fragment_id, local_step_end, base_fragment_version)
);
```

保留旧表以兼容 `fragment_id=0` full mode。

## 8. Learner 行为

伪代码：

```text
load latest fragment set
reconstruct full model params
reset inner optimizer

while not stopped:
  train 50 local optimizer steps
  fragment_id = scheduler.next(learner_id, local_update_index)
  fragment_tensor = extract_fragment(model_params, fragment_id)
  write fragment_tensor safetensors
  write fragment update metadata JSON
  poll latest fragment pointer
  apply available fragment updates to local model
  reset inner optimizer after any applied fragment
```

第一版 scheduler：

```text
round_robin_global:
  update_index 0 -> fragment 0
  update_index 1 -> fragment 1
  update_index 2 -> fragment 2
  update_index 3 -> fragment 3
```

所有 learners 使用同一 fragment schedule。这样第 1 次 merge 聚合 fragment 0，第 2 次 merge 聚合 fragment 1，第 3 次 merge 聚合 fragment 2，第 4 次 merge 聚合 fragment 3。

## 9. Syncer 行为

伪代码：

```text
initialize fragment_index
initialize fragment weights from model theta_0
initialize per-fragment outer optimizer state

target_fragment = scheduler.next_global_merge_event()
while global_merge_event < 4:
  ingest pending metadata
  eligible = select pending updates where fragment_id == target_fragment
  wait for quorum_min or grace_window
  selected = choose most_recent_per_learner(eligible)
  p_bar = token/staleness weighted average selected local fragment params
  grad = theta_fragment - p_bar
  theta_fragment = outer_optimizer_fragment.step(theta_fragment, grad)
  write fragment weight and outer state
  update SQLite fragment_versions and fragment_updates
  publish latest fragment pointer
  global_merge_event += 1
```

本阶段先保留现有 direct pseudo-gradient semantics：

```text
grad[f] = theta_syncer[f] - weighted_average_i(p_i[f])
```

RDA merge 可以作为后续 option，不作为本阶段验收必须项。

## 10. 配置文件

新增 `configs/fs_diloco_gpt2_wikitext2_8l_fragment_50x4.yaml`：

```yaml
run:
  name: fs_diloco_gpt2_wikitext2_8l_fragment_50x4
model:
  name_or_path: gpt2
  dtype: bfloat16
data:
  dataset_name: wikitext
  dataset_config_name: wikitext-2-raw-v1
  train_split: train
  validation_split: validation
  block_size: 1024
sync:
  num_learners: 8
  mode: fragment
  upload_mode: params
  quorum_min: 4
  quorum_max: 8
  max_staleness_versions: 2
  staleness_lambda: 0.25
  selection_policy: most_recent_per_learner
  stop_after_outer_steps: 4
  scan_interval_seconds: 1.0
  grace_window:
    mode: fixed
    fixed_seconds: 5.0
    max_seconds: 10.0
fragments:
  enabled: true
  strategy: balanced_tensor
  num_fragments: 4
  schedule: round_robin_global
  fragments_per_update: 1
  reset_inner_optimizer_on_fragment_adopt: true
training:
  inner_steps: 50
  micro_batch_size: 1
  gradient_accumulation_steps: 1
  block_size: 1024
  precision: bf16
  reset_on_global_update: true
outer_optimizer:
  name: nesterov
  lr: 0.7
  momentum: 0.9
io:
  tensor_dtype: float32
  atomic_write: true
  sqlite_local_dir: null
wandb:
  enabled: false
```

## 11. PBS 脚本

新增：

```text
scripts/miyabi/run_9node_fragment_gpt2_wikitext2_50x4.pbs
```

要求：

```bash
#PBS -l select=9:mpiprocs=1
#PBS -l walltime=00:20:00
```

rank 0 为 syncer，rank 1–8 为 learners。脚本结束后自动运行：

```bash
python -m fs_diloco.analysis "$RUN_ROOT" --json > "$RUN_ROOT/analysis_summary.json"
python -m fs_diloco.analysis assert-fragment-smoke \
  --run-root "$RUN_ROOT" \
  --expected-learners 8 \
  --expected-global-merge-events 4 \
  --expected-fragment-ids 0,1,2,3 \
  --min-selected-count 4
```

## 12. 测试计划

必须新增测试：

```bash
pytest \
  tests/test_fragment_index.py \
  tests/test_fragment_codec.py \
  tests/test_fragment_scheduler.py \
  tests/test_fragment_merge.py \
  tests/test_fragment_pipeline_smoke.py
```

覆盖：

1. flat vector -> fragments -> flat vector roundtrip。
2. `balanced_tensor` 生成 4 个非空 fragments。
3. 每个 fragment 的 slice 不重叠且覆盖所有 trainable numel。
4. fragment safetensors 写读一致。
5. per-fragment outer optimizer state 可保存/恢复。
6. selection policy 不会跨 fragment 选错 update。
7. fragment version 不会重复 apply。
8. analysis 能统计每个 fragment 的 applied count。

## 13. 最终验收目标

验收作业：

```bash
qsub scripts/miyabi/run_9node_fragment_gpt2_wikitext2_50x4.pbs
```

验收条件：

1. PBS job 使用 9 个 Miyabi-G 节点：1 syncer + 8 learners。
2. PBS wall-time 限制为 20 分钟。
3. 模型为 GPT-2，数据为 WikiText-2。
4. `training.inner_steps = 50`。
5. syncer 成功提交 4 个 global/fragment merge events。
6. 4 个 merge events 覆盖 fragment ids `{0,1,2,3}`。
7. 每个 merge event 的 `selected_count >= quorum_min`，默认至少 4。
8. 至少 8 个 learner 都完成过 heartbeat，且至少 6 个 learner 产生过 fragment update。
9. `control/latest.json` 为 format version 2，并包含 fragment latest pointers。
10. `fragment_versions` 表包含每个 fragment 的 committed version。
11. `fragment_updates` 表中无 corrupt update 被标为 applied。
12. `analysis_summary.json` 存在，并包含 fragment size、fragment merge latency、selected_count distribution、staleness distribution。
13. 作业在 20 分钟内正常退出。

若任一条件失败，验收不通过。

## 14. Codex 实施顺序

1. 先实现 fragment index 和 roundtrip tests。
2. 再实现 fragment tensor codec。
3. 扩展 SQLite schema 和 store API。
4. 修改 syncer：支持 per-fragment selection 和 per-fragment outer optimizer。
5. 修改 learner：支持 fragment scheduler、fragment upload、fragment adoption。
6. 修改 `control/latest.json` format，保持 full mode 兼容。
7. 添加 50x4 配置和 PBS 脚本。
8. 添加 analysis assertions。
9. 先用 local tiny smoke 跑 fragment pipeline。
10. 再提交 Miyabi 9-node 20-minute acceptance job。
