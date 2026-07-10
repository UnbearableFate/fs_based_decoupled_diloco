# Design

This repository implements milestone 1 of the filesystem-based Decoupled DiLoCo plan. The design follows the Decoupled DiLoCo idea of independent learners communicating asynchronously with a central synchronizer using quorum, grace-window, and token-weighted merging. The project uses the Miyabi-G facts that each GPU node has one NVIDIA Hopper H100 with 96 GB GPU memory and that the system provides a Lustre/DDN EXAScaler shared filesystem.

References:

- Miyabi system page: https://www.cc.u-tokyo.ac.jp/en/supercomputer/miyabi/system.php
- Decoupled DiLoCo paper: https://arxiv.org/abs/2604.21428
- Google DeepMind blog: https://deepmind.google/blog/decoupled-diloco/
- PCCL Async DiLoCo docs: https://pccl.primeintellect.ai/DiLoCo%20-%20Distributed%20Low-Communication/AsyncDiloco
- PCCL example: https://github.com/PrimeIntellect-ai/pccl/blob/main/python/examples/nanogpt_diloco/async_diloco.py

## Baseline And Fragment Scope

The original path uses the full-model parameter vector as one logical fragment. The current implementation also supports `balanced_tensor` fragmentation: complete parameter tensors are assigned deterministically across multiple fragments, and learners publish the scheduled fragment for each interval. In both modes, learners write a `safetensors` payload and then metadata JSON. The syncer only treats metadata JSON as the update commit marker; orphan tensor files are ignored.

No milestone 1 code depends on `torch.distributed`, NCCL collectives, RPC, Ray, DeepSpeed, FSDP, or PCCL. PBS scripts use MPI only as a process launcher across allocated nodes.

## Syncer State

SQLite is authoritative after ingestion. It tracks learners, updates, global versions, events, and DB dumps. The DB path defaults to syncer-local storage under `${TMPDIR:-/tmp}/fs_diloco/$RUN_ID`; consistent backups are copied to the shared filesystem with SQLite's backup API.

## Merge Semantics

For selected updates, the syncer loads each local parameter vector `p_i`, computes staleness `s_i = current_global_version - base_global_version_i`, and assigns:

```text
raw_weight_i = tokens_this_update_i / (1 + staleness_lambda * s_i)
```

After normalization, `p_bar = sum_i alpha_i * p_i` and the outer pseudo-gradient is:

```text
grad = theta_t - p_bar
```

The sign follows the Async DiLoCo pseudo-gradient pattern where an outer optimizer subtracts `outer_param - local_param`.

## Learner Adoption

Learners load the latest published global weight file, overwrite their full trainable model parameters, and rebuild the inner optimizer/scheduler. This reset is logged as `inner_optimizer_reset`.

## Fragment Implementation

Full-vector mode uses `fragment_id = 0`. Fragment mode currently uses:

```text
fragments/fragment_index.json
updates/pending/learner_000/update_<uuid>_fragment_000.params.safetensors
mailbox/learner_000/global_v000123_fragment_000.safetensors
```

The implemented strategy is `balanced_tensor` with a deterministic fragment index and round-robin scheduling. Direct parameter-level fragment gather/scatter and richer layout strategies remain future performance work.
