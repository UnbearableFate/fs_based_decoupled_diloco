# M00 Production Replay Workflow Review

Date: 2026-07-11  
Status: active review; no further nine-node submission is authorized until the
pre-submit conditions below are satisfied.

## Scope

This review covers the production full-vector path from learner publication to
the next learner adoption:

```text
learner train
  -> immutable proposal payload
  -> discovery marker
  -> catalog validation/selection
  -> proposal manifest publication
  -> aggregate + outer step
  -> params/outer-state/commit/frontier publication
  -> head CAS
  -> replay-derived RuntimeView
  -> derived latest/checkpoint export
  -> learner adoption
```

The committed log and head CAS remain the sole transition authority. This
review does not authorize a database, durable process cache, alternate head, or
learner head mutation.

## Evidence-led reconstruction

The first seven terminal attempts mixed several independent costs and led to
overly local fixes. Attempt 8 isolates the actual sequence.

For `20260711_m00_680126a_gpt2_9n_50x10`:

- all eight bfloat16 proposal authority objects were durable at timestamps
  1783731029–1030;
- all eight proposal manifests were durable at 1031–1034;
- successor params were durable at 1037;
- successor outer state, commit, frontier, and head were durable at 1038;
- no `transition_committed` event followed before operator termination;
- the head and immutable object set prove that CAS sequence 1 succeeded;
- production replay then entered `validate_tensor_payload`, whose bfloat16
  finite check is a Python scalar loop over about 124 million elements per
  proposal.

The retained one-node payload benchmark also proves that raw read, SHA, and
vectorized validation are not intrinsically slow: all eight bfloat16 payloads
completed parallel full validation in less than one second on a compute node.

## Root causes

### R1 — Validator routing was based on file format, not workload

The dependency-free protocol validator is correct for bounded fixtures and
portable contract tests. It is not a production large-tensor implementation.
Catalog validation was moved to the vectorized production validator, but full
production replay still called the scalar validator.

### R2 — Steady-state replay and recovery replay were treated as one operation

The syncer performs full replay before preparation and again after every CAS.
Even after replacing the scalar validator, repeatedly reading and validating
the entire prefix makes steady-state work grow quadratically with transition
count. Strict full replay is necessary at process start, takeover, checker, and
explicit recovery boundaries; it is not necessary after a directly observed
successor CAS when the process already owns a verified immutable prefix.

### R3 — Timing did not cover the transaction's full critical path

Existing `read_seconds` fields are hard-coded to zero and
`global_interval_seconds` combines waiting, catalog, immutable publication,
CAS, replay, and export. This made different bottlenecks look identical.

### R4 — Correct immutable publication was centralized unnecessarily

Earlier attempts made the syncer write and fsync every large proposal payload.
Learner-side content-addressed immutable publication is valid protocol behavior:
it happens before the discovery marker, cannot mutate the head, and leaves only
an unreachable orphan on failure. This part of the current design is retained,
but tests must continue to prove learners have no head-CAS surface.

## Revised replay model

### Strict full replay

Used for process open/resume, takeover, checker, analysis, explicit verification,
and any incremental fallback. It must:

- walk the complete head/frontier/commit ancestry;
- verify every referenced manifest and content digest;
- route production proposal tensors through the production vectorized validator;
- verify params/outer-state pairing and all selection/causal/consumption rules;
- reconstruct an immutable `ReplayResult` and `RuntimeView` from no local state.

### Verified incremental successor extension

Used only inside a process that already holds a strict verified `ReplayResult`.
It may extend that result by one directly observed successor if and only if:

- the newly loaded head names commit sequence `prior + 1`;
- the new commit's parent ID and logical parent-head token match the cached head;
- the new frontier's parent digest matches the cached frontier;
- all newly referenced proposal manifests/payloads and successor params/outer
  state pass the same production verification rules;
- selection, lineage, interval, staleness, weights, fragments, scheduler, and
  consumption are valid relative to the cached verified prefix;
- the resulting prefix digest equals the digest produced by strict full replay
  in tests.

The cache is process memory only. It is never serialized and never authoritative.
On head jump, conflict, mismatch, missing cache, response ambiguity, or any
verification error, the path falls back to strict full replay.

## Implementation order

1. Replace the scalar validator in production replay with the vectorized
   production validator. Keep the reference replay dependency-free.
2. Add stage timing for catalog validation, proposal immutable observation,
   aggregation, successor immutable publication, CAS, post-CAS replay, and
   materialized export.
3. Add an in-memory verified replay anchor to `ProductionTransactionalLog`.
4. Implement a one-successor incremental verifier without changing committed
   schemas or digests.
5. Route production prepare and post-CAS `RuntimeView` construction through the
   anchor; retain strict full replay for fresh open and every fallback.
6. Audit fragment mode through the same mechanism.

## Required tests before another submission

- strict production replay never calls the scalar finite-value iterator;
- strict and incremental results are equal for every prefix of a 10-transition
  full run and a multi-fragment run;
- cache deletion followed by strict replay yields the same digest;
- head jump and CAS conflict force strict replay/reselection;
- delayed response loss followed by a successor resolves by ancestry;
- corrupt new proposal, params, outer state, commit, or frontier fails before
  anchor replacement;
- corrupt historical state is detected by a forced strict replay;
- listing omission/reorder plus process kill recovers without durable selection;
- learner source can publish immutable proposal objects but cannot reference
  head CAS operations;
- one-node dependency-complete suite and log-only full/fragment recovery pass;
- two-node backend/transaction/takeover qualification passes on the same clean
  commit.

Only after these conditions have evidence may one new nine-node terminal job be
submitted. If that job fails, submissions stop again and its complete stage
timing is reviewed before any new runtime change.

## Non-claims

- This does not introduce P05 lease/fencing.
- It does not make an in-memory anchor authoritative or durable.
- It does not weaken fresh-process full replay.
- It does not treat latest/checkpoints/telemetry as authority.
- It does not claim that the current nine-node terminal gate has passed.
