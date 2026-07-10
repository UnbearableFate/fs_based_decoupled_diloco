# Prototype to DuraLoCo Migration Map

| Runtime fact/mechanism | Current source | Authority/status | Next owner |
|---|---|---|---|
| Learner marker plus tensor payload | `learner.py`, `proposal_catalog.py` | Listing is discovery only; selected payload and Protocol v2 manifest are immutable log objects | P06 interval adoption |
| Candidate pending/eligible/selection | `proposal_catalog.py`, `runtime_view.py` | Volatile process state; reconstructed and revalidated after conflicts | P05 fenced syncer |
| Global params and outer state | `log/production.py`, `log/production_codec.py` | Paired ObjectRefs become visible only through the head CAS | P07 snapshots |
| Proposal consumption | commit/frontier prefix | Cumulative committed fact; no second materialization | P07 compaction |
| `control/latest.json` and stop file | `syncer.py` | Derived learner/operator exports | P05 committed stop state |
| Heartbeats, JSONL, CSV, W&B | learner/syncer telemetry | Observational, never protocol authority | P08 telemetry |
| Full-vector and fragment outer optimizers | `outer_optim.py`, `merge.py` | One production transition adapter, checked against P02 numeric semantics | P10 co-design |
| Parameter/fragment indexes | `param_index.py`, `fragment_index.py` | Shared immutable run inputs whose digests are frozen in the run manifest | P07 snapshot roots |
| Filesystem mutation semantics | `storage/` | Verified immutable writes and one conditional head replacement | optional P09 backend |
| Single syncer process | PBS role layout | Safe one-writer M00 baseline; failover is not yet claimed | P05 lease/fencing |
| Learner recovery | `learner.py` | Warm global adoption only | P06/P07 |
| Retention | `retention.py` | Export cleanup only; authoritative object deletion is forbidden | P07 reachability GC |

Historical P00–P04 evidence is preserved as history. Active generations do not
read or convert the removed persistence format. A historical checkpoint may
only seed an explicit new-generation warm start.
