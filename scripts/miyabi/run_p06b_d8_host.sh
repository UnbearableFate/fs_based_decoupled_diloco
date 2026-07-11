#!/bin/bash
set -eEuo pipefail
: "${PROJECT_ROOT:?}" "${PYTHON_BIN:?}" "${CONFIG:?}" "${RUN_ID:?}" "${SHARED_ROOT:?}" "${ARTIFACT_ROOT:?}" "${NODE_IDS:?}"
rank="${OMPI_COMM_WORLD_RANK:?}"
member_id=$(printf 'member-%03d' "$rank")
learner_id=$(printf 'learner_%03d' "$rank")
executor_id=$(printf 'executor-%03d' "$rank")
owner_rank=$("$PYTHON_BIN" - "$RUN_ID" "$NODE_IDS" <<'PY'
import sys
from fs_diloco.distributed_syncer.bootstrap import revision_zero_membership
from fs_diloco.distributed_syncer.executor import ExecutorBudget
from fs_diloco.distributed_syncer.ownership import derive_ownership
run_id,raw=sys.argv[1:]; nodes=tuple(raw.split(',')); learners=tuple(f'learner_{i:03d}' for i in range(8))
m=revision_zero_membership(run_id=run_id,learner_ids=learners,node_ids=nodes,budget=ExecutorBudget(threads=8))
print(int(derive_ownership(m,fragment_ids=(0,),replication_factor=1).owner_ids(0)[0].split('-')[-1]))
PY
)
standby_rank=$(((owner_rank + 1) % 8))
executor=("$PYTHON_BIN" -m fs_diloco.distributed_syncer.cli executor --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" --num-learners 8 --member-id "$member_id" --executor-id "$executor_id" --executor-session-id "$RUN_ID-$executor_id-session" --threads 8)
learner=("$PYTHON_BIN" -m fs_diloco.learner --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" --learner-id "$learner_id" --num-learners 8 --session-id "$RUN_ID-$learner_id-session")
CUDA_VISIBLE_DEVICES="" "${executor[@]}" > "$ARTIFACT_ROOT/${member_id}_executor.log" 2>&1 & executor_pid=$!
CUDA_VISIBLE_DEVICES=0 "${learner[@]}" > "$ARTIFACT_ROOT/${member_id}_learner.log" 2>&1 & learner_pid=$!
committer_pid=""
if [[ "$rank" -eq "$owner_rank" || "$rank" -eq "$standby_rank" ]]; then
  committer=("$PYTHON_BIN" -m fs_diloco.distributed_syncer.cli committer --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" --num-learners 8 --node-ids "$NODE_IDS" --member-id "$member_id" --owner-session-id "$RUN_ID-$member_id-committer-session" --threads 8)
  [[ "$rank" -eq "$owner_rank" ]] || committer+=(--standby)
  CUDA_VISIBLE_DEVICES="" "${committer[@]}" > "$ARTIFACT_ROOT/${member_id}_committer.log" 2>&1 & committer_pid=$!
fi
while [[ ! -f "$SHARED_ROOT/control/stop.json" ]]; do sleep 0.2; done
wait "$learner_pid" 2>/dev/null || true
kill "$executor_pid" 2>/dev/null || true; wait "$executor_pid" 2>/dev/null || true
if [[ -n "$committer_pid" ]]; then wait "$committer_pid" 2>/dev/null || true; fi
