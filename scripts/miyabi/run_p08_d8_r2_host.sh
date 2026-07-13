#!/bin/bash
set -eEuo pipefail

: "${PROJECT_ROOT:?}" "${PYTHON_BIN:?}" "${CONFIG:?}" "${RUN_ID:?}"
: "${SHARED_ROOT:?}" "${ARTIFACT_ROOT:?}" "${NODE_IDS:?}"
rank="${OMPI_COMM_WORLD_RANK:?}"
member_id=$(printf 'member-%03d' "$rank")
learner_id=$(printf 'learner_%03d' "$rank")
executor_id=$(printf 'executor-%03d' "$rank")
faults="$SHARED_ROOT/distributed/faults"
mkdir -p "$faults"

read -r primary_rank backup_rank < <("$PYTHON_BIN" - "$RUN_ID" "$NODE_IDS" <<'PY'
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
owners = derive_ownership(membership, fragment_ids=(0,), replication_factor=2).owner_ids(0)
print(*(int(value.split('-')[-1]) for value in owners))
PY
)

mapfile -t cpus < <("$PYTHON_BIN" -c 'import os; print(*sorted(os.sched_getaffinity(0)), sep="\n")')
(( ${#cpus[@]} > 8 ))
learner_cpus=$(IFS=,; echo "${cpus[*]:0:${#cpus[@]}-8}")
lfe_cpus=$(IFS=,; echo "${cpus[*]:${#cpus[@]}-8:8}")
printf 'learner_cpus=%s\nlfe_cpus=%s\n' "$learner_cpus" "$lfe_cpus" \
  > "$ARTIFACT_ROOT/${member_id}_placement.log"

executor_base=("$PYTHON_BIN" -m fs_diloco.distributed_syncer.cli executor
  --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT"
  --num-learners 8 --member-id "$member_id" --executor-id "$executor_id"
  --threads 8 --max-prefetch-bytes 1073741824)
learner=("$PYTHON_BIN" -m fs_diloco.learner --config "$CONFIG" --run-id "$RUN_ID"
  --shared-root "$SHARED_ROOT" --learner-id "$learner_id" --num-learners 8
  --session-id "$RUN_ID-$learner_id-session")
committer=()
if [[ "$rank" -eq "$primary_rank" || "$rank" -eq "$backup_rank" ]]; then
  committer=("$PYTHON_BIN" -m fs_diloco.distributed_syncer.cli committer
    --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT"
    --num-learners 8 --node-ids "$NODE_IDS" --member-id "$member_id"
    --owner-session-id "$RUN_ID-$member_id-committer-session" --threads 8
    --max-prefetch-bytes 1073741824 --replication-factor 2
    --execution-mode hedged --hedge-delay-ms 6000 --lifecycle-cadence 2
    --terminal-strict-audit)
  [[ "$rank" -eq "$primary_rank" ]] || committer+=(--standby)
fi

mark_primary_failed() {
  "$PYTHON_BIN" - "$SHARED_ROOT/distributed/active_work_order.json" "$member_id" \
    "$SHARED_ROOT/logs/distributed_executor_${member_id}.jsonl" \
    "$faults/p08_fault_sequence.jsonl" <<'PY'
import json, sys, time
from fs_diloco.atomic_io import atomic_write_json, safe_read_json
active_path, member_id, executor_log, fault_log = sys.argv[1:]
dispatch = safe_read_json(active_path)
if not isinstance(dispatch, dict) or member_id not in dispatch.get('owner_member_ids', []):
    raise SystemExit('controlled failure target is not an active owner')
rows = [json.loads(line) for line in open(executor_log, encoding='utf-8')]
failure = [row for row in rows if row.get('event_type') == 'executor_injected_failure'][-1]
if failure['work_order_id'] != dispatch.get('work_order_id'):
    raise SystemExit('controlled failure evidence differs from active work order')
dispatch['failed_member_ids'] = sorted(set(dispatch.get('failed_member_ids', [])) | {member_id})
dispatch['backup_activated'] = True
atomic_write_json(active_path, dispatch)
with open(fault_log, 'a', encoding='utf-8') as handle:
    handle.write(json.dumps({
        'event': 'executor_injected_failure',
        'target_member_id': member_id,
        'work_order_id': failure['work_order_id'],
        'attempt_id': failure['attempt_id'],
        'timestamp': time.time(),
    }, sort_keys=True) + '\n')
PY
}

CUDA_VISIBLE_DEVICES=0 taskset -c "$learner_cpus" "${learner[@]}" \
  > "$ARTIFACT_ROOT/${member_id}_learner.log" 2>&1 &
learner_pid=$!
committer_pid=""
if [[ "${#committer[@]}" -gt 0 ]]; then
  CUDA_VISIBLE_DEVICES="" taskset -c "$lfe_cpus" "${committer[@]}" \
    > "$ARTIFACT_ROOT/${member_id}_committer.log" 2>&1 &
  committer_pid=$!
fi

if [[ "$rank" -eq "$primary_rank" ]]; then
  initial=("${executor_base[@]}" --executor-session-id "$RUN_ID-$executor_id-fault-session"
    --inject-error-before-first-attempt)
  set +e
  CUDA_VISIBLE_DEVICES="" "${initial[@]}" \
    > "$ARTIFACT_ROOT/${member_id}_executor.log" 2>&1
  initial_status=$?
  set -e
  [[ "$initial_status" -ne 0 ]]
  cp "$SHARED_ROOT/logs/performance_executor_${member_id}.health.json" \
    "$SHARED_ROOT/logs/performance_executor_${member_id}-fault.health.json"
  mark_primary_failed
  restarted=("${executor_base[@]}" --executor-session-id "$RUN_ID-$executor_id-restart-session")
  CUDA_VISIBLE_DEVICES="" "${restarted[@]}" \
    >> "$ARTIFACT_ROOT/${member_id}_executor.log" 2>&1 &
  executor_pid=$!
else
  executor=("${executor_base[@]}" --executor-session-id "$RUN_ID-$executor_id-session")
  CUDA_VISIBLE_DEVICES="" "${executor[@]}" \
    > "$ARTIFACT_ROOT/${member_id}_executor.log" 2>&1 &
  executor_pid=$!
fi

wait "$learner_pid"
wait "$executor_pid"
if [[ -n "$committer_pid" ]]; then wait "$committer_pid"; fi
