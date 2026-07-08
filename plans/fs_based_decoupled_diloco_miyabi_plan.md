# FS-based Decoupled DiLoCo for Miyabi: Codex Implementation Plan

Status: implementation specification for a research prototype.
Target executor: Codex with the `miyabi-development` skill installed.
Primary goal: implement a complete repository with PyTorch + Hugging Face training code, a filesystem-backed learner/syncer protocol, syncer-local SQLite metadata, safetensors tensor storage, and PBS launch scripts for Miyabi.

## 1. Fixed design decisions

The first implementation targets GPT-style causal language modeling, with `gpt2` as the default model and WikiText-2 as the default dataset.

The first full Miyabi run uses 9 Miyabi-G GPU nodes:

- 8 learner nodes, one learner process per node, one GPU per learner.
- 1 syncer node, CPU-only process on a Miyabi-G node. The GPU on this node should remain unused in the first version.

The implementation must not depend on `torch.distributed`, NCCL, RPC, Ray, DeepSpeed, FSDP, or PCCL in milestone 1. The communication simulation is:

- large tensors: Lustre/EXAScaler shared filesystem, using `safetensors`;
- control state: syncer-local SQLite database;
- learner-to-syncer notification: JSON metadata files written to the shared filesystem, then ingested by the syncer into SQLite;
- syncer-to-learner publication: shared filesystem `latest.json` pointer plus `safetensors` global checkpoints.

Outer optimizer support required in milestone 1:

- SGD with momentum;
- SGD with Nesterov momentum;
- AdamW-style outer optimizer.

Learners must overwrite the full model when they observe a newer global version and must reset the inner optimizer state after this overwrite.

## 2. External references to use

Codex should use these references when implementing or validating design choices:

- Miyabi system page: https://www.cc.u-tokyo.ac.jp/en/supercomputer/miyabi/system.php
- Decoupled DiLoCo paper: https://arxiv.org/abs/2604.21428 and https://arxiv.org/html/2604.21428v1
- Google DeepMind blog: https://deepmind.google/blog/decoupled-diloco/
- PCCL Async DiLoCo docs: https://pccl.primeintellect.ai/DiLoCo%20-%20Distributed%20Low-Communication/AsyncDiloco
- PCCL async example: https://github.com/PrimeIntellect-ai/pccl/blob/main/python/examples/nanogpt_diloco/async_diloco.py
- User's Miyabi skill: https://github.com/UnbearableFate/miyabi-development

Important Miyabi facts to encode into project assumptions:

- Miyabi-G nodes have one NVIDIA Hopper H100 GPU with 96 GB GPU memory.
- Miyabi provides a Lustre/DDN EXAScaler shared filesystem.
- Miyabi software includes CUDA, NCCL, PyTorch, JAX, TensorFlow, Miniforge, Apptainer, and Singularity Community Edition.
- The `miyabi-development` skill says login nodes are control-plane only. Runtime tests, model loading, training, heavy imports, CUDA work, and distributed launchers must run in PBS interactive/debug or batch compute nodes.

## 3. Research scope and non-goals

This repository is a research prototype, not a production communication system. The implementation should make asynchronous Decoupled DiLoCo behavior observable and debuggable before attempting real RPC or high-performance communication.

Milestone 1 goals:

- independent learners train GPT-2 on WikiText-2;
- learners upload one full-model parameter vector as a single logical fragment;
- syncer aggregates submitted learner states with quorum, grace-window, token-weighting, and staleness policy;
- syncer applies one of the configured outer optimizers;
- syncer publishes new global model versions to the shared filesystem;
- learners asynchronously adopt newer global versions and reset their inner optimizer;
- runs are inspectable through SQLite, JSONL logs, and metric CSV/JSON files;
- PBS scripts can launch 1-node, 2-node, and 9-node variants under Miyabi constraints.

Milestone 1 non-goals:

- no sharded syncer;
- no true parameter-fragment pipeline;
- no RPC service;
- no NCCL or PCCL dependency;
- no FSDP or DeepSpeed;
- no multi-GPU learner;
- no production-grade checkpoint recovery;
- no claim that filesystem throughput represents PS/RPC throughput.

Milestone 2 can add true fragment-level synchronization. The milestone 1 full-model vector is treated as `fragment_id = 0`.

## 4. System architecture

The system has two process types.

Learner process:

1. Load or initialize the model and tokenizer.
2. Load the latest published global model from the shared filesystem.
3. Reset inner optimizer and scheduler.
4. Run `inner_steps` local optimization steps on its WikiText-2 shard.
5. Serialize the current full trainable parameter vector to a `safetensors` update file.
6. Write a metadata JSON commit marker.
7. Poll for newer global versions.
8. If a newer global version exists, overwrite model weights and reset inner optimizer.
9. Continue until syncer publishes stop state or local `training.max_local_steps` is reached.

Syncer process:

1. Initialize shared run directory and syncer-local SQLite database.
2. Initialize global weights and outer optimizer state.
3. Scan learner update metadata commit markers on the shared filesystem.
4. Ingest valid metadata into SQLite.
5. Select pending updates according to quorum, grace window, staleness, and learner liveness policies.
6. Load selected learner parameter vectors from `safetensors`.
7. Compute token/staleness-weighted merge.
8. Convert the merge into an outer pseudo-gradient.
9. Apply configured outer optimizer.
10. Publish new global model version and optimizer state to the shared filesystem.
11. Mark selected updates as applied or dropped in SQLite.
12. Periodically dump SQLite backups and metrics to the shared filesystem.
13. Publish stop state when `sync.stop_after_outer_steps`, `sync.stop_after_global_tokens`, a liveness no-progress timeout, or walltime guard condition is reached.

## 5. Filesystem layout

The shared root must be configurable. Default:

```text
$PROJECT_ROOT/runs/fs_diloco/$RUN_ID/
```

Required layout:

```text
$SHARED_ROOT/
  control/
    latest.json
    latest.tmp.json
    stop.json
    run_config.resolved.yaml
    param_index.json
  weights/
    global_v000000.safetensors
    global_v000001.safetensors
    ...
  optim/
    outer_v000000.safetensors
    outer_v000001.safetensors
    ...
  updates/
    pending/
      learner_000/
        update_<uuid>.params.safetensors
        update_<uuid>.meta.json
      learner_001/
      ...
    processed/
      learner_000/
      learner_001/
      ...
    dropped/
      learner_000/
      learner_001/
      ...
  heartbeats/
    learner_000.json
    learner_000.tmp.json
    learner_001.json
    ...
  db_dumps/
    metadata_<timestamp>_v000000.db
    metadata_<timestamp>_v000001.db
  logs/
    syncer.jsonl
    learner_000.jsonl
    learner_001.jsonl
  metrics/
    syncer_metrics.csv
    learner_metrics.csv
    update_manifest.csv
```

Rules:

- All atomic publication must use write-to-temp-then-rename in the same directory.
- Learner update metadata JSON is the commit marker. The syncer must ignore update tensor files without a matching final `.meta.json`.
- Learner heartbeat JSON files must also use write-to-temp-then-rename. They are liveness hints, not update commit markers.
- `latest.json` is the only global pointer learners poll. Learners should not scan `weights/`.
- SQLite is syncer-local, not placed directly on Lustre in the default configuration.
- The syncer must periodically copy a consistent SQLite backup into `db_dumps/` using the SQLite backup API or a safe copy after checkpointing.

## 6. Tensor format and parameter index

Use `safetensors` for all large tensor files.

The implementation must create a deterministic parameter index at run initialization:

```json
{
  "format_version": 1,
  "model_name_or_path": "gpt2",
  "trainable_only": true,
  "total_numel": 124439808,
  "params": [
    {
      "name": "transformer.wte.weight",
      "shape": [50257, 768],
      "dtype": "torch.float32",
      "numel": 38597376,
      "offset": 0
    }
  ]
}
```

Global model files should store named tensors compatible with `model.load_state_dict(..., strict=False)` where practical. Update files should store a flat tensor for fast aggregation:

```text
update_<uuid>.params.safetensors:
  local_params: flat tensor, dtype configurable, default float32
```

Outer optimizer files should store flat tensors:

```text
outer_v000123.safetensors:
  theta: flat global parameter vector
  momentum: optional, for SGD momentum/Nesterov
  exp_avg: optional, for AdamW-style outer optimizer
  exp_avg_sq: optional, for AdamW-style outer optimizer
  step: int64 tensor or scalar tensor
```

The helper layer must support:

- flatten model parameters to a CPU tensor in deterministic order;
- load a flat tensor into model parameters in deterministic order;
- convert flat global vector to named state dict for saving global weights;
- reconstruct global flat vector from saved global weights;
- round-trip tests.

## 7. Metadata model

SQLite is authoritative for syncer state after ingestion. Learner JSON metadata is an ingestion transport, not the final database.

Required tables:

```sql
CREATE TABLE IF NOT EXISTS run_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS global_versions (
    version INTEGER PRIMARY KEY,
    weight_path TEXT NOT NULL,
    optim_path TEXT NOT NULL,
    created_at REAL NOT NULL,
    num_updates INTEGER NOT NULL,
    total_update_tokens INTEGER NOT NULL,
    total_seen_tokens INTEGER NOT NULL,
    outer_optimizer TEXT NOT NULL,
    status TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS learners (
    learner_id TEXT PRIMARY KEY,
    hostname TEXT,
    pid INTEGER,
    last_seen REAL,
    last_loaded_global_version INTEGER,
    last_local_step INTEGER,
    last_update_id TEXT,
    tokens_per_sec REAL,
    last_heartbeat_path TEXT,
    status TEXT NOT NULL,
    status_reason TEXT
);

CREATE TABLE IF NOT EXISTS updates (
    update_id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL,
    hostname TEXT,
    base_global_version INTEGER NOT NULL,
    local_step_start INTEGER NOT NULL,
    local_step_end INTEGER NOT NULL,
    inner_steps INTEGER NOT NULL,
    tokens_this_update INTEGER NOT NULL,
    tokens_since_global_load INTEGER NOT NULL,
    num_examples_this_update INTEGER,
    train_loss REAL,
    grad_norm REAL,
    param_norm REAL,
    delta_norm REAL,
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
    applied_version INTEGER,
    staleness_versions INTEGER,
    effective_weight REAL,
    drop_reason TEXT,
    UNIQUE(learner_id, local_step_end, base_global_version)
);

CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    actor TEXT NOT NULL,
    event_type TEXT NOT NULL,
    global_version INTEGER,
    learner_id TEXT,
    update_id TEXT,
    payload_json TEXT
);

CREATE TABLE IF NOT EXISTS db_dumps (
    dump_id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    global_version INTEGER NOT NULL,
    path TEXT NOT NULL,
    size_bytes INTEGER
);
```

Update status values:

```text
pending -> selected -> applied
pending -> dropped
selected -> failed -> pending
selected -> dropped
```

Learner status values:

```text
unknown -> active
active -> stale -> dead
active -> stopped
stale/dead -> active
unknown/stale/dead -> stopped
```

Global version status values:

```text
writing -> committed
writing -> abandoned
```

### 7.1 Heartbeat files and liveness DB updates

Learners must publish one heartbeat file per learner:

```text
$SHARED_ROOT/heartbeats/learner_003.json
```

The file is written atomically as `learner_003.tmp.json` followed by `rename()` to `learner_003.json`. Example:

```json
{
  "format_version": 1,
  "run_id": "20260708_120000_fs_diloco_gpt2_wikitext2",
  "learner_id": "learner_003",
  "hostname": "mg1234",
  "pid": 123456,
  "timestamp": 1783500000.123,
  "status": "active",
  "phase": "inner_steps",
  "last_loaded_global_version": 17,
  "last_local_step": 4100,
  "last_update_id": "learner_003_00000041_91d2a9",
  "tokens_per_sec": 945.2
}
```

Syncer liveness behavior:

1. On every scan loop and during the grace window, the syncer reads `heartbeats/*.json`.
2. It ignores heartbeat files with mismatched `run_id`, unsupported `format_version`, malformed JSON, or learner IDs outside `learner_000..learner_{num_learners-1}`.
3. For each valid heartbeat, it upserts `learners` with `hostname`, `pid`, `last_seen = heartbeat.timestamp`, `last_loaded_global_version`, `last_local_step`, `last_update_id`, `tokens_per_sec`, `last_heartbeat_path`, and `status = active`.
4. After ingestion, the syncer computes `age = syncer_walltime - learners.last_seen`.
5. If `age <= liveness.stale_after_seconds`, status remains `active`.
6. If `liveness.stale_after_seconds < age <= liveness.dead_after_seconds`, status becomes `stale`.
7. If `age > liveness.dead_after_seconds`, status becomes `dead`.
8. A later valid heartbeat from a stale or dead learner moves it back to `active`.
9. A learner that observes `stop.json` writes one final heartbeat with `status = stopped`; the syncer preserves `stopped` unless a newer active heartbeat appears.

Default liveness settings:

```yaml
liveness:
  heartbeat_interval_seconds: 30.0
  stale_after_seconds: 120.0
  dead_after_seconds: 300.0
  no_progress_timeout_seconds: 600.0
  quorum_policy: fixed
```

Heartbeat liveness must not make a valid, fully committed update disappear. A committed update can still be selected if it passes run ID, file existence, staleness, and one-update-per-learner checks. Liveness is used for observability, timeout decisions, and optional future quorum adjustment. In milestone 1, `quorum_policy=fixed`: `quorum_min` is not reduced automatically when learners are stale or dead. If no outer step is committed for `liveness.no_progress_timeout_seconds` while fewer than `quorum_min` eligible updates are available, the syncer publishes `stop.json` with `reason = "no_progress_timeout"` and exits cleanly unless an explicit future config enables waiting forever.

## 8. Update metadata JSON schema

Each learner writes metadata after the tensor file has been fully written and atomically renamed.

Example:

```json
{
  "format_version": 1,
  "run_id": "20260708_120000_fs_diloco_gpt2_wikitext2",
  "update_id": "learner_003_00000042_8d75f2",
  "learner_id": "learner_003",
  "hostname": "mg1234",
  "pid": 123456,
  "base_global_version": 17,
  "local_step_start": 4100,
  "local_step_end": 4200,
  "inner_steps": 100,
  "tokens_this_update": 819200,
  "tokens_since_global_load": 1638400,
  "num_examples_this_update": 800,
  "train_loss": 3.47,
  "grad_norm": null,
  "param_norm": 283.1,
  "delta_norm": null,
  "file_path": "$SHARED_ROOT/updates/pending/learner_003/update_...params.safetensors",
  "file_size_bytes": 497759232,
  "sha256": null,
  "created_at": 1783500000.123,
  "committed_at": 1783500001.456
}
```

For milestone 1, `sha256` may be disabled by default because hashing full GPT-2 vectors every update can add overhead. The code should support `sha256=true` for debugging.

## 9. Merge and outer optimization semantics

### 9.1 Default milestone-1 upload mode: parameter-vector mode

Milestone 1 should use full local parameter vectors as one logical fragment. This matches Decoupled DiLoCo's parameter-fragment communication more closely than a pure delta-only transport.

For selected updates `i = 1..K`, load local parameter vector `p_i`. Let current syncer global vector be `theta_t`. Let learner token count be `n_i`. Let staleness be:

```text
s_i = current_global_version - base_global_version_i
```

Default weight:

```text
raw_weight_i = n_i / (1 + staleness_lambda * s_i)
```

Drop update if:

```text
s_i > max_staleness_versions
```

Normalize:

```text
alpha_i = raw_weight_i / sum_j(raw_weight_j)
```

Weighted local parameter vector:

```text
p_bar = sum_i alpha_i * p_i
```

Outer pseudo-gradient:

```text
g_t = theta_t - p_bar
```

Outer optimizer applies gradient descent semantics:

```text
theta_{t+1} = OuterOpt(theta_t, grad=g_t)
```

This sign convention matches PCCL's pseudo-gradient pattern `outer_param - local_param`, where PyTorch SGD subtracts the pseudo-gradient.

### 9.2 Optional ablation: delta mode

The code may include an optional `upload_mode=delta` after the parameter-vector path is stable. In delta mode, learner uploads:

```text
delta = interval_start_params - interval_end_params
```

Syncer computes:

```text
g_t = weighted_average(delta_i)
```

This is closer to the PCCL Async DiLoCo example and is useful for comparison, but it is not required before the default parameter-vector path passes.

### 9.3 SGD momentum and Nesterov outer optimizer

Implement custom flat-vector optimizer classes instead of relying on `torch.optim` internals. This makes serialization explicit and stable.

State:

```text
theta: global flat vector
momentum_buffer: flat vector
step: int
```

For ordinary momentum:

```python
momentum_buffer = momentum * momentum_buffer + grad
theta = theta - lr * momentum_buffer
```

For Nesterov:

```python
momentum_buffer = momentum * momentum_buffer + grad
update = grad + momentum * momentum_buffer
theta = theta - lr * update
```

Default Nesterov config:

```yaml
outer_optimizer:
  name: nesterov
  lr: 0.7
  momentum: 0.9
  weight_decay: 0.0
```

The default learning rate is intentionally a starting point, not a claim of optimality. The experiment config should sweep it.

### 9.4 AdamW-style outer optimizer

State:

```text
theta
exp_avg
exp_avg_sq
step
```

Semantics:

```python
step += 1
if weight_decay != 0:
    theta = theta * (1 - lr * weight_decay)
exp_avg = beta1 * exp_avg + (1 - beta1) * grad
exp_avg_sq = beta2 * exp_avg_sq + (1 - beta2) * grad * grad
m_hat = exp_avg / (1 - beta1 ** step)
v_hat = exp_avg_sq / (1 - beta2 ** step)
theta = theta - lr * m_hat / (sqrt(v_hat) + eps)
```

Default config:

```yaml
outer_optimizer:
  name: adamw
  lr: 0.001
  betas: [0.9, 0.999]
  eps: 1.0e-8
  weight_decay: 0.0
```

## 10. Quorum, grace window, and staleness

Default for 8 learners:

```yaml
sync:
  num_learners: 8
  quorum_min: 4
  quorum_max: 8
  max_staleness_versions: 2
  staleness_lambda: 0.25
  selection_policy: most_recent_per_learner
  grace_window:
    mode: fixed
    fixed_seconds: 20.0
    max_seconds: 60.0
  scan_interval_seconds: 2.0
```

Behavior:

1. Syncer ingests all available heartbeat files and updates learner liveness status in SQLite.
2. Syncer ingests all available update metadata.
3. It filters pending updates by status, staleness, existence of tensor file, run ID, and optional liveness policy.
4. If fewer than `quorum_min` eligible updates exist, it sleeps for `scan_interval_seconds` until either quorum is reached or `liveness.no_progress_timeout_seconds` is exceeded.
5. Once `quorum_min` is reached, it opens a grace window.
6. During the grace window, it keeps ingesting heartbeats and eligible updates until either `quorum_max` is reached or the grace window ends.
7. It selects at most one pending update per learner per outer step. Default: most recent update for each learner that passes staleness bounds; `selection_policy=oldest_pending` is an explicit ablation.
8. It applies the merge.
9. It marks selected updates as `applied`; older updates from the same learner that are now too stale are marked `dropped`.

Later adaptive grace-window mode:

```yaml
grace_window:
  mode: adaptive_ema
  target_overlap_steps: 2
  safety_margin_seconds: 2.0
  max_seconds: 60.0
```

The adaptive mode should maintain EMA estimates for learner inner-step time, time-to-quorum, and synchronization time, then fit grace time within estimated slack. This is a milestone 2 feature unless it is easy to implement after fixed grace works.

## 11. Learner algorithm

Pseudo-code:

```python
def learner_main(config, learner_id):
    setup_logging()
    model, tokenizer = load_hf_causal_lm(config.model)
    dataset = load_wikitext2_shard(learner_id, num_learners=config.sync.num_learners)
    param_index = wait_for_param_index_or_create_compatible_view()

    latest = wait_for_latest_json(shared_root)
    load_global_weights(model, latest.weight_path, param_index)
    inner_optimizer, scheduler = build_inner_optimizer(model, config.inner_optimizer)

    local_step = 0
    last_loaded_global_version = latest.version
    tokens_since_global_load = 0
    write_heartbeat(status="active", phase="loaded_global")

    while not stop_requested(shared_root, local_step, config):
        interval_start_step = local_step
        loss_meter = []
        token_count = 0

        for _ in range(config.training.inner_steps):
            batch = next_batch()
            loss = train_one_step(model, batch, inner_optimizer, scheduler)
            local_step += 1
            token_count += batch.num_tokens
            tokens_since_global_load += batch.num_tokens
            loss_meter.append(loss)
            maybe_write_heartbeat(status="active", phase="inner_steps")

            if config.learner.poll_latest_during_inner_steps:
                maybe_adopt_latest_global_only_between_safe_points()

        params_vector = flatten_trainable_params(model, param_index).cpu()
        update_path = write_update_safetensors_atomic(params_vector)
        meta_path = write_update_metadata_atomic(...)
        write_heartbeat(status="active", phase="update_written", last_update_id=update_id)
        log_update(...)

        latest = read_latest_json_if_newer(shared_root, last_loaded_global_version)
        if latest is not None:
            load_global_weights(model, latest.weight_path, param_index)
            inner_optimizer, scheduler = build_inner_optimizer(model, config.inner_optimizer)
            last_loaded_global_version = latest.version
            tokens_since_global_load = 0
            write_heartbeat(status="active", phase="global_adopted")

    write_heartbeat(status="stopped", phase="process_exit")
```

Default: learners poll for newer global versions after each upload. This is simpler and safer than mid-inner-step overwrites. `maybe_write_heartbeat` writes only when `liveness.heartbeat_interval_seconds` has elapsed or an important phase transition occurs. A later version can poll during inner steps if update granularity becomes large.

Inner optimizer defaults:

```yaml
inner_optimizer:
  name: adamw
  lr: 5.0e-5
  betas: [0.9, 0.95]
  eps: 1.0e-8
  weight_decay: 0.1
  reset_on_global_update: true
```

Training defaults:

```yaml
training:
  inner_steps: 100
  micro_batch_size: 2
  gradient_accumulation_steps: 8
  block_size: 1024
  max_local_steps: null
  precision: bf16
  seed: 1337
```

## 12. Syncer algorithm

Pseudo-code:

```python
def syncer_main(config):
    setup_logging()
    init_shared_dirs()
    db = open_local_sqlite()

    if config.init.resume:
        theta, outer_state, version = load_resume_state()
    else:
        model = load_hf_causal_lm(config.model)
        param_index = build_and_publish_param_index(model)
        theta = flatten_trainable_params(model, param_index).cpu().float()
        outer_state = init_outer_optimizer_state(theta)
        publish_global(version=0, theta=theta, outer_state=outer_state)

    last_progress_time = now()
    stop_published = False
    while not termination_condition():
        ingest_heartbeat_files_from_fs(db)
        update_liveness_statuses(db, now())
        ingest_update_metadata_from_fs(db)
        eligible = query_eligible_pending_updates(db, current_version=version)

        if len(eligible) < config.sync.quorum_min:
            if now() - last_progress_time > config.liveness.no_progress_timeout_seconds:
                publish_stop_json(reason="no_progress_timeout")
                stop_published = True
                break
            sleep(config.sync.scan_interval_seconds)
            continue

        selected = collect_with_grace_window(eligible)
        selected = choose_at_most_one_update_per_learner(selected)

        local_vectors = []
        weights = []
        for update in selected:
            p_i = load_local_params(update.file_path)
            staleness = version - update.base_global_version
            w_i = update.tokens_this_update / (1 + staleness_lambda * staleness)
            local_vectors.append(p_i.float())
            weights.append(w_i)

        p_bar = weighted_average(local_vectors, weights)
        grad = theta - p_bar
        theta, outer_state = outer_optimizer_step(theta, grad, outer_state)
        version += 1

        publish_global(version, theta, outer_state)
        mark_updates_applied(db, selected, applied_version=version)
        drop_obsolete_updates(db, current_version=version)
        dump_db_if_needed()
        write_metrics()
        last_progress_time = now()

    if not stop_published:
        publish_stop_json()
    final_db_dump()
```

Resume semantics for `config.init.resume`:

- `init.resume=false`: create a new run. If `control/latest.json` already exists under the resolved `shared_root`, fail unless `init.allow_overwrite_existing_run=true`.
- `init.resume=true`: resume an existing run. The syncer must load `control/param_index.json`, the target global weight file, and the matching outer optimizer file before ingesting new updates.
- `init.resume_version: latest` means use `control/latest.json`; an integer value means load `weights/global_vNNNNNN.safetensors` and `optim/outer_vNNNNNN.safetensors`.
- If the syncer-local SQLite DB is missing, load `init.resume_db_dump` when provided, otherwise restore from the newest compatible `db_dumps/metadata_*_vNNNNNN.db`. If no DB dump exists, initialize an empty local DB, insert the resumed `global_versions` row, and then idempotently re-ingest unapplied metadata from the filesystem.
- Resume must be idempotent: already-applied update IDs must not be applied again, and the `(learner_id, local_step_end, base_global_version)` uniqueness constraint must remain enforced.
- Resume must validate that the resolved config, model name, trainable parameter index, and tensor dtype are compatible with the resumed run. Mismatches fail unless a future explicit `allow_config_mismatch` option is added for manual recovery.

## 13. Repository structure to implement

Codex should create the following repository layout:

```text
fs-diloco-miyabi/
  README.md
  AGENTS.md
  pyproject.toml
  configs/
    fs_diloco_gpt2_wikitext2_8l.yaml
    fs_diloco_gpt2_wikitext2_1l_debug.yaml
    fs_diloco_tiny_local.yaml
  fs_diloco/
    __init__.py
    cli.py
    config.py
    constants.py
    logging_utils.py
    atomic_io.py
    sqlite_store.py
    schema.sql
    tensor_codec.py
    param_index.py
    outer_optim.py
    merge.py
    liveness.py
    syncer.py
    learner.py
    hf_data.py
    hf_model.py
    metrics.py
    failure_sim.py
    analysis.py
  scripts/
    miyabi/
      run_9node_gpt2_wikitext2.pbs
      run_2node_debug.pbs
      run_1node_debug.pbs
      inspect_run.sh
      dump_sqlite.sh
    local/
      run_tiny_2proc_smoke.sh
      clean_run.sh
  tests/
    test_param_index_roundtrip.py
    test_outer_optim.py
    test_merge.py
    test_atomic_io.py
    test_sqlite_store.py
    test_liveness.py
    test_resume.py
    test_syncer_selection.py
    test_config.py
  docs/
    design.md
    miyabi_runbook.md
    experiments.md
```

## 14. Python package requirements

Use a `pyproject.toml` with at least:

```toml
[project]
name = "fs-diloco-miyabi"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
  "torch",
  "transformers",
  "datasets",
  "safetensors",
  "pyyaml",
  "numpy",
  "tqdm",
  "typing-extensions",
]

[project.optional-dependencies]
dev = [
  "pytest",
  "ruff",
]

[project.scripts]
fs-diloco-syncer = "fs_diloco.syncer:main"
fs-diloco-learner = "fs_diloco.learner:main"
fs-diloco-inspect = "fs_diloco.analysis:main"
```

Do not hardcode Python 3.13 in the project if current Miyabi/HF/Torch package availability requires a different Python. The `miyabi-development` skill defaults to `uv`, but Codex should inspect existing project pins and choose the Python version compatible with Miyabi's installed PyTorch stack.

## 15. Configuration file schema

Example config:

```yaml
run:
  name: fs_diloco_gpt2_wikitext2_8l
  run_id: null
  shared_root: null
  log_level: INFO

init:
  resume: false
  resume_version: latest
  resume_db_dump: null
  allow_overwrite_existing_run: false

model:
  name_or_path: gpt2
  trust_remote_code: false
  dtype: bfloat16
  compile: false

data:
  dataset_name: wikitext
  dataset_config_name: wikitext-2-raw-v1
  train_split: train
  validation_split: validation
  block_size: 1024
  num_proc: 4
  cache_dir: null
  streaming: false

sync:
  num_learners: 8
  upload_mode: params
  quorum_min: 4
  quorum_max: 8
  max_staleness_versions: 2
  staleness_lambda: 0.25
  selection_policy: most_recent_per_learner
  scan_interval_seconds: 2.0
  grace_window:
    mode: fixed
    fixed_seconds: 20.0
    max_seconds: 60.0
  db_dump_every_versions: 1
  stop_after_outer_steps: 20
  stop_after_global_tokens: null
  stop_file_poll_seconds: 5.0

liveness:
  heartbeat_interval_seconds: 30.0
  stale_after_seconds: 120.0
  dead_after_seconds: 300.0
  no_progress_timeout_seconds: 600.0
  quorum_policy: fixed

training:
  inner_steps: 100
  micro_batch_size: 2
  gradient_accumulation_steps: 8
  block_size: 1024
  max_local_steps: null
  precision: bf16
  seed: 1337
  log_every_steps: 10

inner_optimizer:
  name: adamw
  lr: 5.0e-5
  betas: [0.9, 0.95]
  eps: 1.0e-8
  weight_decay: 0.1
  scheduler: cosine
  warmup_steps: 100
  reset_on_global_update: true

outer_optimizer:
  name: nesterov
  lr: 0.7
  momentum: 0.9
  weight_decay: 0.0
  betas: [0.9, 0.999]
  eps: 1.0e-8

io:
  tensor_dtype: float32
  atomic_write: true
  compute_sha256: false
  keep_processed_updates: true
  cleanup_applied_after_versions: null
  sqlite_local_dir: null

learner:
  poll_latest_during_inner_steps: false
  adopt_global_after_upload: true

failure_sim:
  enabled: false
  sleep_jitter_seconds: 0.0
  upload_skip_probability: 0.0
  crash_probability: 0.0
```

## 16. PBS launch scripts

### 16.1 9-node regular run

Create `scripts/miyabi/run_9node_gpt2_wikitext2.pbs`.

The script must follow the `miyabi-development` skill conventions:

- use PBS batch, not login-node runtime;
- use `regular-g` by default;
- use `select=9:mpiprocs=1`;
- fill `#PBS -W group_list=<group_id>` with a real group before submission, because PBS directives do not expand shell variables;
- use MPI only as a PBS multi-node process launcher; Milestone 1 communication remains filesystem-based and must not use MPI collectives for learner/syncer data exchange;
- pass MPI child environment via `/usr/bin/env`, not `mpirun -x`;
- print node/rank/log information before launch;
- write timestamped logs.

Template:

```bash
#!/bin/bash
#PBS -q regular-g
#PBS -W group_list=<group_id>
#PBS -l select=9:mpiprocs=1
#PBS -l walltime=02:00:00
#PBS -j oe
#PBS -m ae

set -eEuo pipefail
trap 'echo "[ERROR] Failed at line $LINENO" >&2' ERR

PROJECT_ROOT="${PROJECT_ROOT:-${PBS_O_WORKDIR:-$PWD}}"
PYTHON_BIN="${PYTHON_BIN:-$PROJECT_ROOT/.venv/bin/python}"
CONFIG="${CONFIG:-$PROJECT_ROOT/configs/fs_diloco_gpt2_wikitext2_8l.yaml}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d_%H%M%S)_fs_diloco_gpt2_wikitext2_8l}"
SHARED_ROOT="${SHARED_ROOT:-$PROJECT_ROOT/runs/fs_diloco/$RUN_ID}"
SYNCER_DB_DIR="${SYNCER_DB_DIR:-${TMPDIR:-/tmp}/fs_diloco/$RUN_ID}"

: "${PBS_NODEFILE:?PBS_NODEFILE is not set}"
cd "$PROJECT_ROOT"

mapfile -t HOSTS < <(sort -u "$PBS_NODEFILE")
NNODES="${#HOSTS[@]}"
if [[ "$NNODES" -ne 9 ]]; then
  echo "Expected 9 unique nodes, got $NNODES" >&2
  printf '%s\n' "${HOSTS[@]}" >&2
  exit 2
fi

mkdir -p "$SHARED_ROOT" "$PROJECT_ROOT/logs"
LOG_ROOT="$PROJECT_ROOT/logs/qsub_${RUN_ID}"
mkdir -p "$LOG_ROOT"

MPI_ENV_ARGS=(
  "PROJECT_ROOT=$PROJECT_ROOT"
  "PYTHON_BIN=$PYTHON_BIN"
  "CONFIG=$CONFIG"
  "RUN_ID=$RUN_ID"
  "SHARED_ROOT=$SHARED_ROOT"
  "SYNCER_DB_DIR=$SYNCER_DB_DIR"
  "NUM_LEARNERS=8"
)

echo "RUN_ID=$RUN_ID"
echo "PROJECT_ROOT=$PROJECT_ROOT"
echo "CONFIG=$CONFIG"
echo "SHARED_ROOT=$SHARED_ROOT"
echo "SYNCER_DB_DIR=$SYNCER_DB_DIR"
echo "NNODES=$NNODES"
printf 'HOST %s\n' "${HOSTS[@]}"

mpirun \
  --mca mpi_abort_print_stack 1 \
  --report-bindings \
  --bind-to core \
  -np "$NNODES" \
  /usr/bin/env "${MPI_ENV_ARGS[@]}" \
  bash -lc '
    set -eEuo pipefail
    rank="${OMPI_COMM_WORLD_RANK:?missing OMPI_COMM_WORLD_RANK}"
    host="$(hostname)"
    echo "[launcher] rank=${rank} host=${host}"
    if [[ "$rank" -eq 0 ]]; then
      export CUDA_VISIBLE_DEVICES=""
      exec "$PYTHON_BIN" -m fs_diloco.syncer \
        --config "$CONFIG" \
        --run-id "$RUN_ID" \
        --shared-root "$SHARED_ROOT" \
        --sqlite-local-dir "$SYNCER_DB_DIR" \
        2>&1 | tee "$PROJECT_ROOT/logs/qsub_${RUN_ID}/syncer.log"
    else
      learner_num=$((rank - 1))
      learner_id=$(printf "learner_%03d" "$learner_num")
      export CUDA_VISIBLE_DEVICES="0"
      exec "$PYTHON_BIN" -m fs_diloco.learner \
        --config "$CONFIG" \
        --run-id "$RUN_ID" \
        --shared-root "$SHARED_ROOT" \
        --learner-id "$learner_id" \
        --num-learners "$NUM_LEARNERS" \
        2>&1 | tee "$PROJECT_ROOT/logs/qsub_${RUN_ID}/${learner_id}.log"
    fi
  '
```

### 16.2 2-node debug run

Create a smaller PBS script with:

```text
select=2:mpiprocs=1
rank 0 = syncer
rank 1 = learner_000
num_learners = 1
config = configs/fs_diloco_gpt2_wikitext2_1l_debug.yaml
walltime = 00:10:00 for interact-g, or regular-g if submitted as batch
```

### 16.3 1-node debug run

Create a 1-node script that starts syncer and one learner on the same compute node using background processes. This is only for smoke testing and must keep `sync.stop_after_outer_steps` very small.

Example:

```bash
"$PYTHON_BIN" -m fs_diloco.syncer ... > "$LOG_ROOT/syncer.log" 2>&1 &
syncer_pid=$!
sleep 5
CUDA_VISIBLE_DEVICES=0 "$PYTHON_BIN" -m fs_diloco.learner ... > "$LOG_ROOT/learner_000.log" 2>&1 &
learner_pid=$!
wait "$learner_pid"
wait "$syncer_pid"
```

## 17. Miyabi development workflow for Codex

Codex must use the user's `miyabi-development` skill.

Minimum expected workflow:

1. Check `hostname` before choosing workflow.
2. On local machine: edit code, run safe local checks, commit to `codex/fs-diloco-miyabi`, push branch.
3. On Miyabi login node: fetch branch, run only static checks such as `bash -n scripts/miyabi/*.pbs` and config review. Do not import `torch`, `transformers`, or `datasets` on the login node.
4. Request 1-node interactive allocation for first runtime smoke test.
5. Run 1-node debug for a tiny number of steps.
6. If it passes, request 2-node interactive allocation for rank/role and shared filesystem behavior.
7. If it passes, submit 9-node batch job.
8. Report branch, commit, which checks ran locally, which ran on login node, and which ran inside PBS compute nodes.

Codex must not merge to `main` without explicit approval.

## 18. Hugging Face training details

Use a custom training loop instead of Hugging Face `Trainer`, because the learner must control synchronization points precisely.

Model:

```python
AutoModelForCausalLM.from_pretrained("gpt2")
AutoTokenizer.from_pretrained("gpt2")
```

Tokenizer handling:

- GPT-2 has no default pad token. Set `tokenizer.pad_token = tokenizer.eos_token` if padding is used.
- Prefer packed fixed-length blocks over padding.

Dataset:

```python
load_dataset("wikitext", "wikitext-2-raw-v1")
```

Learner sharding:

```python
dataset = dataset.shard(num_shards=num_learners, index=learner_index, contiguous=True)
```

Tokenization:

- tokenize raw text;
- concatenate token streams;
- split into `block_size` chunks;
- labels equal input ids shifted internally by HF causal LM loss.

Training step:

- use bf16 autocast when CUDA supports it;
- apply gradient accumulation;
- clip gradients only if configured;
- log finite loss;
- abort or mark learner failed if loss is NaN/Inf.

## 19. Logging and metrics

Every process writes JSONL logs.

Required learner events:

```text
process_start
loaded_global
heartbeat_written
inner_step_summary
update_written
latest_polled
global_adopted
inner_optimizer_reset
stop_seen
process_exit
error
```

Required syncer events:

```text
process_start
run_initialized
heartbeats_ingested
learner_liveness_updated
metadata_ingested
quorum_wait
updates_selected
update_loaded
outer_step_applied
global_published
updates_marked_applied
updates_dropped
db_dumped
no_progress_timeout
stop_published
process_exit
error
```

Metrics to compute:

- learner tokens/sec;
- learner local step time;
- learner time spent writing update tensor;
- syncer scan time;
- update file read time;
- aggregation time;
- outer optimizer time;
- global publish time;
- selected learner count per outer step;
- stale updates dropped;
- effective tokens per outer step;
- global version interval wall time;
- useful token goodput estimate.

## 20. Failure simulation controls

Add lightweight failure simulation to learners after the stable path works:

```yaml
failure_sim:
  enabled: true
  sleep_jitter_seconds: 30.0
  upload_skip_probability: 0.05
  crash_probability: 0.0
```

Implementation:

- `sleep_jitter_seconds`: random sleep before upload or after local interval;
- `upload_skip_probability`: train an interval but skip writing the update;
- `crash_probability`: intentionally exit with a nonzero code at interval boundaries. Keep disabled by default.

The syncer should continue with quorum when learners are missing.

## 21. Testing plan

Unit tests:

- `test_param_index_roundtrip.py`: flatten -> load -> flatten preserves values.
- `test_outer_optim.py`: SGD momentum, Nesterov, and AdamW-style update known small vectors correctly.
- `test_merge.py`: token/staleness weighting and stale-drop behavior.
- `test_atomic_io.py`: temp file is ignored and final renamed file is visible.
- `test_sqlite_store.py`: insert, select, status transitions, and uniqueness constraints.
- `test_liveness.py`: heartbeat parsing, DB upsert, active/stale/dead transitions, stopped preservation, and no-progress timeout decisions.
- `test_resume.py`: `init.resume` restores latest or requested global version, restores compatible DB dumps when present, and does not reapply already-applied updates.
- `test_syncer_selection.py`: quorum and one-update-per-learner selection.
- `test_config.py`: YAML defaults and CLI overrides resolve correctly.

Local integration smoke:

- use a tiny synthetic model or `sshleifer/tiny-gpt2` if available;
- run 1 syncer + 2 learner processes on CPU with `sync.stop_after_outer_steps=2`;
- verify global versions `v0`, `v1`, `v2` exist;
- verify SQLite status transitions;
- verify learners stop cleanly.

Miyabi 1-node runtime smoke:

- load real `gpt2` and WikiText-2;
- `num_learners=1`;
- `inner_steps=2`;
- `sync.stop_after_outer_steps=1`;
- verify finite loss and global version `v1`.

Miyabi 2-node runtime smoke:

- rank 0 syncer, rank 1 learner;
- same tiny training limits;
- verify FS communication across nodes.

Miyabi 9-node batch acceptance:

- rank 0 syncer, ranks 1-8 learners;
- run at least `sync.stop_after_outer_steps=3`;
- verify at least 3 committed global versions;
- verify at least 4 learners selected per outer step by default quorum;
- verify all selected update files exist and were applied once;
- verify no login-node runtime work was used.

## 22. Acceptance criteria for milestone 1

Codex should consider milestone 1 complete only when all of the following are true:

1. Repository contains the requested package, configs, tests, docs, and PBS scripts.
2. `bash -n scripts/miyabi/*.pbs` passes.
3. Unit tests pass in an environment where dependencies are installed.
4. Local CPU smoke can complete with a tiny model/config.
5. Miyabi 1-node compute-node smoke can run real `gpt2` + WikiText-2 for a tiny number of steps.
6. Miyabi 2-node compute-node smoke verifies shared filesystem update exchange.
7. 9-node PBS script is syntactically ready and follows Miyabi skill constraints.
8. Syncer-local SQLite is periodically backed up to shared FS.
9. Learner updates are never applied twice.
10. Learners overwrite full model and reset inner optimizer after adopting a newer global version.
11. Both Nesterov/SGD-momentum and AdamW-style outer optimizers are implemented and unit-tested.
12. Logs and metrics are sufficient to reconstruct which learners contributed to every global version.
13. Learner heartbeat files are atomically written, syncer DB liveness transitions are implemented, and no-progress timeout behavior is unit-tested.
14. `init.resume` can recover from a published global version and DB dump without applying the same learner update twice.

## 23. Milestone sequence

### Milestone A: skeleton and local utilities

Deliverables:

- `pyproject.toml`;
- config loader;
- atomic IO utilities;
- SQLite schema/store;
- parameter flatten/load utilities;
- outer optimizer utilities;
- tests for all utilities.

### Milestone B: local CPU integration

Deliverables:

- syncer process can publish initial global;
- learner process can write update metadata and tensors;
- learner process can write heartbeat files and syncer can update liveness status;
- syncer can ingest and apply one update;
- local smoke script can run 1 syncer + 2 learners.

### Milestone C: Hugging Face GPT-2/WikiText-2 learner

Deliverables:

- custom GPT-2 training loop;
- WikiText-2 loading, tokenization, sharding;
- local interval upload;
- latest global polling and inner optimizer reset;
- finite loss logging.

### Milestone D: Miyabi scripts and runtime validation

Deliverables:

- 1-node debug PBS;
- 2-node debug PBS;
- 9-node PBS;
- Miyabi runbook;
- login-node static checks only;
- compute-node runtime smoke.

### Milestone E: experiments and analysis

Deliverables:

- run inspection command;
- metrics summarizer;
- plots or CSV summaries for outer step time, selected learners, staleness, tokens/sec, update read/write time;
- failure simulation toggles.

### Milestone F: fragment design, not necessarily implementation

Deliverables:

- document how `fragment_id` will generalize from full model to parameter groups;
- define fragment metadata schema;
- define future learner mailbox layout for syncer-to-learner fragment update messages.

## 24. Future fragment-level extension

After milestone 1 is stable, extend the single-fragment design:

```text
fragments/
  fragment_index.json
updates/pending/learner_000/update_<uuid>_fragment_000.params.safetensors
mailbox/learner_000/global_v000123_fragment_000.safetensors
```

Fragment strategies to support in later work:

1. layer-based fragments: easiest to debug;
2. tensor-based fragments: one tensor per fragment group;
3. balanced tensor fragments: greedily balance total bytes per fragment;
4. sub-tensor fragments: most balanced, but highest implementation complexity.

Recommended order:

- implement layer-based first;
- implement balanced tensor fragments second;
- avoid sub-tensor fragmentation until a strong need appears.

## 25. Known risks and mitigations

Risk: SQLite on Lustre may suffer lock or latency problems.
Mitigation: keep SQLite on syncer-local storage and only dump backups to shared FS.

Risk: full GPT-2 parameter vector upload is large.
Mitigation: this is acceptable for a research prototype on Miyabi's Lustre, but metrics must report update write/read time. Later add bf16 update tensors, compression, and fragments.

Risk: learner local params based on stale global may destabilize training.
Mitigation: implement `max_staleness_versions`, token/staleness weighting, and drop stale updates. Run small sweeps.

Risk: learners adopt globals only after upload, so they may drift for long `inner_steps`.
Mitigation: keep `inner_steps` modest initially. Later add safe mid-interval polling.

Risk: PBS script launches syncer on a GPU node and wastes the GPU.
Mitigation: acceptable in milestone 1. Later move syncer to Miyabi-C or another CPU allocation if scheduling permits.

Risk: login-node misuse.
Mitigation: encode `miyabi-development` skill rules in `AGENTS.md` and `docs/miyabi_runbook.md`; do not run heavy imports or training on login nodes.

## 26. Suggested initial experiment matrix

Correctness:

```text
1 learner, quorum=1, sync.stop_after_outer_steps=3
2 learners, quorum=1 and quorum=2
8 learners, quorum=4
```

Optimization:

```text
outer_optimizer = nesterov, momentum, adamw
outer_lr sweep for nesterov: 0.1, 0.3, 0.7, 1.0
inner_steps: 10, 50, 100
max_staleness_versions: 0, 1, 2, 4
```

Resilience:

```text
sleep_jitter_seconds: 0, 10, 30
upload_skip_probability: 0.0, 0.05, 0.2
quorum_min: 2, 4, 6, 8
```

System metrics:

```text
update write time
update read time
syncer aggregation time
global publish time
learner tokens/sec
effective selected tokens per outer step
```

## 27. `AGENTS.md` content to generate in the repo

Codex should create an `AGENTS.md` similar to this:

```markdown
# AGENTS.md

Use the `miyabi-development` Codex skill for all Miyabi-related work.

Do not run training, model loading, CUDA checks, torch imports, transformers imports, datasets preprocessing, `torchrun`, `mpirun`, or pytest runtime tests on Miyabi login nodes. Login nodes are control-plane only: inspect files, edit, run `bash -n`, review configs, submit jobs, inspect logs.

For runtime validation, use PBS interactive/debug or batch compute nodes. Start with 1-node checks, then 2-node checks, then 9-node batch.

This repository implements a filesystem-based Decoupled DiLoCo prototype:

- learners are independent single-GPU PyTorch/Hugging Face processes;
- syncer is CPU-only;
- tensors are stored in safetensors on the shared filesystem;
- syncer metadata is stored in syncer-local SQLite and periodically dumped to shared filesystem;
- milestone 1 uses one full-model vector as one logical fragment;
- no NCCL, torch.distributed, RPC, PCCL, Ray, FSDP, or DeepSpeed is required for milestone 1.

Before submitting PBS scripts, run `bash -n scripts/miyabi/*.pbs` on a safe node. Fill real `#PBS -W group_list=<group_id>` values before submission.
```

## 28. Final instruction block for Codex

Use this as the initial Codex task prompt:

```text
Implement the repository described in `fs_based_decoupled_diloco_miyabi_plan.md`.

Use the `miyabi-development` skill. Start by creating a feature branch `codex/fs-diloco-miyabi`. Implement the repository skeleton, utility modules, SQLite schema, safetensors tensor codec, flat-vector outer optimizers, learner/syncer processes, GPT-2 WikiText-2 training loop, configs, tests, and Miyabi PBS scripts.

Milestone 1 must use full-model parameter-vector uploads as a single logical fragment. Use syncer-local SQLite plus shared filesystem safetensors. Do not add torch.distributed, NCCL, RPC, PCCL, Ray, DeepSpeed, or FSDP in milestone 1.

Respect Miyabi login-node restrictions. Static checks may run on login nodes; runtime checks must run only inside PBS compute/debug nodes. Prepare 1-node, 2-node, and 9-node PBS scripts. Do not merge to main without explicit user approval.
```
