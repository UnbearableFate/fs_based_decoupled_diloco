# P08 D8-R2 post-run review — PBS 2370941

## Classification

- Clean commit: `067d33be79d9dbe63e4a31056e35e96ee525cb1f`.
- Runtime: PASS — ten optimizer transitions, one controlled executor failure,
  guarded normal stop, and complete raw factor-two telemetry.
- Job: FAIL — the post-run P08 reporter rejected the correct factor-two attempt
  cardinality at line 91 of the PBS wrapper.
- Authority: normal terminal; the namespace is immutable evidence and will not
  be reused.

The reporter accidentally applied factor-one cardinality to R2. The run has
ten work orders and two canonical attempts per work order. One injected attempt
failed before it could publish a prepared result, so the correct evidence is
twenty terminal attempts, nineteen successful `fragment_prepared` events, and
one terminal loser. The obsolete assertion required only ten prepared events.
This is an analysis-harness defect, not an optimizer, fencing, or recovery
failure.

## Evidence

- `artifacts/duraloco/P08/20260713_p08_r2_067d33b_r1/manifest.json`
- `artifacts/duraloco/P08/20260713_p08_r2_067d33b_r1/training_summary.json`
- `artifacts/duraloco/P08/20260713_p08_r2_067d33b_r1_storage/training/`
- `duraloco_p08_r2.o2370941`
- `tracejob 2370941.opbs`

The raw evidence contains ten `distributed_transition_committed` events,
nineteen `fragment_prepared` events, twenty reconstructed attempts, exactly
one failed terminal attempt, one controlled-fault record, and a normal
`stop_after_outer_steps` terminal.

## Repair and retry gate

The reporter now validates the frozen R2 relation explicitly: ten timelines,
two attempts per timeline, one terminal loser, and nineteen prepared results.
It archives all four cardinalities in the report. Before any fresh nine-node
R2 submission, the repair must pass (1) a read-only compute recovery against
this preserved run, (2) the clean one-node qualification, and (3) the clean
two-node qualification on one commit. Only then may one fresh R2 namespace be
submitted with the already-passing matched C9 and factor-one reports.
