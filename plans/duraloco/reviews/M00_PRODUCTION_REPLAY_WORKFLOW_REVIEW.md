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

### R2 — Large immutable objects were reverified as if they could mutate

The syncer performs full replay before preparation and again after every CAS.
Even after replacing the scalar validator, repeatedly reading and validating
every historical tensor makes large-object work grow quadratically with
transition count. The manifests and causal rules are cheap enough to replay
strictly every time; content-addressed tensor objects that were already
verified in this process do not need another read and decode.

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

### Verified immutable-object memoization

Used only inside a process that already completed production replay. Every
call still reloads the head, walks the complete manifest ancestry, and applies
the same causal verifier. A large tensor read/decode may be skipped only when:

- its full `ObjectRef` identity `(key, sha256, size)` was successfully verified
  earlier by the same process;
- the storage contract continues to provide immutable-create semantics;
- the current replay reaches that reference through a freshly verified
  manifest chain.

The cache is process memory only. It is never serialized and never authoritative.
It is updated only after a complete replay succeeds. Fresh open, explicit
verification, CAS conflict/response ambiguity, and cache deletion use an empty
cache and therefore perform strict full tensor replay.

This deliberately keeps one causal replay implementation instead of adding a
second incremental state machine. At the M00 ten-transition bound, rereading
small canonical manifests is preferable to duplicating lineage, staleness,
selection, scheduler, and prefix-digest logic. Stage timings will determine
whether a later phase needs a separately specified incremental manifest index.

## Implementation order

1. Replace the scalar validator in production replay with the vectorized
   production validator. Keep the reference replay dependency-free.
2. Add stage timing for catalog validation, proposal immutable observation,
   aggregation, successor immutable publication, CAS, post-CAS replay, and
   materialized export.
3. Add process-local verified immutable-object memoization to
   `ProductionTransactionalLog` without changing committed schemas or digests.
4. Route production prepare and post-CAS `RuntimeView` construction through
   the memoized strict verifier; retain empty-cache full replay for fresh open
   and every explicit fallback.
5. Audit fragment mode through the same mechanism.

## Required tests before another submission

- strict production replay never calls the scalar finite-value iterator;
- memoized and empty-cache strict results are equal for every prefix of a
  10-transition full run and a multi-fragment run;
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

The runtime ladder now includes a read-only one-node replay benchmark against
the preserved sequence-1 authority from attempt 8 before the ordinary one-node
and two-node requalification jobs. It must prove that strict CPU and GPU replay
produce the same digest, record their wall times, and show that a second
memoized replay performs zero reads of proposal/params/outer tensor objects.

## Non-claims

- This does not introduce P05 lease/fencing.
- It does not make an in-memory anchor authoritative or durable.
- It does not weaken fresh-process full replay.
- It does not treat latest/checkpoints/telemetry as authority.
- It does not claim that the current nine-node terminal gate has passed.
