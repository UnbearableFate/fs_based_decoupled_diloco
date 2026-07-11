# M00 P00–P04 Acceptance Mapping

Verified implementation: `c052438a3cfe5e16c3b154fc842f32dcd61ec6ff`
Status: PASS; independent Checker PBS `2359306.opbs` approved all 41 IDs and
both explicit remaps with `required_gate_followups: none`.

All historical acceptance IDs are requalified by current SQLite-free source and
new M00 evidence. Historical artifacts explain the original contracts but are
not used as current PASS evidence.

## Explicit semantic remaps

| ID | M00 contract | Result |
|---|---|---|
| P00-A06 | Removed embedded-database config/CLI keys fail closed; supported database-free configuration remains compatible. | PASS |
| P04-A06 | After all process-local and compatibility exports are deleted, a fresh process reconstructs the identical full/fragment RuntimeView solely from committed log/head authority. | PASS |

## Current evidence ladder

| Layer | Evidence | Result |
|---|---|---|
| Forbidden surface + full suite + full/fragment recovery | `20260711_m00_c052438_1node_requal`, PBS `2359248.opbs`, 281 passed/1 skipped | PASS |
| Backend races + transaction races + production takeover | `20260711_m00_c052438_2node_requal`, PBS `2359250.opbs` | PASS |
| Preserved real-prefix strict/memoized replay | `20260711_m00_6e85182_replay_benchmark`, PBS `2359243.opbs` | PASS |
| GPT-2/WikiText-2 1+8, 50×10 terminal | `20260711_m00_c052438_gpt2_9n_50x10`, PBS `2359253.opbs`, elapsed 7m24s | PASS |
| Independent final Checker | `20260711_m00_checker_358ecc0_1node`, PBS `2359306.opbs` | PASS |

## Gate-by-gate mapping

| Phase | Acceptance IDs | Current proof |
|---|---|---|
| P00 | P00-A01–A05 | Frozen research/failure/numeric/invariant contracts, drift report, state/evidence validators, clean M00 manifests |
| P00 | P00-A06 | Explicit removed-key fail-closed tests and zero-finding forbidden scan |
| P00 | P00-A07–A08 | Self-checking run manifests, this complete mapping, bilingual phase report, final Checker gate |
| P01 | P01-A01–A08 | Current protocol goldens, strict validation/identity/quarantine/v1-read-only tests in the 281-test compute suite |
| P02 | P02-A01–A08 | Reference independence, crash prefixes, double inclusion, five mutants, Torch oracle, 10,000 traces, oldest-first counterexample |
| P03 | P03-A01–A02 | Shared memory/POSIX conformance and capability tests |
| P03 | P03-A03 | 100 two-node Lustre races, zero double winners and visibility failures |
| P03 | P03-A04–A08 | Listing independence, fault taxonomy/schedules, Lustre mount evidence, capability/compatibility checks, production takeover |
| P04 | P04-A01–A02 | Single head-CAS transition path and complete crash matrix |
| P04 | P04-A03–A04 | Delayed response-loss ancestry and 20 same-parent races with zero double inclusion |
| P04 | P04-A05 | Production params/outer-state ObjectRefs are paired and replay verified |
| P04 | P04-A06 | Explicit log-only fresh-process full/fragment recovery remap |
| P04 | P04-A07 | Memory/POSIX replay plus strict/memoized full/fragment equality and real-prefix benchmark |
| P04 | P04-A08–A09 | Inspect/corruption localization, workflow review, terminal authority probe, final Checker gate |

The machine-readable companion enumerates all 41 IDs and their exact current
evidence paths: `plans/duraloco/M00_P00_P04_ACCEPTANCE_MAPPING.json`.
