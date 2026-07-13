# P08R repaired D8-R2 rerun — PBS 2373631

## Verdict

PASS. The snapshot-suffix cache repair is verified end to end on clean commit
`8ebece36bd65c75ffb2b0b057d1f36e42cebcb1a` with exactly eight learner nodes.
The repaired complete experiment took `410.779549171` seconds versus
`527.044491248` seconds historically: `116.264942077` seconds faster, a
`22.060%` reduction. It is `29.220450829` seconds below the original
440-second diagnostic boundary and `189.220450829` seconds below D-4406's
current 600-second R2 envelope.

## Matched elapsed comparison

| Envelope component | Factor one, PBS 2373434 (s) | R2, PBS 2373631 (s) | R2 minus factor one (s) |
|---|---:|---:|---:|
| Setup | 1.110014108 | 1.083778931 | -0.026235177 |
| Runtime | 327.793824885 | 388.524113360 | 60.730288475 |
| Post-runtime | 6.631738400 | 21.171656880 | 14.539918480 |
| Complete | 335.535577393 | 410.779549171 | 75.243971778 |

The repaired matched R2 premium is `22.425%`. The historical matched premium
was `189.491502084` seconds or `56.137%`, so the premium fell by
`114.247530306` seconds or `60.292%`. The historical and repaired factor-one
controls differ by only `-2.017411771` seconds (-0.598%).

## Direct repair evidence

- five lifecycle cycles fell from `89.645466118` to `8.564232228` seconds;
- lifecycle payload reads fell from `47,805,060,618` to `20,581,751` bytes;
- cycle times changed from `0.691/21.445/21.852/22.530/23.127` seconds to
  `0.698/1.110/1.618/2.230/2.907` seconds;
- authority replay stage time fell from `93.915` to `53.967` seconds;
- successor publication stage time fell from `50.824` to `31.050` seconds;
- aggregate publish-to-commit time fell from `361.334` to `241.107` seconds;
- post-CAS replay heartbeat intervals fell from four to zero.

Candidate counts, inventory counts, effective-live growth, and snapshot-get
counts stayed the same. Prepared-result visibility stayed effectively flat
(`126.154` versus `126.453` seconds), and GPU-step mean stayed flat (`26.079`
versus `26.091` ms). Stage totals overlap and are diagnostic, not additive.

## Correctness and qualification

The same clean commit passed the required ladder before the terminal runs:

- targeted historical-prefix proof `2373361.opbs`: 58 tests, first suffix
  replay `5,973,112,800` tensor bytes, warm replay zero tensor bytes and
  `0.260073265` seconds, strict digest equality, source head unchanged;
- full one-node `2373379.opbs`: 526 passed, one skipped, zero active database
  findings;
- D1 `2373399.opbs`: real GPT-2 PASS;
- D2 `2373419.opbs`: fenced error-stop/resume at epoch two and four exact
  factor-two attempt pairs;
- matched factor one `2373434.opbs`: ten transitions, terminal strict equality,
  complete time `335.535577393` seconds;
- repaired R2 `2373631.opbs`: 20 attempts, 19 prepared successes, one controlled
  failed executor, ten transitions, five lifecycle cycles, eight retained exact
  capsules, terminal strict equality, interference/bundle/lifecycle reports
  PASS, and 32 post-runtime lifecycle/replay tests PASS.

Both terminal jobs used config digest
`532dabdeaf3f100ff57eea0f469ab63520197d93f95a6ca797d729c55e2c84d1`,
GPT-2/WikiText-2 raw-v1, seed 1337, 50x10, the default `nvidia/25.9` and
`nv-hpcx/25.9` modules, eight allocated hosts, eight active learner hosts, and
no dedicated or idle control node.

## Evidence

- factor one:
  `artifacts/duraloco/P08R/20260713_p08r_d8_8ebece3_repaired_r1/`;
- repaired R2:
  `artifacts/duraloco/P08R/20260713_p08r_d8r2_8ebece3_repaired_r1/`;
- failed startup review: `P08R_D8_WORKFLOW_FAILURE_REVIEW_2373113.md`.
