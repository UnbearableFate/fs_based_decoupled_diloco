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
