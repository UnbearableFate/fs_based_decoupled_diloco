# P07 D8-R2 renewal retry review — job 2366167

The lease-checkpoint repair worked: lifecycle cycles of 46.193, 69.307, 93.257, and 118.557 seconds retained fencing epoch two through substage renewals, and the run safely committed nine of ten optimizer transitions after the required executor/whole-host faults.

The workflow nevertheless terminated when the rank-zero chaos harness reached its fixed 840-second orchestration deadline while the tenth transition's final lifecycle cycle was in strict replay. PBS allowed 35 minutes, but the inherited P06C harness deadline allowed only 14 minutes and did not account for P07's preregistered lifecycle observations. `mpirun` therefore aborted the otherwise healthy workers. The failure manifest and all stage events are preserved at `artifacts/duraloco/P07/20260712_p07_renew_f56b953_d8`.

Repair: make the harness deadline configurable, preserve 840 seconds as the P06C default, and set P07 D8-R2 to 1800 seconds (inside the 2100-second PBS walltime). Prove the exact environment wiring on one compute node, then rerun clean one-node and two-node qualifications before one new nine-node attempt.
