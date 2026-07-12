#!/bin/bash
set -eEuo pipefail

: "${PROJECT_ROOT:?}" "${PYTHON_BIN:?}" "${CONFIG:?}" "${RUN_ID:?}"
: "${SHARED_ROOT:?}" "${ARTIFACT_ROOT:?}" "${NODE_IDS:?}"
rank="${OMPI_COMM_WORLD_RANK:?}"
member_id=$(printf 'member-%03d' "$rank")
learner_id=$(printf 'learner_%03d' "$rank")
executor_id=$(printf 'executor-%03d' "$rank")

read -r owner_rank standby_rank < <("$PYTHON_BIN" - "$RUN_ID" "$NODE_IDS" <<'PY'
import sys
from fs_diloco.distributed_syncer.bootstrap import revision_zero_membership
from fs_diloco.distributed_syncer.executor import ExecutorBudget
from fs_diloco.distributed_syncer.ownership import derive_ownership
run_id, raw = sys.argv[1:]
nodes = tuple(raw.split(','))
learners = tuple(f'learner_{index:03d}' for index in range(8))
membership = revision_zero_membership(
    run_id=run_id, learner_ids=learners, node_ids=nodes, budget=ExecutorBudget(threads=8)
)
owner = derive_ownership(membership, fragment_ids=(0,), replication_factor=1).owner_ids(0)[0]
rank = int(owner.split('-')[-1])
print(rank, (rank + 1) % 8)
PY
)

mapfile -t cpus < <("$PYTHON_BIN" -c 'import os; print(*sorted(os.sched_getaffinity(0)), sep="\n")')
(( ${#cpus[@]} > 8 ))
learner_cpus=$(IFS=,; echo "${cpus[*]:0:${#cpus[@]}-8}")
lfe_cpus=$(IFS=,; echo "${cpus[*]:${#cpus[@]}-8:8}")
printf 'learner_cpus=%s\nlfe_cpus=%s\n' "$learner_cpus" "$lfe_cpus" \
  > "$ARTIFACT_ROOT/${member_id}_placement.log"

executor=("$PYTHON_BIN" -m fs_diloco.distributed_syncer.cli executor
  --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT"
  --num-learners 8 --member-id "$member_id" --executor-id "$executor_id"
  --executor-session-id "$RUN_ID-$executor_id-session" --threads 8
  --max-prefetch-bytes 1073741824)
learner=("$PYTHON_BIN" -m fs_diloco.learner --config "$CONFIG" --run-id "$RUN_ID"
  --shared-root "$SHARED_ROOT" --learner-id "$learner_id" --num-learners 8
  --session-id "$RUN_ID-$learner_id-session")
committer=()
if [[ "$rank" -eq "$owner_rank" || "$rank" -eq "$standby_rank" ]]; then
  committer=("$PYTHON_BIN" -m fs_diloco.distributed_syncer.cli committer
    --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT"
    --num-learners 8 --node-ids "$NODE_IDS" --member-id "$member_id"
    --owner-session-id "$RUN_ID-$member_id-committer-session" --threads 8
    --max-prefetch-bytes 1073741824)
  [[ "$rank" -eq "$owner_rank" ]] || committer+=(--standby)
fi

CUDA_VISIBLE_DEVICES="" "${executor[@]}" > "$ARTIFACT_ROOT/${member_id}_executor.log" 2>&1 &
executor_pid=$!
CUDA_VISIBLE_DEVICES=0 taskset -c "$learner_cpus" "${learner[@]}" \
  > "$ARTIFACT_ROOT/${member_id}_learner.log" 2>&1 &
learner_pid=$!
committer_pid=""
if [[ "${#committer[@]}" -gt 0 ]]; then
  CUDA_VISIBLE_DEVICES="" taskset -c "$lfe_cpus" "${committer[@]}" \
    > "$ARTIFACT_ROOT/${member_id}_committer.log" 2>&1 &
  committer_pid=$!
fi

wait "$learner_pid"
wait "$executor_pid"
if [[ -n "$committer_pid" ]]; then wait "$committer_pid"; fi
