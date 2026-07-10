# DuraLoCo Invariant Catalog

Invariant IDs are stable. P00 freezes their meaning; later phases supply the
listed executable owners.

| ID | Invariant | Future executable owner |
|---|---|---|
| I-001 | Every object referenced by committed head/frontier exists and passes size and digest verification. | `tests/log/test_replay_prefix.py` (P04) |
| I-002 | Committed heads form one parent-linked chain with strictly increasing commit sequence. | `tests/reference/test_reference_transitions.py` (P02), `tests/log/test_cas_conflict.py` (P04) |
| I-003 | A proposal ID appears in at most one committed selected set. | `tests/reference/test_double_inclusion.py` (P02), `tests/log/test_commit_crash_matrix.py` (P04) |
| I-004 | Every selected proposal has a current-run causal base that is a committed ancestor and within configured staleness. | `tests/protocol/test_validation_matrix.py` (P01) |
| I-005 | Each fragment version and its outer-optimizer state are generated and referenced by the same commit. | `tests/reference/test_reference_transitions.py` (P02), `tests/log/test_commit_happy_path.py` (P04) |
| I-006 | A head CAS is the sole committed-transition linearization point; prepared/orphan objects never affect committed state. | `tests/reference/test_crash_prefixes.py` (P02), `tests/log/test_commit_crash_matrix.py` (P04) |
| I-007 | Fencing epochs never decrease; after an epoch bump an older leader cannot advance head. | `tests/syncer_v2/test_lease_fencing.py` (P05) |
| I-008 | Recovery equals the fold of one complete head-reachable committed prefix and is independent of disposable caches. | `tests/reference/test_crash_prefixes.py` (P02), `tests/log/test_cache_rebuild.py` (P04) |
| I-009 | Equal canonical parent/input/decision/optimizer data produces the same transition identity under the declared numeric mode. | `tests/reference/test_reference_outer_optim.py` (P02) |
| I-010 | Objects reachable from head, snapshots, active cursors/capsules, pins, eligible proposals, or grace roots are never reclaimed. | `tests/lifecycle/test_reachability.py` (P07) |
| I-011 | Protocol identities map to one canonical body and one content digest; conflicts fail closed. | `tests/protocol/test_identities.py` (P01) |
| I-012 | A proposal's payload path/key stays inside its run namespace and matches declared key, size, digest, shape, dtype, and finite-value contract. | `tests/protocol/test_validation_matrix.py` (P01) |

The P0 stop conditions are any unexplained violation of I-003, I-005, I-006,
I-007, I-008, or I-010. Performance or training gates must remain closed while
such a violation is open.
