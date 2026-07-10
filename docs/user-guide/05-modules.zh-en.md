# 模块 / Modules

| Module | 中文职责 | English responsibility |
|---|---|---|
| `learner.py` | 本地训练、payload/marker、checkpoint adoption | Local training, proposal publication, checkpoint adoption |
| `syncer.py` | 唯一 production dispatcher 与 transition loop | Single production dispatcher and transition loop |
| `proposal_catalog.py` | 可重入 discovery、验证、quarantine、oldest-first selection | Re-entrant discovery, validation, quarantine, oldest-first selection |
| `runtime_view.py` | 从 replay 派生的不可变进程视图 | Immutable replay-derived process view |
| `log/production.py` | safetensors transition 与 head CAS | Safetensors transition preparation and head CAS |
| `log/production_codec.py` | params/outer-state codec 与实现 digest | Parameter/outer-state codec and implementation digest |
| `log/replay.py` | committed prefix 校验与恢复 | Committed-prefix verification and recovery |
| `storage/` | memory/POSIX semantic backend | Memory/POSIX semantic backend |
| `analysis.py` | log + JSONL/CSV deterministic fold | Deterministic log plus JSONL/CSV fold |
| `protocol/` | canonical schemas、identity、validation | Canonical schemas, identities, and validation |
| `retention.py` | 只清理 derived exports | Derived-export cleanup only |

`latest.json` 与 telemetry 不向这些模块提供 correctness decisions。
`latest.json` and telemetry never feed correctness decisions back into the protocol.
