# P08 D8 factor-one post-run review — PBS 2370782

## Classification

- Clean commit: `6cd515cc193b6a5d7dc3fd0efd8d6b67fa46565c`.
- Runtime: PASS — ten optimizer transitions, guarded normal stop, complete raw
  learner/executor/committer evidence.
- Job: FAIL — the inherited P06B report rejected elapsed time above 900 seconds.
- Authority: normal terminal; no authority repair is needed and the namespace
  remains immutable evidence only.

The lease repair did exactly what it was intended to do. The job ran for
17:41 wall time, within its P08 25-minute allocation, but
`create_p06b_d8_report.py` retained P06B's historical 900-second assertion.
P08 never froze a 900-second acceptance threshold; its matched comparison and
D-0807 gate need the measured elapsed time, not an obsolete phase ceiling.
The 17:41 result remains negative performance evidence until the matched
comparison is complete; widening only the report-construction envelope does
not label it fast or acceptable.

## Evidence

- `artifacts/duraloco/P08/20260713_p08_d8_6cd515c_r2/manifest.json`
- `artifacts/duraloco/P08/20260713_p08_d8_6cd515c_r2/training_summary.json`
- `artifacts/duraloco/P08/20260713_p08_d8_6cd515c_r2_storage/training/`
- `duraloco_p08_d8.o2370782`
- `tracejob 2370782.opbs`

Duplicate PBS `2370787` reused the same caller namespace. D-0818's atomic
`mkdir` rejected it in one second before runtime or authority access; this is
recorded separately as P08-E025 and contributes no performance sample.

## Repair and retry gate

Parameterize the legacy reporter ceiling with a 900-second default so P06B is
unchanged, and pass the P08 job's actual 1500-second allocation envelope. Prove
the base and complete P08 factor-one reports against the preserved terminal
artifact on a compute node, then rerun the clean one-node and D2 qualification
before one fresh D8 attempt.
