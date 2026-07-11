---
blocker_id: "BLK-YYYYMMDD-NNN"
phase: "PXX"
status: "OPEN|RESOLVED|WONT_FIX"
severity: "correctness|authority|recovery|performance|environment|research"
created_at: "YYYY-MM-DDTHH:MM:SSZ"
---

# Blocker

## Summary

One precise sentence describing the blocked invariant or acceptance gate.

## Context

- Commit/branch:
- Phase/loop/acceptance ID:
- Topology (C9/D1/D2/D8/D8-R2):
- Run/work-order/FWO/PFT/transition IDs:
- Membership/ownership epoch:
- Environment/job IDs:

## Minimal reproduction

```bash
# exact commands
```

## Expected vs observed

- Expected:
- Observed:
- Raw artifact paths:

## Authority and safety impact

- Can this create a second authority, duplicate logical inclusion, mixed parameter/state, live deletion or unreplayable state?
- Is the run safe to continue, read-only only, or must stop?

## Attempts

| attempt | commit | change | result | artifact |
|---|---|---|---|---|

## Current hypothesis

Separate facts from inference. Record uncertainty.

## Smallest next experiment

One bounded test or benchmark that discriminates hypotheses.

## Decision/approval needed

- Agent/Checker decision:
- Human approval only if required by plan:

## Resolution

- Fix/ADR:
- Regression test:
- Requalified shapes:
- Checker verdict:
