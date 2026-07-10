# P00 Baseline Inventory

Observed base: `afc50a1e179c64321645b278b2497ea3ab3fe24d`; actual
work started from the dirty tree described in `drift_report.md`. This inventory
describes the legacy prototype before Protocol v2 becomes a runtime authority.

## Package and command surface

| Area | Current modules | Authority/behavior |
|---|---|---|
| Entry points | `cli.py`, `learner.py`, `syncer.py`, `analysis.py`, `eval_lm_harness.py` | `fs-diloco-learner`, `fs-diloco-syncer`, `fs-diloco-inspect`, `fs-diloco-lm-eval` |
| Config | `config.py`, YAML under `configs/` | Dataclass configuration resolved to `control/run_config.resolved.yaml` |
| Model/data | `hf_model.py`, `hf_data.py` | Hugging Face model/dataset runtime; compute-node only on Miyabi |
| Index/layout | `param_index.py`, `fragment_index.py`, `fragment_scheduler.py` | Parameter order and balanced whole-tensor fragment layout |
| Encoding/I/O | `tensor_codec.py`, `fragment_codec.py`, `atomic_io.py`, `paths.py` | Safetensors payloads and temp-write/replace JSON/file publication |
| Merge/math | `merge.py`, `outer_optim.py` | Token/staleness weighted merge; explicit SGD, momentum, Nesterov, AdamW |
| Learner | `learner.py` | Full-vector or scheduled fragment publication and global-state reload |
| Syncer | `syncer.py` | Discovery, SQLite selection state, merge, outer step, `latest.json` publication |
| Local database | `schema.sql`, `sqlite_store.py` | Update status, selection/application/drop state; currently syncer-local authority |
| Operations | `liveness.py`, `retention.py`, `failure_sim.py`, `metrics.py`, `logging_utils.py`, `wandb_logging.py` | Heartbeats/stop, version retention, process-failure simulation, JSONL/CSV/W&B telemetry |

The package contains 26 top-level Python modules at the planning base. P01 and
P02 add isolated `protocol`, `storage`, `log`, and `testing` packages without
changing legacy entry-point defaults.

## Existing tests

The base suite covers atomic I/O, configuration, parameter/fragment indexing
and codecs, fragment scheduling/store/pipeline, full and fragment merge,
explicit outer optimizers, SQLite transitions, syncer selection, resume,
liveness, retention, metrics/analysis, and W&B behavior. The authoritative
test list is captured in the baseline manifest; all runnable legacy tests are
executed on a PBS compute node for P00 because the suite imports Torch.

P00 adds state/manifest/baseline contract tests. P01 adds strict Protocol v2
tests. P02 adds pure deterministic reference/model-checker tests.

## Configurations

| Config family | Purpose |
|---|---|
| `fs_diloco_tiny_local.yaml` | Two-process synthetic full-vector local smoke |
| `fs_diloco_tiny_fragment_local.yaml` | Synthetic fragment local smoke |
| `*_1l_debug.yaml` | One-learner GPT-2/WikiText-2 debug, full or fragment |
| `*_8l*.yaml` | Eight-learner Miyabi full/fragment acceptance and longer runs |

Legacy default behavior is full-vector mode unless fragment configuration is
explicitly enabled. Protocol v2 is not selected by any legacy config in
P00–P02.

## Scripts and Miyabi topology

- Local: `scripts/local/run_tiny_2proc_smoke.sh` and `clean_run.sh`.
- Inspection: `scripts/miyabi/inspect_run.sh` and `dump_sqlite.sh`.
- Runtime: 1-node and 2-node full/fragment debug scripts, 9-node 8-learner +
  1-syncer scripts, and a 1-node lm-eval script.
- Every PBS script names the real group `xg24i002`, records the compute-node
  default module stack and project Python, and is statically checked with
  `bash -n` on the login node.

The current shell is `miyabi-g1` without `$PBS_JOBID` or `$PBS_NODEFILE`, so it
is control-plane only. Runtime tests, Torch imports, model/data loading, and
smokes are submitted to PBS compute nodes.

## Current filesystem layout and authority

```text
<run-root>/
  control/latest.json                 current global pointer
  control/stop.json                   terminal request/reason
  control/param_index.json            parameter ordering
  control/run_config.resolved.yaml    resolved configuration
  updates/pending/<learner>/           payload + JSON commit markers
  weights/ and optim/                  full-vector global/outer checkpoints
  fragments/weights|optim/...          fragment materializations
  metadata/syncer.db or local DB       update state machine
  db_dumps/                            SQLite snapshots
  heartbeats/                          liveness observations
  logs/ and metrics/                   non-authoritative telemetry
```

Authority is distributed across payload/marker files, `latest.json`, and
syncer-local SQLite. `latest.json` names a global version/materialization, but
there is no Protocol v2 parent-linked commit/frontier log or conditional head
CAS. SQLite contains durable `selected` state that cannot yet be reconstructed
solely from committed optimizer history. Listings/globs participate in
discovery and existing behavior.

## Baseline evidence

The representative legacy run
`runs/fs_diloco/20260710_013757_fs_diloco_gpt2_wikitext2_8l_fragment_5000steps`
contains resolved config, parameter/fragment indexes, `latest.json`, stop
state, two SQLite dumps, eight learner logs/heartbeats, syncer logs/metrics,
and final global weights. P00 samples control files, the final weight, the
newest DB dump, and representative logs; it does not recursively copy/hash
all historical tensors. This run is legacy observational evidence, not proof
of Protocol v2 invariants.

Known baseline limitations are the absence of strict content/causal proposal
validation, conditional head commit, durable consumption history, cache-free
replay, fencing/failover, atomic fragment/outer-state publication, exact
fragment resume, and reachability-based reclamation.

Observed smoke defects and their exact reproductions are recorded in
`baseline_limitations.md`; a non-success stop cannot pass the evidence checker
unless its reason is explicitly allowed and linked to such a limitation.
