# FS DiLoCo Miyabi

Filesystem-backed Decoupled DiLoCo research prototype for Miyabi-G.

The prototype uses independent single-GPU learners and one GPU-backed syncer process. It supports both the original full-vector mode (`fragment_id = 0`) and a balanced-tensor fragment mode with multiple scheduled fragments. Learners publish `safetensors` payloads followed by JSON commit markers on the shared filesystem. The syncer ingests those metadata files into a syncer-local SQLite database, applies token/staleness-weighted merging with quorum and grace-window behavior on its local GPU, steps explicit outer optimizers, logs syncer-side telemetry to W&B, and publishes global state through `control/latest.json`.

The implementation intentionally does not use `torch.distributed`, NCCL, RPC, Ray, DeepSpeed, FSDP, or PCCL for milestone 1 communication.

## Layout

- `fs_diloco/`: Python package.
- `configs/`: GPT-2/WikiText-2 and tiny synthetic smoke configs.
- `scripts/miyabi/`: PBS launch and inspection scripts.
- `scripts/local/`: synthetic CPU smoke helpers.
- `tests/`: focused unit and integration tests.
- `docs/`: split bilingual user guide, design notes, Miyabi runbook, and experiment plan.

## Documentation

- [Bilingual documentation index](docs/user-guide/00-README.zh-en.md): Chinese and English docs split by overview, training, dataflow, storage/schema, modules, configuration, and operations.
- [Compatibility guide entry](docs/USER_GUIDE.zh-en.md): short redirect for the original single-file guide path.
- [Miyabi runbook](docs/miyabi_runbook.md): node policy and PBS launch commands.
- [Design notes](docs/design.md): protocol-level design summary.
- [Experiments](docs/experiments.md): suggested correctness, optimizer, and resilience matrices.
- [DuraLoCo research contract](docs/duraloco/research_contract.md): frozen recovery,
  authority, failure, invariant, and numeric semantics for Protocol v2.
- [DuraLoCo phase state](plans/duraloco/STATE.yaml): durable maker/checker progress
  and acceptance evidence; phase plans live under
  `plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans/`.

## Quick Commands

Static checks on a Miyabi login node:

```bash
bash -n scripts/miyabi/*.pbs scripts/miyabi/*.sh scripts/local/*.sh
.venv/bin/python -m py_compile fs_diloco/*.py
```

Runtime checks must run inside PBS compute/debug nodes, not on login nodes.

DuraLoCo login-node-safe contract checks:

```bash
.venv/bin/python scripts/agent/check_research_contract.py
.venv/bin/python scripts/agent/check_phase_state.py plans/duraloco/STATE.yaml
```

Local synthetic smoke on a safe runtime node:

```bash
scripts/local/run_tiny_2proc_smoke.sh
```

Miyabi 1-node debug batch:

```bash
qsub scripts/miyabi/run_1node_debug.pbs
```

Inspect a completed run:

```bash
python -m fs_diloco.analysis runs/fs_diloco/<RUN_ID>
```

## Runtime Contract

- Large tensors are stored as `safetensors`.
- Learner update metadata JSON is the commit marker.
- Heartbeat JSON files are liveness hints.
- `control/latest.json` is the only global pointer learners poll.
- SQLite stays local to the syncer and is backed up to `db_dumps/`.
- Learners overwrite the full model and reset the inner optimizer after adopting a newer global version.
- Outer optimizers are explicit flat-vector SGD, momentum/Nesterov, and AdamW-style implementations.

See `docs/miyabi_runbook.md` before launching on Miyabi.
