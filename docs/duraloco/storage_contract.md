# Semantic Storage Contract

P03 defines the storage primitives used by later DuraLoCo commit code. The API
is backend-neutral and includes immutable create, create-if-absent,
single-object conditional replace, verified get/head/range read, per-object
batch-delete status, and prefix listing. Listing is discovery/GC-only and is
never an input to head reads or conditional commits.

## POSIX layout and atomicity

`PosixStorageBackend` maps canonical relative POSIX keys into one isolated root.
Absolute paths, aliases, dot segments, controls, backslashes, symbolic-link
traversal, and the backend lock namespace are rejected.

Each visible file is one internal envelope containing the opaque version,
previous version, size, SHA-256, and original payload. A mutation uses:

1. a stable per-key advisory `flock`;
2. a same-directory temporary file;
3. flush and `fsync(file)`;
4. atomic link for immutable create or `rename`/replace for CAS;
5. `fsync(parent directory)` when the recorded capability is available.

Payload and version therefore become visible together. Random opaque versions
prevent an A→B→A ABA cycle from revalidating an old CAS token. A retry after a
lost successful CAS response is idempotent only while the current envelope
names the caller's expected version as its direct predecessor and contains the
same new bytes.

The persistent lock inode is not lock ownership. POSIX releases `flock` when a
process exits, so a later process/node can take over without deleting or aging
the lock file.

## Integrity and errors

Correctness mode always parses and verifies the complete envelope for `get`,
`head`, and `range_get`. Short, malformed, or hash-mismatched objects raise
`IntegrityError`. Missing objects, immutable conflicts, stale CAS versions,
invalid keys, lock timeouts, missing capabilities, and OS I/O failures have
distinct typed errors. EIO/ESTALE are marked retryable; permission, quota, and
space/configuration failures are not automatically retried.

## Capability and durability scope

The capability probe executes real operations in a run-isolated prefix and
records immutable conflict detection, verified reads, range behavior, stale-CAS
rejection, discovery, advisory locking, atomic replacement, directory fsync,
filesystem identity, block size, mount information, and Lustre stripe output
when available. Required missing capabilities fail closed.

Directory fsync is evidence for the declared process/OS crash sequence, not a
claim of physical durability under permanent storage loss, controller failure,
or every parallel-filesystem failure mode. P03 preserves the observed
capability report and limits later claims to that evidence.

## Fault and race validation

`FaultInjectingBackend` consumes a canonical seed/replay schedule and injects
before/after-effect timeout, EIO, detected short/corrupt read, and delayed-list
omission faults. Process tests kill publication at each temp-write/fsync/publish
boundary. The two-node Miyabi worker performs at least 100 same-version CAS
races, verifies exactly one winner and cross-node visibility in every round,
and checks takeover after a lock-owning process exits.

Each Lustre probe and MPI rank persists its semantic operation trace alongside
the mount, stripe, hostname, PBS, capability, and winner summaries. These
traces make failure-window and visibility conclusions independently auditable.

The existing learner and syncer continue using their legacy `atomic_io` and
SQLite paths. P03 does not activate the new backend as a runtime default.
