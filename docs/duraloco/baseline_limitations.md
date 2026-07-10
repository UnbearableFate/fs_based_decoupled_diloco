# P00 Baseline Limitations

## BASE-001 — Full-vector tiny smoke can exhaust local steps before target outer steps

- Environment: Miyabi compute node `mg0032`, PBS `2357333.opbs`, clean commit
  `32e84da63c5a0a31842fbcca46a5bc2876398dad`.
- Command: the full-vector invocation recorded in
  `artifacts/duraloco/P00/20260710_clean_p00_32e84da/commands.log`, using
  `configs/fs_diloco_tiny_local.yaml`.
- Expected: `sync.stop_after_outer_steps: 2` produces global version 2 and
  `stop_after_outer_steps`.
- Observed: eight finite loss records and one valid global outer update were
  produced, then both learners exhausted `training.max_local_steps: 8`; the
  syncer stopped after the configured 30-second no-progress window at version
  1 with reason `no_progress_timeout`.
- Evidence: `full_smoke.log`, `full_smoke_evidence_v2.json`, the run's
  `control/stop.json`, and PBS stdout for job 2357333.
- Scope: this is a legacy baseline liveness/configuration limitation, not a
  Protocol v2 correctness result. The fragment smoke reached all 4 configured
  outer steps in the same job.
- P00 treatment: preserve the failure and finite/artifact evidence; do not
  alter legacy training semantics to make P00 green. The evidence checker
  rejects this reason by default; the P00 harness opts in with
  `--allow-stop-reason no_progress_timeout` solely for BASE-001.
- Future owner: a separate legacy configuration/liveness fix, outside P00–P02.
