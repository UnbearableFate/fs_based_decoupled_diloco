#!/bin/bash
set -eEuo pipefail
: "${PROJECT_ROOT:?}" "${PYTHON_BIN:?}" "${CONFIG:?}" "${RUN_ID:?}" "${SHARED_ROOT:?}" "${ARTIFACT_ROOT:?}" "${NODE_IDS:?}"
rank="${OMPI_COMM_WORLD_RANK:?}"
member_id=$(printf 'member-%03d' "$rank")
learner_id=$(printf 'learner_%03d' "$rank")
executor_id=$(printf 'executor-%03d' "$rank")
sync_root="$SHARED_ROOT/distributed/p08_resume_control"
mkdir -p "$sync_root"

executor=("$PYTHON_BIN" -m fs_diloco.distributed_syncer.cli executor --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" --num-learners 2 --member-id "$member_id" --executor-id "$executor_id" --executor-session-id "$RUN_ID-$executor_id-session" --threads 4 --max-prefetch-bytes 1073741824)
learner=("$PYTHON_BIN" -m fs_diloco.learner --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" --learner-id "$learner_id" --num-learners 2 --session-id "$RUN_ID-$learner_id-session")
base_committer=("$PYTHON_BIN" -m fs_diloco.distributed_syncer.cli committer --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" --num-learners 2 --node-ids "$NODE_IDS" --member-id "$member_id" --threads 4 --max-prefetch-bytes 1073741824 --replication-factor 2 --execution-mode active_active --error-resume)

run_workers() {
  local phase="$1" executor_pid learner_pid
  CUDA_VISIBLE_DEVICES="" "${executor[@]}" >> "$ARTIFACT_ROOT/${member_id}_executor.log" 2>&1 & executor_pid=$!
  CUDA_VISIBLE_DEVICES=0 "${learner[@]}" >> "$ARTIFACT_ROOT/${member_id}_learner.log" 2>&1 & learner_pid=$!
  wait "$learner_pid"
  wait "$executor_pid"
  touch "$sync_root/${phase}_${member_id}_workers_done"
}

run_workers phase1 &
phase1_workers=$!
if [[ "$rank" -eq 0 ]]; then
  first_committer=("${base_committer[@]}" --owner-session-id "$RUN_ID-phase1-committer-session" --inject-error-after-transitions 1)
  set +e
  CUDA_VISIBLE_DEVICES="" "${first_committer[@]}" >> "$ARTIFACT_ROOT/member-000_committer.log" 2>&1
  first_status=$?
  set -e
  [[ "$first_status" -ne 0 ]]
  "$PYTHON_BIN" - "$SHARED_ROOT/control/stop.json" "$ARTIFACT_ROOT/error_stop.json" <<'PY'
import json,sys
from pathlib import Path
source,target=map(Path,sys.argv[1:])
payload=json.loads(source.read_text())
assert payload['reason']=='error'
target.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY
  touch "$sync_root/error_stop_committed"
fi
wait "$phase1_workers"
while [[ ! -f "$sync_root/phase1_member-000_workers_done" || ! -f "$sync_root/phase1_member-001_workers_done" || ! -f "$sync_root/error_stop_committed" ]]; do sleep 0.2; done

if [[ "$rank" -eq 1 ]]; then
  resume_committer=("${base_committer[@]}" --owner-session-id "$RUN_ID-phase2-committer-session" --standby)
  CUDA_VISIBLE_DEVICES="" "${resume_committer[@]}" >> "$ARTIFACT_ROOT/member-001_committer.log" 2>&1 & resume_committer_pid=$!
  deadline=$((SECONDS + 120))
  while [[ -f "$SHARED_ROOT/control/stop.json" ]]; do [[ "$SECONDS" -lt "$deadline" ]]; sleep 0.2; done
  touch "$sync_root/error_resumed"
fi
while [[ ! -f "$sync_root/error_resumed" ]]; do sleep 0.2; done

run_workers phase2 &
phase2_workers=$!
wait "$phase2_workers"
if [[ "$rank" -eq 1 ]]; then
  wait "$resume_committer_pid"
fi
while [[ ! -f "$sync_root/phase2_member-000_workers_done" || ! -f "$sync_root/phase2_member-001_workers_done" ]]; do sleep 0.2; done
