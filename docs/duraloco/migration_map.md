# Prototype to DuraLoCo Migration Map

| Current authority/mechanism | Current source | DuraLoCo destination | Phase |
|---|---|---|---|
| Learner JSON marker plus safetensors payload | `fs_diloco/learner.py`, `tensor_codec.py` | Strict immutable Protocol v2 proposal | P01/P06 |
| Syncer-local update states | `fs_diloco/schema.sql`, `sqlite_store.py` | Committed selection records; SQLite is rebuildable cache | P04/P05 |
| `control/latest.json` | `paths.py`, `syncer.py` | CAS-protected head and immutable frontier | P03/P04 |
| Local `selected -> applied/dropped` transaction | `sqlite_store.py`, `syncer.py` | In-memory tentative selection plus one head CAS | P04/P05 |
| Full-vector and fragment outer optimizers | `outer_optim.py`, `merge.py` | Deterministic oracle plus production transition adapter | P02/P04 |
| Parameter/fragment indexes | `param_index.py`, `fragment_index.py` | Stable digests in run/proposal manifests | P01 |
| Direct filesystem paths/rename/glob | `atomic_io.py`, `paths.py` | Backend-neutral semantic storage API | P03 |
| Single syncer assumption | `syncer.py` and PBS role layout | Lease, fencing epoch, standby replay/takeover | P05 |
| Learner reload/resume | `learner.py`, `test_resume.py` | Frozen contribution intervals, boundary adoption, warm/exact recovery | P06/P07 |
| Count/version retention | `retention.py` | Reachability, pins, acknowledgments, grace, audited GC | P07 |
| Whole-model flatten and quorum materialization | `param_index.py`, `merge.py` | Direct fragment access and streaming reduction | P08 |

Legacy entry points and namespaces stay default until their explicit promotion
gates. Protocol v1 readers may import into an isolated compatibility context,
but never write v1 and v2 authority into the same run generation.
