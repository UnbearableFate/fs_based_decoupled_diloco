# DuraLoCo Decisions

Each decision is frozen for P00–P02 and remains reversible only through a new
run generation plus an explicit compatibility amendment.

## D-0001 — Authority model

- Context: the prototype distributes facts across files, `latest.json`, and SQLite.
- Candidates: retain distributed authority; declare SQLite authoritative; use a committed log with one head.
- Choice: record the legacy split honestly; target a parent-linked immutable transition log whose single CAS head is authoritative. Caches/listings are rebuildable.
- Rejected: distributed or SQLite authority cannot prove cache-free prefix recovery.
- Compatibility: P00–P02 do not promote the v2 path or change legacy defaults.
- Reversibility: backend/layout adapters may change, but changing the single-authority model requires a new protocol/run generation.

## D-0002 — Failure model

- Context: safety claims need precise omissions and storage assumptions.
- Candidates: process-only; crash/omission/duplication/corruption; Byzantine/provider-loss.
- Choice: cover process/node loss, timeout before/after effect, duplicate/reordered/stale/future input, detectable corruption, partitions, competing writers, and lifecycle crashes.
- Rejected: process-only is too weak; Byzantine and confirmed-durable provider loss are outside initial scope.
- Compatibility: legacy evidence is not upgraded to the broader guarantee.
- Reversibility: stronger failure modes may be added with new validation/proof gates.

## D-0003 — Numeric reproducibility

- Context: global replay and full learner replay have different determinism limits.
- Candidates: universal bitwise; digest-stable decisions plus tolerance tensors; unconstrained approximate replay.
- Choice: audit mode provides canonical metadata and deterministic float64 CPU reference; performance tensor paths use declared tolerances and implementation digests.
- Rejected: universal cross-GPU bitwise replay is not credible; unconstrained tolerance is not auditable.
- Compatibility: legacy Torch formulas define the P02 oracle comparison.
- Reversibility: tolerances/implementations are versioned and cannot change within a run.

## D-0004 — Recovery semantics

- Context: fragment proposals omit private learner state.
- Candidates: call all recovery exact; global exact only; three explicit levels.
- Choice: distinguish global exact prefix recovery, non-exact warm learner restart, and capsule-dependent exact learner restart.
- Rejected: equating a proposal or global frontier with a full learner checkpoint.
- Compatibility: current resume behavior is classified as legacy/warm unless complete private state is demonstrated.
- Reversibility: exact capsules can be added without weakening global semantics.

## D-0005 — Communication non-claim

- Context: durable storage targets long local intervals, not step-synchronous collectives.
- Candidates: claim general communication replacement; scope to low-frequency asynchronous exchange.
- Choice: explicitly do not claim replacement of NCCL/RDMA high-frequency synchronization.
- Rejected: a universal replacement claim exceeds the mechanism and evidence.
- Compatibility: no runtime effect.
- Reversibility: only new experiments could broaden the research claim.

## D-0101 — Identity JSON numeric domain

- Context: host-dependent JSON floats undermine stable content IDs.
- Candidates: JSON numbers; decimal strings; prohibit floats in identity-bearing canonical JSON.
- Choice: prohibit Python/JSON floats in canonical identity bodies; record protocol weights as `float.hex` strings.
- Rejected: implicit decimal rendering and NaN/Inf.
- Compatibility: observational timestamps remain strings.
- Reversibility: a future canonical-decimal schema needs a new protocol version.

## D-0102 — Proposal identity

- Context: proposal identity must bind lineage and payload without self-hash recursion.
- Candidates: random UUID; tuple only; content-derived ID over a body without `proposal_id`/observational fields.
- Choice: `p-<sha256>` over canonical identity and content fields with `proposal_id` and `created_at` omitted.
- Rejected: UUID cannot independently detect content conflict; self-hash is recursive.
- Compatibility: the v1 adapter labels legacy IDs but cannot write v2 authority.
- Reversibility: identity changes require a new run generation/protocol version.

## D-0103 — Initial payload kind

- Context: P02 needs a single unambiguous optimizer input.
- Candidates: local end weight; pseudo-gradient; both in one run.
- Choice: `pseudo_gradient` is the initial authoritative kind; the schema can parse `local_end_weight`, but a run manifest freezes exactly one kind.
- Rejected: mixing payload kinds in a run complicates deterministic semantics.
- Compatibility: legacy local-weight manifests are read-only adapter input.
- Reversibility: new run generations may select another supported kind.

## D-0104 — Finite checks

- Context: sampling may miss NaN/Inf entering correctness transitions.
- Candidates: sampled; always full; selectable mode.
- Choice: correctness/audit validation scans every tensor value; later performance mode may explicitly sample only after pre-commit full validation evidence exists.
- Rejected: implicit sampling in correctness suites.
- Compatibility: no legacy default change.
- Reversibility: sampling is an explicit performance policy, never a silent downgrade.

## D-0105 — Quarantine layout and retention

- Context: invalid proposals must neither crash scanners nor disappear.
- Candidates: delete; mutable error log; immutable typed record keyed by observation/content.
- Choice: idempotent immutable quarantine records under an isolated v2 namespace; identity-content conflicts escalate to fatal protocol conflict.
- Rejected: deletion loses evidence; mutable records obscure repeated observation.
- Compatibility: P01 provides an in-memory/reference registry before a storage backend exists.
- Reversibility: backend layout can change while canonical quarantine records remain stable.

## D-0106 — v1 adapter scope

- Context: v1 lacks required v2 causal and identity fields.
- Candidates: silently accept; rewrite in place; read/inspect plus explicit conversion context.
- Choice: read-only parse/inspect by default; optional conversion constructs a new v2 object in a distinct namespace and never writes authority.
- Rejected: implicit acceptance or in-place rewrite.
- Compatibility: legacy runs remain untouched.
- Reversibility: a later migration tool requires its own destructive-operation gate.

## D-0201 — Reference head topology

- Context: P02 needs an unambiguous transition order.
- Candidates: per-fragment heads; transaction coordinator; one global head.
- Choice: a single global head totally orders every reference commit.
- Rejected: multiple heads add atomicity questions before the base proof exists.
- Compatibility: per-fragment versions remain in the frontier.
- Reversibility: sharding requires a new proof, ADR, and migration plan.

## D-0202 — Eligibility after CAS conflict

- Context: a failed prepared commit has no authority.
- Candidates: drop selected proposals; keep old validation; return proposals for authoritative revalidation.
- Choice: proposals become tentative candidates again and must be fully revalidated against the new head.
- Rejected: dropping loses valid work; reusing validation permits double inclusion/stale bases.
- Compatibility: no durable `selected` state exists in the reference model.
- Reversibility: selection policy may supersede/drop explicitly after revalidation.

## D-0203 — Same-session supersession

- Context: multiple proposals from one learner/base can overlap work.
- Candidates: implicit newest-wins; oldest-first; explicit non-overlap lineage plus supersession record.
- Choice: accept only non-overlapping monotonic lineage; use oldest-first selection and explicit supersession/drop decisions.
- Rejected: implicit newest-wins can double-count or erase work.
- Compatibility: v1 ambiguity remains quarantined/compatibility-only.
- Reversibility: another policy must preserve interval non-overlap and record decisions.

## D-0204 — Quorum ordering and fairness baseline

- Context: Python/directory order is nondeterministic and lexical learner order is biased.
- Candidates: arrival order; learner ID; canonical proposal ID with age-credit inputs.
- Choice: P02 canonicalizes eligible proposals by proposal ID; selection inputs/weights are explicit. Dynamic fairness is deferred, but no directory order participates.
- Rejected: arrival/listing order and fixed lexical winner semantics.
- Compatibility: reference traces are stable across process runs.
- Reversibility: later fairness scores become committed decision inputs.

## D-0205 — Reference tensor representation

- Context: P02 must not depend on Torch, filesystem, GPU, or network.
- Candidates: Torch tensors; NumPy arrays; standard-library immutable float tuples.
- Choice: immutable Python float tuples with float64 operations and tolerance `1e-7 + 1e-6*abs(reference)` against legacy FP32.
- Rejected: Torch violates P02 independence; NumPy adds an unnecessary oracle dependency.
- Compatibility: adapter tests compare with the existing Torch implementation on a compute node.
- Reversibility: performance implementations refine to, rather than redefine, this oracle.

## D-0206 — P02 staleness weighting

- Context: the numeric contract requires token/staleness weights, while P02 needs one executable formula.
- Candidates: token-only; exponential decay; rational decay with the research-draft default.
- Choice: use `tokens / (1 + 0.2 * fragment_staleness)` before canonical float64 normalization; commit the normalized hexadecimal weights.
- Rejected: token-only does not satisfy the frozen numeric contract; exponential decay adds a platform-sensitive transcendental operation to the standard-library oracle.
- Compatibility: fresh proposals have staleness zero and exactly preserve token-only legacy comparisons.
- Reversibility: changing the function or lambda requires a new run generation and weighting implementation identity.

## D-0301 — POSIX version tokens and locking

- Context: P03 needs linearizable single-key conditional replace without an external lock service and without relying on mtime.
- Candidates: mtime/inode tokens; sidecar generations; one atomic envelope plus a stable advisory lock file.
- Choice: store payload, a random version token, previous-version token, explicit mutation request ID, size, and SHA-256 in one checksummed envelope; serialize mutations with `flock` on a stable SHA-256-derived lock path; publish with same-directory temp write, file fsync, atomic replace, and parent fsync. Only the same request ID may classify a stale same-data call as an after-effect retry; independent identical CAS calls still have at most one success.
- Rejected: mtime/inode tokens admit aliasing; a separately replaced sidecar creates a two-file atomicity gap.
- Compatibility: the semantic API returns original payload bytes and opaque versions; legacy runtime paths remain untouched.
- Reversibility: another backend may use provider generations/ETags if it passes the same conformance and race gates.

## D-0302 — Directory fsync capability downgrade

- Context: parent directory fsync is required for the declared POSIX durability sequence but may be unsupported by a target filesystem.
- Candidates: ignore errors; always fail; probe and fail closed only when required.
- Choice: probe and record directory-fsync support; a backend configured with `require_directory_fsync=true` fails closed when unsupported, while audit-only mode reports the downgrade without extending durability claims.
- Rejected: silently ignoring the result would overclaim durability.
- Compatibility: P03 reports the observed Miyabi capability and scopes claims to the declared failure model.
- Reversibility: capability policy is configuration, not object layout.

## D-0303 — Verified-read correctness mode

- Context: every authoritative read must detect short/corrupt objects.
- Candidates: sampled verification; metadata-only verification; always verify.
- Choice: P03 always parses the envelope and verifies payload size and SHA-256 for `get`, `head`, and `range_get`; performance sampling is deferred.
- Rejected: sampling is insufficient for the correctness oracle.
- Compatibility: callers receive typed `IntegrityError` instead of unchecked bytes.
- Reversibility: later performance modes must remain explicit and may not be used for commit correctness without new evidence.

## D-0304 — Namespace and key normalization

- Context: the same logical key must map to one object inside an isolated run root.
- Candidates: arbitrary OS paths; normalized POSIX keys; URL-like encoded keys.
- Choice: accept only non-empty canonical relative POSIX keys; reject absolute paths, dot segments, backslashes, controls, symlink traversal, and the backend-reserved lock namespace.
- Rejected: host-path normalization creates aliases and traversal risk.
- Compatibility: Protocol v2 payload keys already use canonical relative POSIX spelling.
- Reversibility: encoded object-store layouts can be added behind the same logical-key validator.

## D-0305 — POSIX error classification

- Context: retry policy must distinguish conflict, visibility, integrity, and infrastructure failures.
- Candidates: expose raw `OSError`; retry every error; typed fail-closed taxonomy.
- Choice: translate ENOENT to `NotFound`, stale versions to `PreconditionFailed`, EIO/ESTALE to retryable `StorageIOError`, permission/quota/space to non-retryable infrastructure errors, and checksum/format failures to `IntegrityError`.
- Rejected: retry-all hides configuration failures and raw errno handling leaks backend details into protocol code.
- Compatibility: existing P02 exception names remain re-exported from `fs_diloco.storage`.
- Reversibility: retryability metadata may be refined without changing semantic outcomes.

## D-0401 — Single authoritative commit point

- Context: one fragment transition publishes params, outer state, a commit record, and a frontier.
- Candidates: publish each object as authority; two-phase coordinator; one global head CAS.
- Choice: immutable objects are only prepared evidence; the conditional replacement of one global head is the sole transition linearization and commit point.
- Rejected: multi-object authority admits partial visibility; a coordinator adds another mutable authority.
- Compatibility: this refines D-0201 over the P03 conditional-replace contract and does not change legacy runtime defaults.
- Reversibility: multiple heads require a new proof, protocol generation, and migration plan.

## D-0402 — Frontier completeness

- Context: a reader must recover the complete committed optimizer view from one reachable object.
- Candidates: fragment-only frontier; external scheduler/cache state; complete frontier with fragment pairs and scheduler state.
- Choice: every frontier records each fragment version, paired params/outer-state refs, producing commit, parent frontier digest, canonical consumed-proposal set, and deterministic scheduler cursor.
- Rejected: external authoritative indexes prevent cache-free replay; fragment-only state omits global scheduling facts.
- Compatibility: the frozen P01 `FrontierManifest` is the wire representation.
- Reversibility: derived fields may be added in a new schema, but committed facts cannot move into a cache.

## D-0403 — Per-fragment immutable optimizer state

- Context: params and outer optimizer state must advance together while payloads may be large.
- Candidates: embed state in the frontier; one mutable state file; separate immutable content-addressed params and outer-state objects.
- Choice: canonical float-hex payload objects are independently content-addressed and referenced as one pair by the commit and frontier.
- Rejected: embedding bloats control objects; mutable state creates a partial-update window.
- Compatibility: P04 uses the P02 standard-library float64 oracle; tensor encodings remain a later performance refinement.
- Reversibility: another payload codec may be selected with an implementation digest and equivalence evidence.

## D-0404 — Authoritative proposal consumption (historical; materialization superseded by D-M0001)

- Context: a proposal must be logically included at most once even if caches disappear or writers race.
- Candidates: mutable SQLite table; separate mutable index; commit selections folded into the frontier.
- Choice at P04 completion: commit records are the authoritative evidence and the frontier carries the canonical cumulative consumed-ID set; SQLite was treated as a rebuildable materialization. D-M0001 preserves the authority choice but deletes that materialization completely.
- Rejected: mutable index authority can diverge from the committed prefix.
- Compatibility: this refines D-0202/D-0203 and preserves explicit revalidation after CAS conflict.
- Reversibility: compaction may summarize the same facts but may not redefine them.

## D-0405 — Canonical transition identity

- Context: retries and independent backends must produce the same logical transition.
- Candidates: random commit IDs; timestamps/listing order; canonical parent, selection, weights, outputs, and implementation digest.
- Choice: proposal IDs are sorted, normalized float weights use exact `float.hex`, payloads use canonical JSON, and commit identity binds the canonical parent-head byte digest plus both output refs and optimizer implementation digest; observational timestamps and backend generation tokens are excluded. The opaque backend generation remains the CAS precondition only.
- Rejected: random or observational inputs prevent deterministic retry and cross-backend equivalence.
- Compatibility: the frozen P01 identities and P02 numeric oracle are reused.
- Reversibility: identity changes require a new run generation/protocol version.

## D-0406 — Orphan definition and retention boundary

- Context: failed CAS and crashes leave complete or partial immutable preparations.
- Candidates: treat listed objects as committed; delete immediately; classify by reachability from the current head.
- Choice: any run object not reachable from the checksum-verified current head/frontier/parent chain is an orphan and never committed. P04 reports but does not delete orphans; retention and grace are deferred to P07.
- Rejected: listing-based authority is unsafe; immediate deletion can race an in-flight prepare.
- Compatibility: P03 listing remains discovery-only and all tests use isolated run prefixes.
- Reversibility: later GC may delete only after the P07 reachability/grace proof.

## D-M0001 — Remove SQLite and reject replacement embedded databases

- Context: P00–P04 left SQLite-backed proposal state, resume dumps, retention hooks, analysis queries, and a P04 replay cache even though the committed transition log/head had become the target authority. The second persistence system adds crash states and operational surface without measured benefit.
- Candidates: keep SQLite as a cache; retain a read-only compatibility layer; replace it with another embedded database; remove database persistence completely.
- Choice: M00 removes SQLite from active source, configuration, CLI, scripts, tests, and new artifacts. No embedded database replacement, read-only compatibility reader, dual-write bridge, or converter is allowed. The committed transition log and one head CAS are the only persistent authority.
- Rejected: a cache still carries schema/migration/locking/dump complexity; a compatibility reader keeps the dependency alive; another database merely renames the same split-state problem.
- Compatibility: old run directories and P00–P04 evidence remain immutable historical artifacts but are not readable by the active runtime.
- Reversibility: adding any database later requires a new protocol decision and evidence that it is purely observational and worth its cost; it may never become authority without a protocol generation change.

## D-M0002 — Replay-derived volatile RuntimeView

- Context: syncer discovery, selection, analysis, and recovery need efficient query state, but correctness must survive loss of all local process state.
- Candidates: persisted materialized view; mutable sidecar indexes; process-local immutable view rebuilt by replay.
- Choice: use a process-local immutable `RuntimeView` derived from checksum-verified committed log/head plus validated discovery inputs. Initial recovery uses full replay; P07 may add snapshot+suffix replay only after digest equivalence gates.
- Rejected: persisted indexes create a second recovery protocol and can silently outrun or lag authority.
- Compatibility: `latest.json`, JSONL, CSV, heartbeats, and metrics remain derived/observational and cannot drive correctness decisions.
- Reversibility: view layout and indexing can change freely because no on-disk view format is part of the protocol.

## D-M0003 — Historical runs use checkpoint-only new-generation bootstrap

- Context: removing SQLite makes exact continuation of DB-era runs impossible without preserving a legacy reader and its semantics.
- Candidates: in-place migration; automatic conversion; read-only DB compatibility; explicit checkpoint bootstrap into a fresh generation.
- Choice: preserve old runs unchanged. An operator may explicitly bootstrap a checksum-verified model checkpoint, and optionally its self-contained optimizer checkpoint, into a new SQLite-free generation with new run/session identities. Imported tensors are initialization data only. This is documented as warm-start, never exact continuation, and imports no proposal/selection/sequence authority from the old DB.
- Rejected: conversion is difficult to verify against split historical state and would make M00 depend on the component being eliminated.
- Compatibility: published historical evidence remains inspectable with its archived environment, outside the active runtime.
- Reversibility: exact legacy migration could only return as a separate, explicitly approved archival tool, not as a production dependency.

## D-M0004 — File/object-native analysis evidence

- Context: analysis and experiment registries previously benefited from SQL-shaped queries but do not need transactional database authority.
- Candidates: SQLite analysis database; external service; canonical manifests/JSONL/CSV with deterministic reducers.
- Choice: manifests and immutable objects are primary evidence; normalized JSONL/CSV tables and deterministic reducers provide analysis inputs and published tables. Every row retains run/commit/config lineage.
- Rejected: a database bundle obscures provenance and introduces another format, migration, and corruption surface.
- Compatibility: P12 clean reproduction must rebuild figures and claims without `.db`, `.sqlite`, or DB dumps.
- Reversibility: deterministic reducers or columnar plain-file exports may be added without changing primary evidence; database generation is outside the supported workflow.

## D-M0005 — Requalify P00–P04 under the SQLite-free design

- Context: historical PASS evidence includes DB-specific configuration and cache-rebuild gates, so it cannot establish correctness of the replacement runtime.
- Candidates: accept historical passes; rerun only modified tests; create M00 as a full requalification milestone.
- Choice: M00 is the new roadmap milestone zero and must produce current evidence for all P00–P04 acceptance IDs. P00-A06 is remapped to the SQLite-free config/CLI surface and fail-closed old keys; P04-A06 is remapped to deleting all local derived state and rebuilding solely from committed log/head. All other semantics remain at least as strict as their historical gates.
- Rejected: partial reuse could miss authority leaks in unmodified-looking paths.
- Compatibility: historical reports are retained and clearly labeled; M00 evidence, not the old SQLite-era pass, authorizes P05.
- Reversibility: the mapping may be tightened by Checker findings but may not be weakened to accept database dependencies.

## D-M0006 — Production tensor codec and implementation identity

- Context: P04's canonical float-hex vectors are a correctness oracle but are not viable for GPT-2 payload volume.
- Candidates: embed tensors in canonical JSON; reference mutable export paths; immutable flat safetensors ObjectRefs.
- Choice: production generations freeze `payload_codec=safetensors-flat-v1`. Each fragment commits one flat float32 params object and one named outer-state safetensors object. The run manifest records the codec, and commits record a digest binding the Torch flat-vector optimizer implementation, frozen optimizer config, and codec identity. Full-vector is fragment zero and uses the same transaction path.
- Rejected: JSON is prohibitively large; mutable export paths break content identity and pairing.
- Compatibility: reference generations retain `canonical-float-hex-v1`; replay dispatches by the immutable run specification.
- Reversibility: a new tensor codec requires a new generation and equivalence evidence.

## D-M0007 — Re-entrant proposal discovery and oldest-first selection

- Context: directory listings can omit, duplicate, and reorder markers, while the P02 checker exposed a runtime/reference policy split.
- Candidates: persist a cursor; newest-wins runtime policy; full rescans plus the frozen oldest-first rule.
- Choice: scanner state is volatile. Every scan validates immutable bytes against the replay-derived view, chooses the lowest sequence/content identity per learner, and canonically orders the final proposal IDs. CAS conflict discards the tentative selection and repeats replay, validation, and selection.
- Rejected: a durable cursor is a second recovery protocol; newest-wins diverges from the P02 semantic kernel.
- Compatibility: old marker files are not accepted unless they contain the M00 run/session/base authority fields.
- Reversibility: scanner batching may change only with omission/reorder/restart equivalence evidence.

## D-M0008 — Telemetry and materialized checkpoints are one-way exports

- Context: learners and operators need efficient latest/checkpoint views, and analysis needs event tables, but none may become authority.
- Candidates: remove exports; let exports drive recovery; regenerate exports after each committed head.
- Choice: `latest.json`, stop, heartbeats, JSONL, CSV, W&B, and materialized safetensors are generated only after successful commit. Analysis verifies/folds the committed prefix before telemetry. Missing or corrupt exports do not change replay and are regenerated by exact resume.
- Rejected: removing latest would unnecessarily rewrite learner polling; reading exports for correctness recreates split authority.
- Compatibility: learner-facing path shapes remain available, with commit/frontier digests added.
- Reversibility: export schemas may evolve independently because committed facts remain in the log.

## D-M0009 — Removed configuration fails closed; historical continuation is warm only

- Context: silently ignoring removed fields could make an operator believe a historical run was exactly resumed.
- Candidates: ignore unknown fields; retain deprecated aliases; strict removal and explicit bootstrap.
- Choice: dataclass config parsing rejects all removed persistence keys and argparse rejects the removed command option. Historical tensors enter only through checkpoint-only bootstrap into a generation greater than zero. `generation_origin` binds source checkpoint digests and `exact_continuation=false` into the immutable run specification.
- Rejected: aliases retain operational ambiguity; an active legacy reader violates M00's deletion contract.
- Compatibility: historical artifacts remain untouched and inspectable only with their archived code.
- Reversibility: exact migration would require a separately approved archival design and cannot become an active runtime dependency.

## M00 完成后的路线修订说明

D-M0010–D-M0012 来自已归档 M00 evidence 的事后提炼，不追溯修改 M00 verdict。
它们在 P05 独立 Checker 显式复核其 evidence attribution 和后续约束后，才作为
P05+ 的规范性路线决策生效。

## D-M0010 — Strict replay with ownership-bound verified-object memoization

- Context: fresh production replay must detect corruption, while rereading every historical GPT-2 tensor after every CAS made the terminal path quadratic and repeatedly revalidated immutable bytes.
- Candidates: always reread every tensor; persist a replay cache; create a second incremental replay state machine; keep one causal replay and memoize verified immutable ObjectRefs in process memory.
- Choice: every replay reloads head and verifies the complete manifest/causal chain. Fresh open, takeover, explicit verify, CAS ambiguity, head jump, cache deletion, and corruption suspicion use an empty cache and strict tensor replay. A process may skip a large tensor read only for a complete `(key, sha256, size)` ObjectRef verified earlier by that process and reached through the freshly verified chain. Memoization updates only after complete replay success, is never serialized, and never crosses owner/session boundaries.
- Rejected: always-reread failed the terminal budget; persisted cache violates M00; a second replay state machine risks semantic drift.
- Compatibility: strict and memoized results are digest-equal for full and fragment prefixes; M00 observed strict CPU/GPU replay was 6.177/6.875s and memoized replay 0.013s.
- Reversibility: P07 snapshot+suffix may accelerate startup only if it remains digest-equal and falls back to empty-cache strict replay.

## D-M0011 — Marker-last learner publication and committed-successor backpressure

- Context: centralized syncer publication serialized large fsyncs, while short post-publication waits allowed learners to flood same-base proposals during slow validation.
- Candidates: syncer republishes payloads; learner publishes mutable latest; learner publishes content-addressed payload then marker and waits for committed successor.
- Choice: learners may publish immutable content-addressed proposal payloads in parallel, then publish the discovery marker last. Learners have no head-CAS surface. After publication they wait for a committed successor, authoritative stop, or explicit no-progress outcome before opening another interval.
- Rejected: syncer republication duplicated I/O; mutable latest creates authority ambiguity; one-scan waiting creates overlapping same-base work.
- Compatibility: bfloat16 proposal transport with float32 aggregation/committed params passed M00 50×10; GC must protect payload-before-marker in-flight objects with grace.
- Reversibility: transport dtype or wait policy changes require implementation identity, numeric evidence, and same-base flood regression.

## D-M0012 — Stage-complete telemetry and terminal retry discipline

- Context: aggregate interval timing hid successive bottlenecks and enabled repeated expensive 9-node guesses.
- Candidates: retain aggregate timing; add complete stage events; automatically resubmit after each local fix.
- Choice: record catalog/rejection, read/SHA/validation, aggregation, outer step, immutable publication, coordination, head CAS, strict/memoized replay, export/adoption, and stop stages. After any non-transient terminal failure, preserve the authority timeline and qstat, write a workflow/root-cause review, prove the repair with a targeted one-node benchmark, rerun 1-node then 2-node qualification on the same clean commit, and permit only one new terminal retry.
- Rejected: aggregate timing cannot attribute root cause; immediate resubmission consumed resources without isolating the path.
- Compatibility: deliberate operator termination remains a real failed attempt with exit status, committed-prefix evidence, and parent lineage.
- Reversibility: telemetry fields may be extended, but stages and retry evidence may not be collapsed or discarded.

## D-0501 — Conditional observational lease and head-committed epoch

- Context: contenders need a bounded liveness mechanism without creating a second optimizer authority.
- Candidates: lease file alone; head-only leader election; conditional lease object followed by a head-committed fencing fact.
- Choice: acquire/renew/release use the storage backend's conditional object operation with stable request identities. Acquisition proposes `head.fencing_epoch + 1`; ownership becomes authoritative only when an `EPOCH_BUMP` control transition commits through the single optimizer head CAS. The lease sequence is monotonic for observation, while committed fencing epochs are the safety order; abandoned candidate epochs may be retried but cannot authorize a writer.
- Rejected: a lease file alone has a head/lease TOCTOU gap; head-only election gives no bounded renewal/expiry signal for standby liveness.
- Compatibility: the first P05 owner performs an epoch bump from the M00 epoch-zero genesis before any optimizer transition.
- Reversibility: lease timing and record layout may change behind the same head-committed fencing contract.

## D-0502 — Clock assumptions affect liveness only

- Context: wall clocks can move and different hosts can disagree near expiry.
- Candidates: trust wall-clock expiry for safety; require synchronized clocks for every commit; use time only to decide when takeover may be attempted.
- Choice: the shared lease records integer UTC nanoseconds, while each process uses its monotonic clock only to schedule its own renew attempts. A declared maximum cross-host wall-clock skew envelope delays takeover: standby waits until recorded UTC expiry plus the allowance before acquire. Clock disagreement may delay or cause competing attempts, but only the epoch/owner/session fact in the head chain authorizes commits.
- Rejected: wall-clock-only fencing admits split brain; per-commit clock synchronization makes storage availability part of safety.
- Compatibility: M00 has no lease and is treated as an unfenced epoch-zero prefix that cannot receive new P05 production commits.
- Reversibility: the skew envelope and clock source may be tightened after measurement without changing committed history.

## D-0503 — Exact owner token checked around the unique head CAS

- Context: a paused leader may resume after standby takeover.
- Candidates: check lease only; check epoch only; bind epoch, owner, and owner-session to both prepared transition and authoritative head.
- Choice: every optimizer or control transition carries an `OwnerToken(epoch, owner_id, owner_session_id)`. Preparation starts from strict/replayed authority and requires an exact match. The audited commit API rechecks that the prepared parent carries the same token immediately before conditional head replacement. Any head change causes full replay and discard/reprepare; a stale token can create only unreachable immutable orphans.
- Rejected: epoch-only permits accidental token sharing; lease-only has no causal connection to the optimizer head.
- Compatibility: reference P04 transactions remain available as a correctness oracle, while the production P05 syncer path requires a token.
- Reversibility: token fields may gain an implementation digest but cannot be weakened below exact equality.

## D-0504 — Stop is a committed control transition

- Context: M00 `stop.json` is derived and can be missing or stale after crash.
- Candidates: mutable stop file; head metadata bit; immutable `STOP` control commit plus frontier projection.
- Choice: the current fenced owner commits a `STOP` control transition containing request ID, reason, owner token, and parent. The successor frontier projects the stop fact. `stop.json` is regenerated after replay and learners treat the committed projection as final authority.
- Rejected: a mutable file creates a second terminal authority; an unlogged head-only bit loses request ancestry and crash evidence.
- Compatibility: an M00 prefix has no committed stop and is interpreted as running until P05 commits one.
- Reversibility: new stop reasons may be added, but clearing or replacing a committed stop requires a new explicitly designed run generation.

## D-0505 — P05 continues only a SQLite-free generation

- Context: coordination must not become a compatibility gateway for historical DB-era runs.
- Candidates: infer and migrate old ownership; allow a DB compatibility flag; require the M00 run manifest and namespace.
- Choice: P05 opens only a Protocol-v2, production-codec, SQLite-free run generation whose committed run manifest matches the requested run/generation. Removed DB flags remain unknown-key errors. Historical tensors enter only through the already-defined new-generation warm bootstrap.
- Rejected: ownership inference from historical local state cannot be replayed from the committed log; a compatibility flag restores dual authority.
- Compatibility: M00 generations are valid prefixes; pre-M00 DB generations are not.
- Reversibility: none within an active generation; another migration design requires a separate archival tool and approval.

## D-0506 — Durable request identity for lease, optimizer, and stop mutations

- Context: response loss must be distinguishable from a new identical operation.
- Candidates: compare payload/effect; retain only process memory; bind canonical request identity into durable mutation evidence.
- Choice: each mutation has a caller-stable request ID and canonical request digest. Lease mutation objects bind the ID/digest and publish immutable request evidence; optimizer and stop request IDs/digests are committed in their transition records. Same ID/same digest returns the original outcome, different ID/same content is an independent competing mutation, and same ID/different digest fails closed.
- Rejected: payload equality repeats the P03 independent-CAS bug; process memory is lost at takeover.
- Compatibility: deterministic M00 optimizer request IDs remain readable; new P05 transitions use explicit owner-scoped IDs.
- Reversibility: retention may compact request results only when ancestry-preserving replay equivalence is proved.

## D-0507 — Response-loss reconciliation walks committed ancestry

- Context: a delayed retry can arrive after one or more successor heads.
- Candidates: compare current head only; inspect observational lease/latest files; search the verified committed chain by request identity and transition digest.
- Choice: commit and stop reconciliation performs strict authority replay after ambiguity and returns `already_committed` only when exactly one matching request ID/digest is present in committed ancestry. Prepared but unreachable objects remain orphans. Lease retry first validates immutable request evidence and the conditional lease record; ambiguity that cannot be uniquely proved is typed inconclusive/fail-closed.
- Rejected: current-head equality loses successful ancestors; observational files can lag or be corrupted.
- Compatibility: extends P04 prepared-transition ancestry resolution without weakening it.
- Reversibility: a P07 snapshot index may accelerate lookup only if it is head-reachable and digest-equivalent.

## D-0508 — Epoch bump is the only lease-to-authority bridge

- Context: separately mutable lease and optimizer head cannot both be authoritative.
- Candidates: copy the lease epoch into each commit without a control transition; atomically mutate lease and head with a coordinator; serialize an epoch bump in the existing head chain.
- Choice: lease acquisition never directly authorizes optimizer work. `EPOCH_BUMP` is an immutable control commit and successor frontier installed by the existing single head CAS. It changes fencing epoch/owner/session but not tensors, fragment versions, scheduler cursor, consumption, or optimizer-transition count.
- Rejected: copying an uncommitted lease epoch leaves a TOCTOU window; a coordinator adds another transactional authority.
- Compatibility: existing replay gains a typed control-transition branch while keeping one causal chain.
- Reversibility: control schema can be versioned in a new generation; the bridge may not bypass head CAS.

## D-0509 — Log sequence and optimizer-transition count are distinct

- Context: lease/stop control facts need ordering but must not change the 50×10 training meaning.
- Candidates: do not sequence control events; count every head transition as an outer step; maintain one commit sequence and an explicit optimizer count.
- Choice: `commit_seq` increments for every optimizer or control transition. `optimizer_transition_count` increments only for optimizer transitions and is projected in every frontier/RuntimeView. Scheduler cursor, fragment versions, selected proposals, and token totals change only on optimizer transitions. Terminal `10` means exactly ten optimizer transitions regardless of epoch bumps or stop.
- Rejected: unsequenced control facts cannot be replayed; counting control as training corrupts stopping and metrics.
- Compatibility: an optimizer-only M00 prefix derives `optimizer_transition_count == commit_seq`.
- Reversibility: none within a generation because the counter is identity-bearing authority.

## D-0510 — Ownership boundary forces empty-cache strict replay

- Context: verified tensor memoization and selected candidates are valid only for the process/owner that established them.
- Candidates: hand cache and selection to standby; retain cache but clear selection; construct a new owner-scoped production log and replay strictly.
- Choice: acquisition/takeover creates a new owner session, discards every tentative selection/validated payload, constructs an empty production replay cache, and completes strict replay before preparing the epoch bump. Only after complete success may that owner build process-local memoization. CAS ambiguity, unexpected head jump, or corruption suspicion clears it again.
- Rejected: cache handoff crosses the verification ownership boundary; retaining selection reuses validation against a stale epoch/base.
- Compatibility: preserves D-M0010 and the M00 stale-cache/corrupt-successor counterexample.
- Reversibility: none without new proof that ownership transfer preserves verification provenance.

## D-0511 — Initial TTL and renewal budget are measured, not safety assumptions

- Context: M00 observed strict replay at 6.177/6.875 seconds and steady post-CAS replay at 4.835–4.940 seconds, but current storage tail and clock skew still require P05 measurement.
- Candidates: make TTL shorter than replay; use a very long fixed lease; start with a conservative bounded configuration and report its measured margin.
- Choice: initial P05 defaults are a 45-second lease TTL, 10-second renewal interval, 15-second minimum renewal margin, and 2-second declared maximum clock-skew allowance. Takeover RTO is measured from expiry eligibility through empty-cache strict replay and epoch-bump CAS. The 1/2/9-node artifacts must report current lease CAS/storage tails and prove the observed margin; failure to renew stops new preparation. Safety remains exact-token/head-CAS based even if any timing target is missed.
- Rejected: a sub-replay TTL guarantees churn; an unbounded lease defeats failover; treating M00 timings as a pass ignores current storage conditions.
- Compatibility: values are new P05 configuration and do not change M00 evidence.
- Reversibility: timing defaults are configuration and may be tuned with new measurements and Checker review.

## D-0601 — Proposal payload remains local end weight

- Context: P06 must bind one proposal to one frozen contribution interval without changing the verified M00 numeric path.
- Candidates: pseudo-gradient; local end weight; configurable per proposal.
- Choice: retain `local_end_weight`; the base frontier and interval cursor make the implied delta unambiguous.
- Rejected: pseudo-gradients change transport/numeric identity; per-proposal choice fragments aggregation semantics.
- Compatibility: preserves M00 bfloat16 proposal transport and float32 aggregation/committed state.
- Reversibility: another payload kind requires a new run generation and numeric equivalence evidence.

## D-0602 — No same-base superseding proposal

- Context: two proposals from one learner/session/base can claim overlapping local work.
- Candidates: newest wins; explicit supersession; reject every second interval on the same base.
- Choice: one canonical proposal per learner/session/fragment/base; publication retry reuses its request identity, while new local work waits for a committed successor.
- Rejected: newest-wins and supersession can silently double-count or discard token intervals.
- Compatibility: tightens D-0203 and the M00 same-base flood gate.
- Reversibility: relaxing this requires an explicit non-overlap lineage proof and protocol change.

## D-0603 — Committed round-robin fragment schedule

- Context: fragment choice must replay identically after restart and across learners.
- Candidates: learner-local cursor; acceptable set; committed scheduler cursor.
- Choice: use the committed frontier scheduler cursor/round-robin policy kernel; learner-local observation never becomes authority.
- Rejected: a local cursor can diverge after crash; an acceptable set leaves selection under-specified.
- Compatibility: preserves the P04/P05 scheduler projection.
- Reversibility: a new schedule must be committed and replay-digest equivalent.

## D-0604 — Reset-all is the default inner optimizer adoption policy

- Context: adopted weights can invalidate momentum/state tied to the pre-adoption model.
- Candidates: preserve; reset updated fragment only; reset all.
- Choice: default to `reset_all`; expose and label `reset_updated_fragment` and `preserve` for controlled ablations, with all three in tests and manifests.
- Rejected: preserve is the least conservative recovery default; fragment-only reset depends on exact parameter/fragment mapping.
- Compatibility: matches the existing effective default behavior.
- Reversibility: changing the default requires numeric/recovery evidence and Checker review.

## D-0605 — Target tokens are actual non-padding training tokens

- Context: proposal weight must represent performed work rather than configured capacity.
- Candidates: examples; nominal batch capacity; actual `Batch.num_tokens` summed across the interval.
- Choice: sum actual `Batch.num_tokens` for successful inner steps and bind the total to the immutable interval/publication identity.
- Rejected: examples ignore sequence length; nominal capacity overclaims partial intervals.
- Compatibility: preserves existing learner counters while making the definition explicit.
- Reversibility: another accounting unit requires a new weighting identity.

## D-0606 — Immutable session start plus per-session monotonic sequence

- Context: process-local counters disappear on restart and no database counter is allowed.
- Candidates: mutable local counter; learner-wide global counter; immutable unique session plus monotonic sequence recovered from immutable markers.
- Choice: publish an immutable UUID session-start record and derive the next sequence by listing and validating that session's immutable publication markers. A restart may safely open a new session at sequence one; it never reuses an existing identity.
- Rejected: local counters can rewind; a learner-wide allocator would add mutable authority.
- Compatibility: existing proposal identity already includes learner session and sequence.
- Reversibility: a future head-reachable session index may accelerate recovery without changing identity.

## D-0607 — Publication request identity and ancestry reconciliation

- Context: payload/marker response loss must not create a second logical proposal.
- Candidates: payload equality; random retry IDs; deterministic session/sequence/fragment request ID with immutable evidence.
- Choice: bind request ID and digest to learner/session/sequence/fragment/base, publish payload then immutable request then immutable marker, and classify retry only by the same request ID/digest. Commit outcome is determined from verified ancestry, never listing alone.
- Rejected: payload equality repeats the P03 CAS bug; random retry IDs duplicate logical publication.
- Compatibility: extends D-0506/D-0507 without granting learners head-CAS.
- Reversibility: key layout may change if canonical identity and marker-last ordering remain.

## D-0608 — One pure interval/adoption policy kernel

- Context: runtime, recovery, tests, and replay must agree under adversarial ordering and restart.
- Candidates: duplicate runtime/reference logic; source-code assertions; one dependency-free immutable kernel.
- Choice: `fs_diloco.learner_protocol` owns interval, wait, recovery, and adoption transitions; runtime calls the same kernel used by model/replay tests.
- Rejected: duplicated policies previously caused selection drift.
- Compatibility: the public learner entrypoint remains `fs_diloco.learner`.
- Reversibility: module boundaries may change while one executable semantic path remains.

## D-0609 — Freeze bfloat16 transport and float32 committed identity

- Context: P06 adds metadata but must not regress the M00 production codec.
- Candidates: inherit configuration implicitly; record the verified pair; change transport.
- Choice: interval/publication records freeze `bfloat16-proposal/float32-aggregate-commit-v1` (or the configured proposal dtype with the same float32 committed contract) and include its implementation digest in evidence.
- Rejected: implicit dtype permits silent drift; changing transport lacks P06 numeric evidence.
- Compatibility: identical to the verified M00/P05 terminal path.
- Reversibility: new dtype pairs require a new implementation identity and 1/2/9-node evidence.

## D-0610 — Successor/stop/no-progress wait state machine

- Context: a single empty listing or timeout previously allowed overlapping work from one base.
- Candidates: continue immediately; wait forever; wait for committed successor or authoritative stop and terminate this process on declared no-progress.
- Choice: after marker publication the learner starts no new interval until a newer committed frontier is adopted, authoritative stop is observed, or the configured no-progress deadline produces a terminal `no_progress` outcome. Epoch/owner changes are adopted only through the committed frontier at this boundary.
- Rejected: immediate continuation floods one base; unbounded wait cannot surface liveness failure.
- Compatibility: preserves current liveness timeout while changing timeout from retry-work to terminal outcome.
- Reversibility: retry/backoff may change but may not permit overlapping same-base intervals.

## D-0611 — Canonical omission across session boundaries

- Context: optional predecessor identity participates in proposal identity.
- Candidates: absent and `null` equivalent; always write `null`; omit when absent and reject explicit `null`/unknown/conflicting fields.
- Choice: omit an absent predecessor, include only a validated non-empty ID, and fail closed on explicit `null`, unknown identity fields, or a predecessor crossing an invalid session boundary.
- Rejected: `null` creates an alternate canonical spelling; loose cross-session links obscure recovery.
- Compatibility: preserves Protocol-v2 canonical omission.
- Reversibility: none within the current protocol generation.

## D-06A01 — One-way syncer kernel dependency boundary

- Context: P06A must expose reusable data-plane computation without creating a second selector, optimizer, or transaction state machine.
- Candidates: copy the central syncer into a new executor; wrap the whole syncer; move validated metadata planning, ordered reduction, the existing outer step, and transition-attempt construction behind pure typed functions.
- Choice: `syncer_core` receives only validated immutable inputs. `ProposalCatalog.select` delegates to its one oldest-first selection kernel, aggregation calls the existing `outer_optim.outer_optimizer_step`, and authority remains exclusively in `ProductionTransactionalLog.prepare_transition/commit_prepared`. Orchestration depends on kernels; kernels never depend on orchestration, storage listing, leases, clocks, or process identity.
- Rejected: code copying creates semantic drift; a whole-syncer wrapper does not establish a prepare-only boundary.
- Compatibility: the CRS keeps its public CLI and exact request/aggregate identities.
- Reversibility: module names may change, but the one-way dependency and single executable semantic path may not be weakened.

## D-06A02 — Byte, paired-state semantic, and numeric evidence are distinct

- Context: one generic semantic hash can conceal whether equality concerns exact object bytes, the parameter/outer-state pair, or a tolerance comparison.
- Candidates: one digest; tensor digest only; three explicit evidence types.
- Choice: SHA-256 identifies exact encoded bytes; a paired-state semantic digest binds parameter bytes, outer-state bytes, and optimizer implementation; a numeric comparison report separately records both content digests, backend identities, tolerances, maximum errors, and verdict.
- Rejected: one digest cannot honestly represent cross-backend numeric equivalence.
- Compatibility: production object refs remain byte-addressed and existing transition identities are unchanged.
- Reversibility: evidence schemas may be extended through new versions, not reinterpreted.

## D-06A03 — Same-backend exactness and cross-backend tolerance

- Context: the archive CRS is GPU-oriented while the planned LFE defaults to CPU.
- Candidates: require universal bitwise equality; allow unspecified approximate equality; scope equality by execution backend identity.
- Choice: the same FWO executed with the same device/backend, Torch/BLAS identity, dtype, thread count, and reduction order must have exact content identity. CPU/GPU comparisons retain both content digests and use pre-registered `atol`/`rtol`; they never claim content identity.
- Rejected: cross-device universal bitwise equality is not credible; unspecified approximation is unauditable.
- Compatibility: P06A CRS differential evidence uses a matched backend and exact bytes.
- Reversibility: another backend requires a new implementation identity and comparison evidence.

## D-06A04 — Grace and cutoff facts stop at orchestration

- Context: grace windows use a monotonic clock, but planning must be replayable without time.
- Candidates: let the kernel read time; commit wall-clock timestamps; have orchestration produce the validated candidate snapshot and explicit parent/planning facts.
- Choice: the CRS orchestration alone waits/scans until its cutoff, then passes validated candidate metadata, parent/frontier facts, current fragment version, quorum bound, and weighting identity to the pure planner. Directory order and the clock never enter kernel semantics.
- Rejected: kernel clock reads are unreplayable; identity-bearing observational timestamps add nondeterminism.
- Compatibility: the existing grace behavior and canonical post-cutoff selection remain unchanged.
- Reversibility: future committed cutoff policies may add explicit replayable fields.

## D-06A05 — Pure transition attempt, existing authoritative adapter

- Context: future LFEs need to construct results without receiving commit authority.
- Candidates: pass a production log into the kernel; implement another commit adapter; return immutable bytes and identity fields to the existing log.
- Choice: `build_transition_attempt` returns the exact selected IDs, encoded parameter/state bytes, aggregate digest, implementation digest, and stable request ID. Only the CRS authoritative orchestration passes those fields to the existing production log and calls commit.
- Rejected: giving a kernel/log wrapper head access collapses the capability boundary; a second adapter duplicates recovery semantics.
- Compatibility: request identity and the one head-CAS linearization point are byte-for-byte preserved.
- Reversibility: distributed final-transition schemas may wrap this input in a new generation, but cannot bypass the production log authority.

## D-06A06 — Strict inactive FWO/PFT v1 schemas

- Context: P06B needs protocol identities frozen before they become active, without changing the P06 generation.
- Candidates: loose dictionaries; add fields directly to P06; strict inactive versioned objects.
- Choice: FWO v1 strictly binds parent, fragment, committed fencing/membership/ownership facts, canonical selected proposals and hex weights, and policy/backend/layout identities. Prepared output separates a canonical result from executor/session/attempt evidence. Unknown fields, explicit nulls, noncanonical weights, and same-ID conflicting content fail closed.
- Rejected: loose or in-place schemas permit identity drift and invalidate the archived generation.
- Compatibility: these objects are offline/inactive throughout P06A and cannot be adopted or committed by P06 readers.
- Reversibility: activation or field changes require the P06B distributed run generation or a later schema version.

## D-06A07 — CRS retention and deprecation gate

- Context: decomposition must not prematurely remove the verified reference and fallback path.
- Candidates: delete CRS in P06A; retain indefinitely as an implicit writer; retain as the sole P06A committer and later read-only oracle/fallback.
- Choice: the dedicated CRS remains the only P06A production committer. P06B removes its write capability from distributed generations but retains offline/shadow reference and explicit fallback. Deletion is ineligible before P06C and subsequent acceptance evidence establishes a replacement lifecycle.
- Rejected: early deletion loses the oracle; implicit concurrent CRS writes create a second authority.
- Compatibility: C1/C2/C9 topology and public CLI remain available.
- Reversibility: later removal needs its own acceptance and rollback plan.

## D-06A08 — Capability audit scope

- Context: same-account Miyabi processes cannot be treated as a Byzantine OS sandbox, but accidental authority wiring must fail visibly.
- Candidates: source grep only; runtime object inspection only; combined import/call audit and restricted-facade test.
- Choice: static AST audit forbids pure/executor modules from storage, coordination, clock, listing, and head-CAS dependencies. Runtime tests construct a facade exposing only prefix-scoped immutable get/put and prove head/control paths plus mutation/listing methods are absent or denied.
- Rejected: either static or runtime evidence alone misses dynamic construction or unused imports.
- Compatibility: the claim is explicitly software least authority under the crash/omission model, not malicious same-user isolation.
- Reversibility: stronger process/credential isolation may be added without weakening this baseline.

## D-06B01 — Separate learner-hosted executor process

- Choice: each learner host runs one separate LFE process with bounded CPU/thread/RSS/I/O budgets. Executor crash and restart are independent of the learner GPU process.
- Compatibility: the public learner remains unchanged; launch integration owns the sidecar lifecycle.

## D-06B02 — One existing lease and one global head

- Choice: Floating Committers reuse the P05 conditional lease, committed fencing epoch, and single global head CAS. Executors receive neither lease nor head mutation capability.
- Rejected: a second coordination head would become a forbidden second authority.

## D-06B03 — Atomic revision-zero bootstrap in a fresh generation

- Choice: the distributed RunSpec canonically freezes revision-zero members, sessions, capability and numeric backend digests, and factor-one ownership. Only those candidates may acquire the first lease.
- Compatibility: P06 authority stays read-only; this is a fresh matched generation, never exact continuation.

## D-06B04 — Session-bound membership eligibility

- Choice: member identity binds learner/executor IDs and sessions, node identity, and capability digest. Heartbeats are evidence only and never mutate eligibility.

## D-06B05 — Canonical rendezvous ownership v1

- Choice: owner ranking is SHA-256 over canonical membership revision, fragment ID, and member identity, with member identity as the tie-break. P06B freezes factor one.

## D-06B06 — Authoritative FWO request identity

- Choice: at most one active FWO binds parent, selection, hex weights, membership/ownership, fencing, numeric implementation, layout, and parameter-index identities. Response loss reconciles by immutable ID.

## D-06B07 — Marker-last PFT discovery and stale classification

- Choice: publish parameter/state objects, canonical prepared result, attempt envelope, then immutable marker. The committer validates every ref and rejects stale parent, membership, ownership, work-order, or implementation facts.

## D-06B08 — Conservative co-location budget

- Choice: D8 defaults to eight LFE CPU threads, one in-flight work order, and one payload pair in memory. Topology evidence records affinity, RSS, thread, and I/O counters.

## D-06B09 — CRS is a read-only oracle

- Choice: CRS remains for offline replay and matched comparison but receives no distributed-generation write capability.

## D-06B10 — One active work order

- Choice: P06B permits one active authoritative FWO at a time, bounding recovery and head-advance ambiguity.

## D-06B11 — Frozen CPU numeric backend identity

- Choice: FWO freezes device, dtype, Torch/BLAS/thread settings, and ordered reduction. Same-backend duplicates require exact core digests; C9 GPU comparison retains both digests and uses declared tolerance.
- Frozen comparison gate: the matched C9/D8 final tensor smoke uses `atol=0.05` and `rtol=0.10`, reports max-absolute and relative-L2 differences, and never relabels numeric equivalence as content identity.

## D-06B12 — Semantic result excludes attempt evidence

- Choice: canonical result and final transition identities exclude executor, attempt, timing, telemetry, and arrival order. Those facts live only in attempt envelopes.

## D-06C01 — Factor two is a fresh-generation committed invariant

- Choice: P06C starts a fresh distributed generation whose RunSpec freezes replication factor 2. Rendezvous top-2 order is canonical: index 0 is primary and index 1 backup. Factor change is not a local runtime knob and requires another generation.
- Rejected: silently degrading to factor one or changing factor from heartbeat evidence would make ownership unreplayable.

## D-06C02 — Warm standby has no private optimizer state

- Choice: warm backup is a ready LFE with the same immutable FWO/input capability. It starts prepare only after an explicit derived backup-activation signal caused by primary liveness timeout; it rereads committed parent/input objects and never receives primary-local state.
- Rejected: copying primary memory/checkpoints violates storage-only recovery.

## D-06C03 — Replayable execution mode lives in FWO v2

- Choice: FWO v2 binds ordered owner IDs and one mode: `warm_standby`, `active_active`, or `hedged`. Only `hedged` carries a positive canonical integer `hedge_delay_ms`; the other modes canonically omit it. Derived dispatch timing may trigger work but cannot alter FWO identity.
- Rejected: process-local mode/delay would make retries and comparisons ambiguous.

## D-06C04 — Same-backend duplicate equivalence is exact

- Choice: same-FWO attempts freeze backend/thread/reduction identity and must produce the same `prepared_result_id`, parameter/state refs, aggregate digest and semantic digest. Any difference is a fatal divergent-result classification with preserved evidence.
- Rejected: tolerance or majority voting can conceal nondeterminism and change the committed trajectory.

## D-06C05 — Winner is semantic result, not fastest attempt

- Choice: the committer validates every discovered attempt in the decision window. Equivalent attempts collapse to one canonical result; attempt envelopes are sorted only for audit attribution. Final transition binds `work_order_id` and `prepared_result_id`, never first-finish/executor identity.
- Rejected: committing an unvalidated first marker lets listing/arrival order enter authority.

## D-06C06 — Failure evidence proposes, head commit disposes

- Choice: heartbeat/timeout/fault tape produces an evidence digest and a derived reconfiguration request. Only the fenced committer may commit the next strict MembershipControlTransition. False suspicion may increase work or commit a conservative member removal, but cannot directly change ownership.
- Rejected: heartbeat-driven local remap is a second authority.

## D-06C07 — Old-epoch PFT is never reused in P06C

- Choice: any parent, fencing epoch, membership revision or ownership digest mismatch rejects the PFT. P06C recomputes from committed storage after reconfiguration rather than rebasing old output.
- Rejected: rebase would require a new numeric/selection proof and can apply output to a different parent.

## D-06C08 — Explicit factor-two liveness boundary

- Choice: factor two requires at least two eligible members. Loss of one owner is recoverable; loss of all owners permits safe no-progress until committed membership supplies an eligible pair. Simultaneous committer failure is recoverable only when another committed candidate and storage remain available.
- Rejected: silent factor-one fallback overstates liveness and changes the RunSpec invariant.

## D-06C09 — Retain winner and loser objects through P07

- Choice: P06C performs no destructive PFT cleanup. Winner/loser attempts, markers, failure evidence and epoch objects remain auditable; P07 freezes reachability, grace and deletion rules.
- Rejected: eager loser deletion repeats the P06A marker-last cleanup race.

## D-06C10 — D8-R2 defaults to fixed six-second hedge

- Choice: the terminal D8-R2 mode is `hedged` with `hedge_delay_ms=6000`, compared with the frozen P06B factor-one D8. D1/D2 also cover warm-standby and active-active modes. The six-second value is an observed-baseline experiment setting, not a universal optimum.
- Rejected: adaptive delay before P10 would add an uncommitted controller decision and confound P06C correctness.

## D-0701 — Snapshot is an immutable side object with an ancestry pin

- Choice: a lifecycle snapshot is derived immutable state covering one exact committed head. It becomes eligible for accelerated replay only when the current fenced committer commits a `snapshot_pin` control transition that binds its complete ObjectRef, content-derived snapshot ID, covered commit identity, and covered state digest. The pin advances the one global head but does not change optimizer, scheduler, membership, or proposal-consumption state.
- Safety: strict full replay never depends on snapshot availability or validity. A missing, corrupt, stale, or mismatched snapshot is ignored by strict replay and causes snapshot mode to fall back to empty-cache strict replay. An unpinned snapshot is an orphan, not a replay root.
- Rejected: an independently mutable `latest-snapshot` pointer would be a second head; trusting an uncommitted snapshot would permit derived state to replace ancestry authority; embedding snapshot bytes in every frontier would bloat the authoritative control path.

## D-0708 — Snapshot replay state is process-local and invalidated at ownership boundaries

- Choice: a pinned snapshot may seed only a process-local replay attempt after its pin, covered head, state digest, and suffix have been strictly validated. Failed snapshot validation does not populate memoization. Fresh open, takeover, explicit verification, CAS ambiguity, head jump, epoch change, or corruption suspicion discards all prior replay acceleration and starts with empty-cache strict replay or a newly validated pinned snapshot.
- Rejected: serializing verified-object caches or carrying them across committer ownership would violate the M00 recovery contract.

## D-0702 — Acknowledgements are typed immutable evidence, not liveness authority

- Choice: acknowledgements distinguish `observed`, `durably_adopted`, `capsuled`, and `no_longer_needs` and bind role, subject/session, committed watermark, optional fragment, and canonical ObjectRefs. `capsuled` and all non-release acknowledgements retain their referenced objects; `no_longer_needs` is audit evidence that may permit reclamation only after reachability and grace checks.
- Rejected: a heartbeat-derived watermark could release objects after false suspicion; one undifferentiated ack cannot distinguish observation from durable adoption or exact recovery state.

## D-0703 — Inactivity never removes roots by itself

- Choice: learner/executor inactivity may stop extending an observational grace period but cannot remove a committed, pinned, capsuled, response-loss, divergent-blocker, or experiment root. Release requires an explicit immutable `no_longer_needs` acknowledgement plus the mark/apply proof.
- Rejected: automatically dropping roots when heartbeats expire would let transient partitions delete live recovery state.

## D-0704 — Prepared evidence has three retention classes

- Choice: the committed prepared result and its output refs remain reachable; equivalent same-result attempt envelopes/markers receive a bounded loser grace; abandoned old-epoch attempts receive a longer audit grace; any same-FWO divergent result set is a blocker root and is never automatically collected. The reachability report records the exact class for every retained object.
- Rejected: treating all uncommitted PFTs as immediate orphans repeats the marker-last race; treating every loser forever-live prevents bounded growth.

## D-0705 — Active work, response loss, and pins are explicit immutable roots

- Choice: active FWO, capsule, restore-point, experiment, response-loss, and quarantine roots are immutable typed pins. Committed final transitions additionally root their exact FWO/PFR identities. Listing and heartbeat observations may discover these records but cannot create or remove authority.
- Rejected: process-local active-work sets or directory presence are not recoverable root definitions.

## D-0707 — GC is immutable mark plus guarded revalidated apply

- Choice: mark records the exact head manifest/backend version, fencing epoch, membership revision, candidate ObjectRefs, and reachability/protected-unknown digests. Creating a mark is always dry-run. Apply is unavailable for real run namespaces without the separate human gate; the active API permits only `synthetic-*` runs with a mark-and-namespace-bound approval token. Apply strict-replays and rebuilds reachability, rejects any head/epoch/object change, writes an immutable delete request, deletes payload/result/attempt objects before publication markers, and writes an immutable result.
- Response loss: retries use the same request ID and ObjectRefs; already-missing targets reconcile as an after-effect while changed identities fail closed. Partial batches resume idempotently and never broaden the original target set.
- Rejected: list-and-delete in one pass, mutable GC cursors, or deleting a candidate after head advance cannot prove zero live deletion.

## D-0706 — Exact capsule consistency is explicit and complete

- Choice: an exact capsule marker is published last after immutable model, inner optimizer, scheduler, scaler, CPU/CUDA/Python RNG, restorable data-source, interval, and frontier components. Synthetic data stores the real `torch.Generator` state and batch index; WikiText stores a content-derived dataset/shard/tokenization identity and batch index. Restore requires every component, the exact covered frontier, matching backend/device RNG topology, and a new learner session with the next sequence.
- Interval rule: boundary capsules carry no open or pending interval. Mid-interval capsules bind the complete interval state and report any old-session pending proposals as discarded/reconciled evidence; they are never silently reused under the new session.
- Claim boundary: missing private, RNG, iterator, scheduler, or scaler state fails the exact path. The caller may separately choose warm recovery, but the report must not relabel it exact.
- Rejected: seed-plus-draw counters, model-only checkpoints, or a nominal WikiText batch number without dataset/tokenizer identity cannot prove exact continuation.

## D-0709 — Reachability extensions are typed ObjectRef edges

- Choice: P08 bundle transitions extend lifecycle reachability by contributing canonical ObjectRefs and edge reasons from their committed transition schema. They may add roots only through the existing typed pin/ack contracts; bundle-local caches, directory conventions, or listing results cannot release an object. Unknown future bundle objects remain quarantined by default.
- Compatibility: P07 freezes `ReachabilityReport`, root/edge reason reporting, two-snapshot retention, and marker-last deletion ordering as the integration surface. P08 must not change the single head, snapshot identity, GC mark, acknowledgement, capsule, FWO, or PFT identities.
- Rejected: hard-coding P08 filenames into generic GC would couple deletion safety to one bundle layout and make schema evolution fail open.

## D-0710 — Two-base active window and accelerated-soak bound

- Choice: active compaction retains the newest two independently ancestry-validated snapshots, the committed suffix above the older base, the newest two exact capsules per learner, and two active audit records per lifecycle record class. Objects covered by the older retained snapshot receive immutable snapshot-age grace; unpublished/abandoned PFTs still require explicit grace, response-loss pins, or acknowledgements, and divergent results remain blocker roots.
- Cadence: terminal D8-R2 uses a snapshot/GC dry-run every two optimizer transitions and one exact capsule per learner at sequence one (cadence one with an explicit maximum sequence of one), ensuring the member later selected for whole-host loss has durable recovery evidence without producing repeated GPT-2 optimizer capsules. The destructive companion remains synthetic-only. The preregistered effective-live-object tail bound is a maximum delta of 64 objects across the final three lifecycle samples; raw inventory, bytes, candidates, replay reads, lifecycle seconds, and capsule counts are persisted.
- Claim boundary: snapshot manifests retain the compacted logical audit prefix and may grow with history; the bounded claim is for active non-snapshot tensor/metadata objects and the explainable effective-live window after eligible apply. Real D8 remains dry-run and must expose reclaimable candidates rather than deleting them.
- Rejected: retaining one snapshot cannot survive corruption after prefix deletion; retaining every capsule/ack/audit object defeats bounded growth; applying GC automatically to a real training namespace violates the human approval gate.

## D-0800 — Fenced recovery from an authoritative error stop

- Context: H0 correctly commits an `error` stop before a crashing committer exits, but D-0504 makes every committed stop terminal. P08 interference and failover experiments require a truthful crash fact and an explicit restart path rather than silently omitting the error.
- Choice: P08 introduces `distributed-head-fenced-error-resume-v2` and a `resume` control transition. Only a new fenced owner after empty-cache strict replay may resume; the parent must project a stop whose reason is exactly `error`, and the transition binds that stopped commit ID plus the new owner token/request identity. Resume advances only commit sequence, clears the stop projection, and changes no optimizer count, tensor, scheduler, membership, consumption, or fragment version. Normal completion/operator stops remain irreversible.
- Compatibility: v1 runs remain readable and cannot emit `resume`. A P08 run that may resume is a fresh generation whose RunSpec freezes the v2 coordination protocol. Old readers reject the new protocol/control kind instead of misreading it.
- Rejected: not committing crash errors regresses H0 truthful-stop evidence; deleting or overwriting the stop creates a second terminal authority; resuming arbitrary stop reasons can violate experiment termination.

## D-0801 — Process-local canonical fragment layout plan

- Choice: direct access derives one immutable gather/scatter plan from the existing parameter and fragment indexes. Its identity is the existing parameter-index digest plus fragment-layout digest and canonical ordered tensor slices. The process-local cache is keyed by those digests, contains no tensor authority, is deletable, and is invalidated on layout identity change.
- Rejected: a parallel layout format or durable plan cache would create another validation truth.

## D-0802 — Ordered float32 streaming reduction

- Choice: proposal transport remains the RunSpec dtype (qualified baseline bfloat16); each selected payload is converted and accumulated in float32, one proposal at a time, in canonical selected-proposal order using the already committed hexadecimal weights. Params and outer state remain float32 production objects. Same implementation/backend/thread identity must be exact.
- Rejected: tree/arrival-order reduction, lower-precision accumulation, or resource-dependent order would change numeric identity.

## D-0803 — Audited LFE resource budget

- Choice: each LFE remains one process with one in-flight FWO, an explicit thread limit, RSS ceiling, maximum prefetch bytes of one input fragment, and CPU affinity taken from its actual schedulable set. The default remains eight threads and 16 GiB until matched P08 interference evidence selects a different value. Actual affinity, NUMA mask, peak RSS, thread count, input/output bytes, and budget violations are recorded; a violation rejects the attempt and triggers backpressure rather than memory overcommit.
- Rejected: unbounded prefetch/in-flight work or declared-only placement cannot support interference claims.

## D-0804 — Owner/head-scoped validation tokens

- Choice: a validation token binds the complete ObjectRef, proposal identity, RunSpec/layout/optimizer digests, head commit ID, fencing epoch, membership revision, owner session, validation level, and a storage observation fingerprint. It contains no payload bytes and is process-local. Catalog rescans under the same scope may reuse it; selection/LFE loading still reads the selected payload once. Head/epoch/membership/owner change, CAS ambiguity, cache clear, changed observation, or corruption suspicion discards all tokens and forces strict revalidation.
- Rejected: path-only/mtime-only keys, serialized tokens, payload retention across scans, or cross-owner reuse.

## D-0805 — Reconstructible scanner and chunk-verified range reads

- Choice: scanner cursors are process-local hints only; restart performs storage discovery and canonical deduplication. POSIX envelope v2 adds fixed-size payload chunk digests under the checksummed header. `range_get` verifies the header and every intersecting chunk while reading only those chunks; full `get` still verifies the complete payload digest. Legacy v1 envelopes use the existing full-read fallback. Range corruption outside the requested chunks is detected by later full access and never becomes a successful authoritative read.
- Compatibility: envelope version is a backend detail; logical keys, ObjectRefs, payload bytes and head-CAS semantics do not change.
- Rejected: unchecked seek reads violate correctness; rereading the full payload is not true range I/O.

## D-0806 — Causal local-clock telemetry

- Choice: stage events are append-only observational JSONL with schema/version, role/session, run/generation, causal transition/FWO/attempt IDs, head/epoch/membership facts, local monotonic start/end/duration, UTC observation time, outcome and typed counters. No cross-host exact span is fabricated. Recorder failure never changes training; the acceptance reducer fails closed if required events, topology, lineage or drop accounting are incomplete. The measurement overhead budget is 2% of matched one-node wall time.
- Rejected: telemetry in canonical identities, blocking authority on the recorder, or timestamps without causal IDs.

## D-0807 — Pre-registered bundle trigger

- Choice: retain the single-FWO path unless matched D8 factor-one and R2 traces show, in at least 8 of 10 optimizer transitions, that non-overlapped FWO serialization wait is at least 25% of transition critical-path time and a two-FWO simulator projects at least 15% end-to-end improvement after measured extra I/O/RSS. The maximum speculative window would be two FWO and one parent. Failure to cross either threshold closes P08-A16–A18 as Checker-audited `not_applicable`.
- Rejected: adding a protocol schema from synthetic-only timing or average-only evidence.

## D-0808 — Conditional bundle serial semantics

- Choice: only if D-0807 triggers, a new generation/schema canonically orders disjoint fragment FWO by fragment ID then work-order ID, binds one parent and the union of non-overlapping proposal consumption, and proves its final state digest equals sequential application in that exact order. It still has one final head CAS.
- Rejected: same-fragment overlap, multiple heads, implicit arrival order, or transparent identity changes in the current generation.

## D-0809 — Conditional bundle cancellation and lifecycle roots

- Choice: a triggered bundle path treats every partial FWO/PFR as immutable prepared evidence, cancels the window on head/epoch/membership change, never rebases, and contributes typed ObjectRef edges through D-0709. Response loss reconciles the one bundle request through committed ancestry. If D-0807 does not trigger, no bundle object/schema is written and these obligations are `not_applicable`.

## D-0810 — Matched performance attribution

- Choice: every P08 performance claim binds clean commit/config/dataset/model/seed, learner and allocation topology, replication/mode/fault tape, LFE affinity/NUMA/thread/RSS/in-flight budget, storage mount/stripe, module/Python/Torch environment and raw stage events. C9/no-LFE, D8 factor one and D8-R2 comparisons must state every unmatched dimension and cannot combine historical timings as matched data.
- Rejected: topology-declared-only, synthetic-only, or cross-commit comparisons as causal performance evidence.

## D-0811 — Derived sidecar durability and materialization cadence

- Choice: control-plane JSON/safetensors sidecars remain derived from the committed log, but every atomic rename is followed by a parent-directory fsync so a visible learner marker or `latest.json` is not intentionally left directory-volatile. Fragment exports reuse only an existing file whose version/path matches the prior derived view. Full-model materialization honors the positive `fragments.materialize_full_every_events` cadence by optimizer-transition count; single-fragment runs and missing prior materializations regenerate immediately. A skipped full export keeps the prior materialized path and records its producing commit sequence.
- Rejected: treating sidecars as authority, trusting a missing/mismatched derived file, or reconstructing every unchanged fragment on every transition.

## D-0812 — Recoverable error observation is not the terminal worker sidecar

- Choice: in an error-resume-v2 generation, the committed error stop remains authoritative and is exported as `control/recoverable_error.json`; it does not create terminal `control/stop.json`. Learners/LFEs may finish or continue producing immutable work against their last adopted parent while no optimizer authority can advance. A successful fenced resume removes only the recoverable derived error observation. Normal completion/operator stops still publish terminal `stop.json` and remain irreversible.
- Rejected: restarting a learner under the same immutable session/sequence, silently changing committed membership sessions, or letting an observational terminal sidecar force identity reuse during an otherwise recoverable authority outage.

## D-0813 — Observable D8-R2 executor fault

- Choice: the final D8-R2 tape injects one executor exception after the canonical work order and attempt identities are known but before payload I/O. The executor writes a typed failed `executor_input_read` stage, flushes recorder health, exits nonzero, and is restarted under a new process session. The host observer binds the same work-order/attempt IDs into the fault tape and activates the frozen backup. This is a real process failure and recovery path without the unknowable telemetry loss of an asynchronous SIGKILL.
- Rejected: claiming complete loser-attempt telemetry after killing a recorder with queued events, or synthesizing an attempt identity outside the canonical executor path.

## D-0814 — D-0807 measured projection

- Choice: the per-transition wait fraction uses `prepared_visibility` divided by the sum of same-committer causal critical stages, avoiding cross-host clock subtraction. The optimistic two-FWO end-to-end bound overlaps half of the total measured wait while charging zero extra I/O/RSS; observed R2 GPU-step overhead relative to factor one is then subtracted as a measured penalty. Because this is an upper bound, a value below 15% conclusively retains single-FWO; a value above threshold only opens the schema gate.
- Rejected: dividing committer wait by cross-host timestamps, excluding learner/job wall time from the E2E projection, or treating a synthetic projection as measured speedup.

## D-0815 — Centralized-shadow long-stage lease guard

- Choice: centralized successor preparation and post-CAS replay may run on a worker only because they cannot perform the global head CAS: prepare writes immutable unreachable evidence and replay is read-only. The owner thread renews the observational lease during those stages and performs one final successful renewal immediately before `commit_prepared`. Any renewal loss prevents CAS and prevents that process from committing a stop.
- Rejected: increasing the matched workload TTL, allowing a worker thread to CAS, committing an error stop after lease authority is lost, or reusing the terminal failed namespace.

## D-0816 — Guarded centralized terminal stop

- Choice: terminal stop uses the same separation as optimizer work: strict stop preparation is a non-authoritative heartbeat-guarded substage, the owner performs a final successful renewal, the caller thread executes the only head CAS, and post-CAS replay is read-only and heartbeat-guarded. A manifest-level pass without live-lease proof at stop CAS is inconclusive.
- Rejected: using the convenience `commit_stop` when strict preparation can exceed TTL, treating a semantically correct but unfenced terminal as acceptance evidence, or extending TTL only for the shadow.

## D-0817 — Distributed critical-path lease guard

- Choice: executor-result wait, winner validation, immutable successor preparation, and post-CAS replay are non-authoritative substages and may run under the main-thread heartbeat helper. One final live renewal immediately precedes optimizer CAS. Distributed terminal stop follows D-0816, and lease-authority loss suppresses stop publication.
- Rejected: guarding only executor wait, summing separately sub-TTL stages without renewal, or committing an error stop after the next-loop renewal proves expiry.

## D-0818 — Atomic P08 run-namespace claim

- Choice: every matched nine-node wrapper atomically creates a previously absent `STORAGE_ROOT` and `ARTIFACT_ROOT` before runtime setup. Existing roots fail before authority access. A PBS job ID never shares a run ID, authority namespace, artifact manifest, or observational logs with another allocation.
- Rejected: `mkdir -p` on caller-supplied experiment roots, treating a duplicate submission as resume, or allowing two allocations to race initialization and marker publication.

## D-0819 — Phase-specific elapsed envelope without hiding measured runtime

- Choice: keep the historical P06B factor-one report ceiling at 900 seconds by default, but require the P08 D8 wrapper to pass its explicit 1500-second PBS allocation envelope. The P08 report always archives the observed elapsed time and the matched comparison uses that value, so accepting report construction within the allocation does not assert that the runtime is fast or acceptable.
- Rejected: silently changing the P06B threshold, dropping elapsed validation, or replacing the measured 17:41 result with a nominal value.

## D-0820 — P08 factor-two lifecycle window budget

- Choice: preserve the P07 lifecycle reporter's 64-object default. P08 R2 binds an explicit 80-object two-interval tail budget: P08 typed resource/attempt evidence adds eight effective-live objects per lifecycle cadence relative to the P07 curve, hence sixteen across the report's three-point/two-interval tail. The measured R2 tail is 229/265/301 (delta 72), while every adjacent cadence remains a constant 36 objects and reclaimable candidates grow 120/182/244. The extension changes only the observational acceptance budget; reachability, two-snapshot retention, dry-run deletion policy, and authority are unchanged.
- Rejected: silently widening P07, disabling the bounded-window check, treating factor-two attempt/resource objects as leaks, or accepting an unbounded/nonlinear curve.
