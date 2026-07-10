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
