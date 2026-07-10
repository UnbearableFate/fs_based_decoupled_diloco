# DuraLoCo P0 Traceability

| Claim ID | Claim/contract | Invariants | Current evidence owner | Future production owner |
|---|---|---|---|---|
| P0-C001 | Protocol identities and canonical bytes are stable and conflicts fail closed. | I-011 | `tests/protocol/test_canonical_json.py`, `test_identities.py` | P01 protocol package |
| P0-C002 | Only same-run, causally valid, complete finite proposals may be eligible. | I-004, I-012 | `tests/protocol/test_validation_matrix.py` | P05 syncer ingest |
| P0-C003 | A single head commit point produces a linear committed prefix. | I-002, I-006 | `tests/reference/test_reference_transitions.py`, `test_crash_prefixes.py` | P04 log commit |
| P0-C004 | Proposal logical inclusion is at most once despite duplicate/response-loss execution. | I-003 | `tests/reference/test_double_inclusion.py`, `test_random_traces.py` | P04/P05 commit pipeline |
| P0-C005 | Parameter fragment and outer state advance as one transition. | I-005 | `tests/reference/test_reference_transitions.py`, mutant tests | P04 frontier/commit |
| P0-C006 | Global recovery equals a complete committed prefix and ignores prepared/orphan state. | I-001, I-008 | `tests/reference/test_crash_prefixes.py` | P04 replay/cache rebuild |
| P0-C007 | Identical reference inputs produce stable optimizer/state digests and agree with fragment-count-one legacy math within contract. | I-009 | `tests/reference/test_reference_outer_optim.py` | P04 optimizer adapter |
| P0-C008 | Performance/training claims remain gated by fencing and safe lifecycle proofs. | I-007, I-010 | contract and phase checker | P05 lease; P07 GC |

P00 establishes the contract and owners. P01 supplies input-boundary evidence;
P02 supplies the executable state-machine oracle. No row claims POSIX/Lustre,
multi-process production runtime, GPU training, or model-quality evidence.
