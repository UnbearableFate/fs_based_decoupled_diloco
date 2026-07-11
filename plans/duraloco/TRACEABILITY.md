# DuraLoCo P0 Traceability

| Claim ID | Claim/contract | Invariants | Current evidence owner | Future production owner |
|---|---|---|---|---|
| P0-C001 | Protocol identities and canonical bytes are stable and conflicts fail closed. | I-011 | `tests/protocol/test_canonical_json.py`, `test_identities.py` | P01 protocol package |
| P0-C002 | Only same-run, causally valid, complete finite proposals may be eligible. | I-004, I-012 | M00 41-ID mapping; `tests/test_proposal_catalog.py` | P05 syncer ingest; P06 interval policy |
| P0-C003 | A single head commit point produces a linear committed prefix. | I-002, I-006 | M00 production transaction and single-head-CAS audit | P05 optimizer/control transactional API |
| P0-C004 | Proposal logical inclusion is at most once despite duplicate/response-loss execution. | I-003 | `tests/reference/test_double_inclusion.py`, `test_random_traces.py` | P04 historical evidence; M00 SQLite-free requalification; P05 commit pipeline |
| P0-C005 | Parameter fragment and outer state advance as one transition. | I-005 | `tests/reference/test_reference_transitions.py`, mutant tests | P04 historical frontier/commit; M00 production tensor bridge |
| P0-C006 | Global recovery equals a complete committed prefix and ignores prepared/orphan state. | I-001, I-008 | M00 strict/memoized replay benchmark and final Checker counterexamples | P05 ownership-bound takeover; P07 snapshot+suffix optimization |
| P0-C007 | Identical reference inputs produce stable optimizer/state digests and agree with fragment-count-one legacy math within contract. | I-009 | `tests/reference/test_reference_outer_optim.py` | M00 full/fragment production codec and optimizer adapter |
| P0-C008 | Performance/training claims remain gated by fencing and safe lifecycle proofs. | I-007, I-010 | contract and phase checker | M00 prerequisite; P05 lease; P07 GC |
| P0-C009 | Process-local verified-object memoization is non-authoritative, ownership-bound, and digest-equivalent to strict replay. | I-001, I-006, I-008 | M00 real-prefix benchmark; stale-cache/head-jump Checker counterexample | P05 takeover; P07 snapshot replay; P08 I/O optimization |
| P0-C010 | Learner publication is marker-last and immutable, learner has no head-CAS surface, and same-base work is backpressured. | I-003, I-004 | M00 50×10 terminal and authority audit | P06 intervals; P07 in-flight grace |
| P0-C011 | Large-object validation is typed/vectorized and not redundantly repeated within one transaction attempt. | I-004, I-009 | M00 production replay review and stage telemetry | P08 direct I/O/streaming reducer |
| P0-C012 | Non-transient terminal retries require review, targeted benchmark, and same-commit 1→2-node requalification. | I-010 | M00 failure lineage and D-M0012 | P05–P12 acceptance harnesses |

P00–P04 establish the historical contracts; M00 supplies the current SQLite-free
production, POSIX/Lustre, replay, multi-process, and 9-node acceptance baseline.
These rows do not claim model-quality or comparative performance evidence;
those remain P12 responsibilities.
