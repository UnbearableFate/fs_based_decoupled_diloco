# DuraLoCo Code Review — 2026-07-12

Reviewer: Claude (full read of the core runtime; targeted read of support modules)
Basis: branch `codex/duraloco-p07-distributed-lifecycle`, commit `c099adc` (P07 completed, P08 next)

Files read line-by-line: `atomic_io.py`, `tensor_codec.py`, `paths.py`, `syncer.py`,
`learner.py`, `proposal_catalog.py`, `outer_optim.py`, `merge.py`, `retention.py`,
`hf_data.py`, `liveness.py`, `runtime_view.py`, `lifecycle_cli.py`, `fragment_scheduler.py`,
`coordination/lease.py`, `storage/posix.py`, `log/production.py`, `log/gc.py`,
`log/reachability.py`, `syncer_core/{aggregation,planning}.py`,
`distributed_syncer/committer.py`. Skimmed: `log/replay.py`, `log/commit.py`,
`log/snapshot.py`, `learner_protocol/*`, `protocol/*`, plus a `ruff` static pass.
Not reviewed in depth: `analysis.py`, `eval_lm_harness.py`, `testing/*`, `log/model.py`,
`coordination/state_machine.py` — findings there may exist beyond this list.

Severity: **H** = correctness/evidence bug, fix before relying on affected path;
**M** = latent bug, wrong-under-conditions, or major inefficiency; **L** = cleanup.

---

## 1. Correctness bugs

### H1. `fragment_id` is clobbered inside the fragment learner's inner-step loop
`fs_diloco/learner.py:851` — inside `run_fragment_learner`, the token-accounting loop

```python
for fragment_id in tokens_since_fragment_load:
    tokens_since_fragment_load[fragment_id] += step_tokens
```

reuses the name `fragment_id` that was set by `select_fragment(...)` at
`learner.py:811`. After the first training step, `fragment_id` is whatever key
iterates last in `tokens_since_fragment_load` (in practice the highest fragment
id). Everything after the inner loop — `interval.base.fragment_versions[fragment_id]`,
`extract_fragment(flat, fragment_index, fragment_id)`, and the
`write_fragment_update(fragment_id=...)` sidecar metadata — uses the clobbered
value, while the authority-side publication (`learner_protocol/publication.py:121`)
uses the correct `interval.fragment_id`. With `num_fragments > 1` this means:
round-robin scheduling is silently defeated (every update targets the last
fragment), and the sidecar metadata and the authority publication disagree about
which fragment an interval covers.

Currently dormant because every DuraLoCo config runs `fragments.enabled: false`
(one fragment), and `tests/test_fragment_pipeline_smoke.py` only asserts that
config files exist — no functional multi-fragment coverage.

**Fix:** rename the loop variable
(`for tracked_fragment_id in tokens_since_fragment_load:`) and add a real
multi-fragment unit/integration test that runs `num_fragments >= 2` and asserts
each published update's metadata `fragment_id` equals `interval.fragment_id`
and follows the round-robin schedule.

### H2. Committer crash paths commit a lying `completed` stop fact
`fs_diloco/distributed_syncer/committer.py:768-780` — `run_committer` initializes
`stop_reason = "completed"` and, unlike `syncer.py` (which has
`except Exception: stop_reason = "error"`), has no except clause. Any exception
(e.g. `_wait_for_result` timeout, storage error) reaches the `finally` block,
which then commits an authoritative stop with reason `"completed"`. A crashed
run becomes indistinguishable from a successful one in the committed history —
this poisons exactly the terminal evidence the P07/P11 acceptance gates rely on.

**Fix:** mirror `syncer.py`: add `except Exception: stop_reason = "error"; raise`
before the `finally`, and treat non-successful reasons accordingly downstream.

### H3. Committer `finally` block can raise and can dereference `None`
`fs_diloco/distributed_syncer/committer.py:768-781`:

- `log.commit_stop(...)` is called without catching `CommitConflict`. If a
  standby took over (stale owner) or the failure happened before owner
  activation (`_require_owner_token` raises), the `finally` raises and masks
  the original exception.
- If `commit_stop` fails or is skipped, `view.authoritative_stop` can still be
  `None`, and `_publish_stop(..., reason=view.authoritative_stop.reason)`
  raises `AttributeError` inside `finally`.

**Fix:** copy the pattern from `syncer.py:1048-1108`: wrap `commit_stop` in
`try/except CommitConflict`, rebuild the view, and only publish `stop.json`
when `view.authoritative_stop is not None`; log
`stop_not_published_without_authority` otherwise.

### M4. Committer has no head-conflict replay path
`fs_diloco/distributed_syncer/committer.py:592-604` — `prepare_transition` /
`commit_prepared` are called without the `except (CommitConflict, InjectedTimeout):
replay and continue` handling that `syncer.py:934-940` has. Any lost CAS or a
stop/epoch bump committed by another process crashes the committer (and, with
H2, records a false `completed` stop). Single-committer + fencing makes this
rare, but the takeover race is exactly the scenario P06C is supposed to survive.

**Fix:** wrap the prepare/commit section in the same conflict handler: on
`CommitConflict`, `build_runtime_view(log, force_full=True)`, reload committed
tensors, and continue (or exit cleanly if the head shows an authoritative stop).

### M5. Lease is not renewed while waiting for executor results
`fs_diloco/distributed_syncer/committer.py:569-576` — `_wait_for_result` can
block up to `config.liveness.no_progress_timeout_seconds` polling for prepared
markers, with no lease renewal inside the loop. If executors are slow, the
lease expires, a standby fences a new epoch, and the old committer's next
commit fails with `CommitConflict` (see M4). The `_run_lifecycle_substage`
helper was built for exactly this "long substage + heartbeat" pattern but is
only used for lifecycle work.

**Fix:** run `_wait_for_result` through `_run_lifecycle_substage` (or renew
inside its polling loop with the same `renew_interval_seconds` cadence). The
same reasoning applies, more mildly, to `syncer.py`'s `collect_candidates`
grace-window wait: document/assert `grace_window < lease_ttl - renew_margin`,
or renew inside the scan loop.

### M6. `resolve_mutation` indexes `replay.commits` by commit_seq
`fs_diloco/log/production.py:1023` — `commit = replay.commits[commit_seq - 1]`
assumes the commits list starts at seq 1. After P07 snapshot compaction, a
snapshot+suffix replay may not contain the physical prefix; if `replay.commits`
is ever suffix-only (as `commit_snapshot`'s embedding loop suggests it can be),
this returns the wrong commit or raises `IndexError` when resolving a retried
request that committed before the snapshot base. Same fragile assumption in
`_optimizer_transition_count`'s fallback (`production.py:273-277`).

**Fix:** look the commit up by `commit_seq` explicitly
(`next(c for c in replay.commits if c.commit_seq == seq)`) or keep a
`commits_by_seq` mapping in `ReplayResult`; add a regression test that resolves
a pre-snapshot-base request id after compaction.

### M7. Heartbeats are not generation-scoped
`fs_diloco/learner.py:249-262` (`write_heartbeat` payload has no
`run_generation`), `fs_diloco/syncer.py:318-329` (`_heartbeat_snapshot` checks
only `run_id`), `fs_diloco/liveness.py:40-54` (same). After a generation bump
under the same `run_id`/shared root, stale heartbeats from the previous
generation with high `last_local_step` can satisfy
`finite_local_training_complete` and enable terminal drain / early quorum
relaxation in the new generation.

**Fix:** add `run_generation` to the heartbeat payload and filter on it in
`_heartbeat_snapshot` and `validate_heartbeat`. (Heartbeats stay observational;
this just stops cross-generation observation bleed.)

### M8. Any syncer/committer exception permanently terminates the generation
`fs_diloco/syncer.py:1044-1062` — on any exception, the owner commits an
authoritative stop with reason `"error"`, and every later resume sees
`authoritative_stop is not None` and exits immediately. A transient failure
(OOM, Lustre hiccup escaping as an unexpected exception type) turns into a
permanent terminal fact requiring a manual generation bump. This is a
deliberate fail-closed choice, but it conflicts with the project's own
durability story ("crash → restart → resume").

**Fix (design decision to make explicitly):** either (a) do not commit a stop
on `"error"` — release/let the lease lapse so a standby or restart resumes the
generation, and reserve committed stops for deliberate terminal reasons; or
(b) keep committing `error` stops but add a fenced `resume`/`unstop` control
transition so operators can reopen a generation without a new one. Document
whichever is chosen in `docs/duraloco/protocol_v2.md`.

### M9. Concurrent first-time lease acquisition crashes instead of retrying
`fs_diloco/coordination/lease.py:244-269` — in `acquire`, the `NotFound` branch
catches only `InjectedTimeout` around `put_if_absent`. If two fresh processes
race, the loser gets `ImmutableConflict` (from `posix.put_immutable`), which is
neither caught there nor converted to `CoordinationConflict`, so a standby's
retry loop (`syncer.py:491-503` catches only `CoordinationConflict`) crashes.

**Fix:** catch `ImmutableConflict` in the `NotFound` branch, re-`load()` the
lease, return it if `_same_request`, else raise `CoordinationConflict`.

### M10. Derived-view writes are not directory-fsynced
`fs_diloco/atomic_io.py:23-69` — `atomic_write_*` fsyncs the temp file but never
the parent directory, unlike `storage/posix.py:_publish` which does both. The
files written this way include `param_index.json`, `fragment_index.json`,
`latest.json`, `stop.json`, and the resolved config. `latest.json`/heartbeats
are observational, but `param_index.json` / `fragment_index.json` are required
by `resume_generation` — after a node crash shortly after `initialize_generation`,
the rename may not be durable and resume fails with `FileNotFoundError` even
though the authority log is fine.

**Fix:** add an optional `fsync_dir=True` parameter to the atomic writers (open
the parent with `O_DIRECTORY` and fsync, as `posix.py:_fsync_directory` does)
and enable it for the control-plane files needed by resume. Alternatively,
rebuild `param_index`/`fragment_index` from the committed `RunSpec` digests on
resume instead of trusting sidecar files.

### M11. Cross-node `flock` on Lustre is assumed, never probed
`fs_diloco/storage/posix.py:200-248` — all CAS/immutable-create atomicity rests
on `fcntl.flock` providing cross-node mutual exclusion. On Lustre this is only
true when the client mounts with `-o flock`; with the common `localflock`
option, locks are node-local and two committers on different nodes could both
pass `conditional_replace`'s read-check-write, breaking the single-head CAS.
`storage/capability_probe.py` probes directory fsync but not lock scope.

**Fix:** add a two-process (ideally two-node, run in preflight on Miyabi) lock
probe to `capability_probe.py`, record the mount option in run manifests, and
fail closed at backend construction when cross-node exclusion cannot be
demonstrated. P11's preflight should assert it per job.

### L12. Dead `loss is None` check
`fs_diloco/learner.py:418-421` — `loss = output.loss / accum` runs before
`if loss is None:`; if `output.loss` were `None` the division raises `TypeError`
first. Move the check above the division.

### L13. Catalog quarantine mislabels unsupported dtypes
`fs_diloco/proposal_catalog.py:151` — `_SAFE_TO_PROTOCOL[header.dtype]` raises
`KeyError` for e.g. `I64` payloads, which the scan handler records as
`MALFORMED_METADATA` (`proposal_catalog.py:273-280`). Safe, but the quarantine
record misstates the cause. Map missing dtypes to a specific
`PAYLOAD_DTYPE` `ProtocolError`.

### L14. Capsule cadence env vars parsed in the hot loop
`fs_diloco/learner.py:79-98` — `FS_DILOCO_CAPSULE_CADENCE` /
`FS_DILOCO_CAPSULE_MAX_SEQUENCE` are re-read and re-validated on every adoption;
a malformed value crashes mid-training instead of at startup, and the knob is
invisible to the resolved-config record. Parse once at startup and move into
`Config` (keep env override if needed, but record it in the resolved config).

---

## 2. Performance and efficiency

### H15. `PosixStorageBackend.list_prefix` scans the whole tree and reads every object
`fs_diloco/storage/posix.py:573-589` — `list_prefix` does `self.root.rglob("*")`
(entire namespace, regardless of prefix) and then calls `_read_path` on every
file, which reads and SHA-checks the **full payload bytes** just to produce a
key listing. Callers include `build_reachability`'s inventory
(`log/reachability.py:144`), `_wait_for_result`'s 0.1 s marker polling
(`committer.py:150`), and recovery scans. On a real run this is O(total stored
bytes) per poll/GC pass on Lustre — it is very likely the dominant cost in the
observed lifecycle latency growth (45 s → 141 s per cycle in the P07 D8-R2
report).

**Fix:** (a) walk only `contained_path(root, prefix)`'s subtree; (b) validate
lazily — for listing, check the envelope magic/header only (bounded read of
`_MAX_HEADER_BYTES`), not the payload digest. Keep full verification in
`get`/`verified_get`.

### H16. `head()` reads the full object
`fs_diloco/storage/posix.py:526-531` — `head` goes through `_read` and therefore
reads and hashes the entire payload. `GcMarkV1.create` heads every candidate,
and the committer's lifecycle inventory substage sums `head(key).size` over the
whole inventory (`committer.py:690-694`) — each a full read of the store.

**Fix:** implement `head` from the envelope header alone (read magic + header,
trust the recorded sha/size; the envelope header is itself checksummed). Full
byte verification stays in `get`.

### M17. `range_get` reads the whole object
`fs_diloco/storage/posix.py:533-538` — `range_get` is `self.get(key)[start:end]`
while `capabilities.range_reads=True`. P08's streaming reducer will depend on
real range reads. Implement seek-based reads: parse the header, then `pread`
only `header_end + start .. header_end + end`; verify against a per-chunk or
whole-object digest policy decided in P08 (D-0802/D-0805 territory).

### M18. Catalog rescans re-read and re-validate every payload; all payloads held in memory
`fs_diloco/proposal_catalog.py:137-160, 230-312` and `syncer.py:346-374` —
`collect_candidates` calls `catalog.scan` in a loop (every `scan_interval`
within the grace window); each scan re-reads every pending payload from Lustre
and reruns the finite-check on the validation device. Every `CatalogEntry` also
retains the full payload bytes (`payload: ValidatedProductionPayload`), so peak
memory is O(pending proposals × fragment size) — the exact "q × fragment
residency" P08 wants to eliminate.

**Fix:** cache validated entries across scans keyed by
`(path, size, mtime, metadata_sha256)` and skip revalidation on hits; store
only the digest/shape in the entry and re-read payload bytes for the selected
quorum at load time (or hold weak/LRU-bounded buffers). This belongs naturally
to P08 Loop 3 (validation reuse) — the plan already names it; the point here is
that the *scan loop*, not just the executor, needs the token reuse.

### M19. Every commit rewrites every fragment file and the full materialized model
`fs_diloco/syncer.py:145-206` — `publish_materialized_view` saves **all**
fragment weights and outer states (unchanged versions included; same content to
the same versioned path), plus a full `materialize_full_from_fragments` +
`save_global_weights` of the whole model, on every commit. With F fragments
that is ~2× model bytes per commit even though only one fragment changed. The
config key `fragments.materialize_full_every_events` exists (`config.py`) but is
read nowhere in the runtime.

**Fix:** skip `save_fragment_weight`/`save_outer_state` when the target
versioned file already exists (versions are content-stable); honor
`materialize_full_every_events` for the full materialization (learners can
already adopt per-fragment via `latest_kind=fragment`), or delete the dead
config key if full-every-commit is intentional.

### M20. Learner update payloads are written twice and read back once
`fs_diloco/learner.py:503-584, 587-672` — `write_update`/`write_fragment_update`
save the tensor into `updates/pending/`, immediately `read_bytes()` the file
back, then `LearnerPublisher.publish` writes the same bytes again into the
authority store. That is 3× payload I/O per interval and 2× steady storage
until retention runs.

**Fix:** serialize to memory once (`safetensors.torch.save`), write the
authority object from that buffer, and make the pending sidecar `file_path`
point at the authority payload (or hardlink into the mailbox). The catalog
already resolves `file_path` through `_contained_payload`, so keeping one copy
under the shared root works.

### M21. O(N²) lineage validation in `prepare_transition`
`fs_diloco/log/production.py:774-798` — for each selected proposal, the code
iterates over **all** consumed proposals in history to enforce sequence
monotonicity and same-base overlap. Per-commit cost grows linearly with run
length (bounded only by snapshot compaction). `RuntimeView` already maintains
`last_committed_sequences` and `consumed_interval_bases`; `ReplayResult` should
expose the same per-lineage maxima/mapping so this check is O(selected).

### L22. `_run_lifecycle_substage` builds a new thread pool per substage
`committer.py:106-135` — minor; reuse one single-thread executor per committer
process.

### L23. `put_immutable` full-byte comparison
`posix.py:419-432` — idempotency check compares full bytes; the envelope header
already stores the sha256, so digest comparison suffices once `head` is
header-only (see H16).

---

## 3. Dead code, duplication, hygiene

- **L24. `fs_diloco/merge.py` is runtime-dead.** Only `tests/test_merge.py`,
  `test_fragment_merge.py`, `test_syncer_selection.py` import it; the live path
  uses `syncer_core/planning.py` + `testing/deterministic_reference.py`. Either
  delete it (and retarget the tests at `syncer_core`), or mark it explicitly as
  the legacy-baseline reference. Keeping two weighting implementations invites
  silent divergence from the committed `weighting_config`.
- **L25. `stop_requested` and `fragment_stop_requested` are identical**
  (`learner.py:335-344`); keep one.
- **L26. Unused imports** flagged by ruff: `syncer.py` (`hashlib`, `OwnerToken`,
  `LEARNER_STATUS_STOPPED`), `committer.py` (`hashlib`, `_candidate_paths`),
  `distributed_syncer/cli.py`, `executor.py`, `bootstrap.py`,
  `runtime_view.py` (`FrontierManifest`), `proposal_catalog.py`
  (`canonical_digest`). Run `ruff --fix` and add ruff (F, B rules) to the local
  static gate — several B-class findings above (B023, B904, B006 in
  `protocol/schemas.py:20`) would have been caught at commit time.
- **L27. B023 lambdas in committer lifecycle substages**
  (`committer.py:628,692`) — currently safe (invoked synchronously in the same
  iteration) but fragile; bind with default args
  (`lambda rid=snapshot_request_id: ...`).
- **L28. `wikitext` streaming mode is misleading** (`hf_data.py:225-253`):
  with `streaming=True` the code still materializes all rows into memory, and
  `dataset.shard(..., contiguous=True)` isn't supported on iterable datasets.
  Either reject `streaming: true` in config validation or implement it.
- **L29. Repo root is littered with PBS logs** (`duraloco_*.o*`, `*.pbs.o*`).
  They appear untracked-but-ignored; move job output into `logs/pbs/` via the
  PBS `-o/-e` options in P11's standardized scripts so the tree stays navigable.
- **L30. Test gap:** there is no test that drives `run_fragment_learner` with
  `num_fragments >= 2` end-to-end (see H1), none for lease-acquire races (M9),
  and none for committer crash-path stop semantics (H2/H3). Add these alongside
  the fixes.

---

## 4. Suggested fix order

1. **Before P08 profiling starts** (results would otherwise be measured on a
   misbehaving base): H2, H3, M4, M5 (committer evidence + survival), H15, H16
   (otherwise profiles measure `rglob` + full-read pathology, not the design),
   M11 (validate the platform assumption the whole CAS story rests on).
2. **With P08 Loops 2–3** (they are the same work): M17, M18, M19, M20, M21.
3. **Anytime, low risk:** H1 (+ its test), M6, M7, M9, M10, M8 (decision),
   L12–L30.
