# Deterministic Reference Model

P02 provides an executable specification independent of Torch, Hugging Face,
NumPy, filesystem I/O, networking, GPU scheduling, and the production syncer.
It comprises an in-memory semantic storage backend, immutable transition
system, deterministic outer-optimizer oracle, crash simulator, trace grammar,
model checker, replay/minimizer, and deliberate safety mutants.

## Storage semantics

`InMemoryStorageBackend` supplies immutable put/put-if-absent, get/head/range,
single-key conditional replacement, delete, operation history, and deterministic
before/after-effect timeout injection. Same-key/same-bytes writes are
idempotent; conflicting immutable content fails. Conditional replacement has
one winner, and replaying the exact operation after an after-effect timeout is
idempotent. Listing exists for discovery tests but is absent from transition
correctness.

## Transition system

`SystemState` contains one global head, per-fragment parameters/version/outer
state, published proposals, committed consumption/drop sets, and a parent-linked
commit sequence. Its state identity binds the optimizer, rational-weighting,
global/fragment staleness configurations, and every durably published proposal
as well as committed/drop state. Preparing a transition
canonicalizes proposal IDs, validates
eligibility against authoritative state, rejects duplicate learners/IDs,
applies the frozen rational staleness decay `tokens / (1 + 0.2 * staleness)`,
normalizes those positive weights in float64, reduces in canonical order, and
executes the declared outer optimizer. Preparation does not mutate authority.

`commit_prepared` succeeds only against the exact parent head, consumes each
proposal once, and installs parameters plus outer state with the same producing
commit ID. Every committed result checks linear history, consumption equality,
version increments, output pairing, reference completeness, and deterministic
transition identity.

## Numeric oracle

Immutable Python float tuples implement SGD, momentum, Nesterov, and AdamW
using the same weight-decay placement, momentum update, bias correction,
epsilon, and step-counter semantics as `fs_diloco.outer_optim`. Repeated inputs
produce stable hexadecimal state identities. PBS compute tests compare all four
optimizers and the `fragment_count=1` path against the legacy Torch code under
the P00 numeric tolerance.

## Crash and model checking

The simulator injects crashes before and after parameter-object, outer-state,
commit-record, frontier, and head-CAS effects. Every pre-CAS crash recovers the
old prefix and may leave only unreachable prepared objects; response loss after
CAS recovers the new prefix. All stored prefixes can be folded and verified.

Seeded traces cover publication (including before/after-effect crashes),
selection/commit, rejected illegal selections, crash, and restart. Rejected
transitions must leave the durable state unchanged, and replay must produce the
same state digest. The quick gate runs 1,000 traces; the
explicit suite runs 10,000. The minimizer removes irrelevant events from a
failing trace. Deliberate double-apply, wrong-parent, parameter/outer-state
pairing, and canonical-but-numerically-wrong transition mutants must be
detected, demonstrating that the checks fail when the target invariants are
actually broken.
