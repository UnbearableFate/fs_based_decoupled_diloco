---
plan_id: "PN-06"
title: "Artifact Evaluation Package (runs off-Miyabi)"
status: "planned"
depends_on: ["PN-02", "PN-03/04 cell definitions"]
parallel_with: ["PN-05"]
effort: "2–4 weeks; mostly engineering, minimal cluster compute"
---

# PN-06 — Artifact Evaluation Package

## 1. Mission

MLSys artifact evaluation committees run artifacts on commodity machines, not
on Miyabi. Produce an AE package that reproduces the paper's *correctness*
claims exactly and its *performance* claims in miniature on a single multi-core
machine, targeting all three badges (Available / Functional / Reproducible).

The repo is closer to this than most: the memory backend, the tiny synthetic
model (`hf_model.py` smoke path), fault injection, the reference model
checker, and the deterministic analysis pipeline all run without GPUs or PBS.
The gap is packaging and a multi-process single-host topology.

## 2. Package contents

| Component | Basis | AE claim it reproduces |
|---|---|---|
| Container/venv spec (pinned) | `uv.lock` | environment determinism |
| Single-host D8-mini topology: 8 learner processes (tiny model, CPU) + LFEs + 2 committer candidates over a local POSIX root | existing CLIs (`distributed_syncer/cli.py`, learner main) | the full protocol path: proposals → FWO → PFR → CAS → recovery |
| Fault demo scripts: kill committer mid-transition → takeover; kill learner; corrupt a derived file (shows authority unaffected); attempt a stale-owner write (rejected) | `failure_sim.py`, chaos scripts | fencing + recovery claims, live |
| `inspect_cli verify/replay/orphans` walkthrough on the produced log | existing | auditability claim |
| TLA+ spec + TLC configs + mutant counterexamples | PN-02 | model-checking claim |
| Crash-matrix + invariant test suite runner | `tests/` | I-001…I-012 |
| Bounded-growth mini-benchmark (memory backend, 2k transitions, asserts flat costs) | PN-04 L2 | scalability claim, in miniature |
| Figure-pipeline replay on shipped artifact data | PN-05 pipeline + exported run manifests | "figures come from data" |
| Anonymized source snapshot + README + LICENSE | repo | Available badge |

Full-scale Lustre numbers are *not* reproducible off-cluster; the AE README
says so explicitly and marks which claims are miniature-reproduced vs
artifact-verified (checked from shipped immutable run data).

## 3. Loops

1. **D8-mini loop.** A `scripts/local/run_d8_mini.sh` that stands up the full
   topology on one machine in <10 minutes end-to-end, including one injected
   takeover. RED first: script asserts committed transition count, a takeover
   event, and a clean `inspect_cli verify` at the end.
2. **Determinism loop.** Two D8-mini runs with the same seed produce identical
   committed state digests; document where wallclock-dependent divergence is
   expected (selection timing) and why identity still holds per transition
   inputs.
3. **Packaging loop.** Container build, pinned deps, offline-capable (HF
   tiny model weights vendored or synthesized — no network assumption);
   total artifact size within the venue's limit.
4. **Cold-machine rehearsal.** A team member (or a fresh VM) with no project
   context follows README start-to-finish; time it; fix every stumble.
   This rehearsal is the real gate — AE committees are cold machines with
   opinions.
5. **Anonymization loop.** Strip cluster names, usernames, group IDs, PBS
   headers from the shipped snapshot; verify with a grep checklist; keep a
   de-anonymization map privately for camera-ready.

## 4. Acceptance gate

- [ ] D8-mini: full protocol + takeover + verify on a 16-core VM, <10 min,
      no GPU, no network.
- [ ] Same-seed digest equality demonstrated.
- [ ] Cold-machine rehearsal completed by a non-author within 2 hours total.
- [ ] Anonymization checklist clean; license and third-party notices audited
      (human approval gate before anything leaves the cluster).
- [ ] Every paper claim tagged in the AE README as: miniature-reproduced /
      artifact-verified / cluster-only (with justification).

## 5. Risks

- **Hidden platform dependencies** (flock semantics differ on the AE
  machine's filesystem): D8-mini must run the capability probe and *pass* on
  local ext4/xfs/tmpfs — required-capability set documented; the probe output
  itself is a nice AE exhibit.
- **Torch/CPU nondeterminism in the miniature:** pin threads=1 for the
  determinism demo; the numeric contract already scopes determinism to a
  fixed backend identity — reuse that language.
