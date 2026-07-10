# DuraLoCo Failure Model

## Covered failures

The initial protocol covers learner and syncer process death, node loss,
standby takeover, duplicate and reordered observations, stale or future
proposals, client timeout before an effect, response loss after a successful
effect, temporary storage unavailability/throttling, short reads, checksum
detectable corruption, network partition, competing syncers, sequence reuse
across learner restarts, and crashes during proposal publication, transition
preparation, head CAS, cache update, replay, compaction, or garbage collection.

The storage contract assumes that an acknowledged immutable object remains
readable until an authorized lifecycle operation removes it. The backend must
provide a linearizable conditional update for one small head object. Process
and request scheduling may be arbitrary; liveness requires eventual storage
availability and a valid proposal quorum.

## Linearization assumptions

- Proposal publication is discoverable only after its immutable payload and
  create-if-absent manifest both exist and validate.
- Prepared transition objects have no authority.
- The conditional replacement of the single global head is the only optimizer
  transition commit point.
- A lease controls liveness and leader selection; head version plus committed
  fencing epoch preserve safety.
- Cache, SQLite, listing results, telemetry, and local `selected` state cannot
  make a transition committed.

## Out of scope

The initial model excludes Byzantine participants, malicious credential use,
silent model/tokenizer/layout replacement within one run generation, loss of
objects acknowledged durable by the provider, unbounded clock skew, permanent
storage partition, and destructive operations outside an isolated run root.
Physical durability beyond the measured POSIX/Lustre or object-store contract
is not inferred from a local filesystem test.

## Recovery boundaries

Syncer recovery and global model recovery must be exact for the committed
prefix. Learner warm restart may lose the current uncommitted interval and all
private optimizer/RNG/data state. Learner exact restart is conditional on a
validated capsule whose contents share one consistency point.
