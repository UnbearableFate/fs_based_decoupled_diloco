#!/bin/bash
set -eEuo pipefail
: "${PROJECT_ROOT:?}" "${PYTHON_BIN:?}" "${CONFIG:?}" "${RUN_ID:?}" "${SHARED_ROOT:?}" "${ARTIFACT_ROOT:?}" "${NODE_IDS:?}"
rank="${OMPI_COMM_WORLD_RANK:?}"
member_id=$(printf 'member-%03d' "$rank")
learner_id=$(printf 'learner_%03d' "$rank")
executor_id=$(printf 'executor-%03d' "$rank")
faults="$SHARED_ROOT/distributed/faults"
mkdir -p "$faults"

committer=("$PYTHON_BIN" -m fs_diloco.distributed_syncer.cli committer --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" --num-learners 2 --node-ids "$NODE_IDS" --member-id "$member_id" --owner-session-id "$RUN_ID-$member_id-committer-session" --threads 4 --replication-factor 2 --execution-mode active_active)
[[ "$rank" -eq 0 ]] || committer+=(--standby)
executor=("$PYTHON_BIN" -m fs_diloco.distributed_syncer.cli executor --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" --num-learners 2 --member-id "$member_id" --executor-id "$executor_id" --executor-session-id "$RUN_ID-$executor_id-session" --threads 4)
learner=("$PYTHON_BIN" -m fs_diloco.learner --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" --learner-id "$learner_id" --num-learners 2 --session-id "$RUN_ID-$learner_id-session")

write_event() {
  "$PYTHON_BIN" - "$faults/fault_sequence.jsonl" "$1" "$2" <<'PY'
import json,sys,time
path,event,target=sys.argv[1:]
with open(path,'a',encoding='utf-8') as handle:
    handle.write(json.dumps({'event':event,'target_member_id':target,'timestamp':time.time()},sort_keys=True)+'\n')
PY
}

mark_dispatch_failed() {
  "$PYTHON_BIN" - "$SHARED_ROOT/distributed/active_work_order.json" "$1" <<'PY'
import sys
from fs_diloco.atomic_io import atomic_write_json, safe_read_json
path,target=sys.argv[1:]
payload=safe_read_json(path)
if not isinstance(payload,dict) or target not in payload.get('owner_member_ids',[]):
    raise SystemExit('target is not an active redundant owner')
payload['failed_member_ids']=sorted(set(payload.get('failed_member_ids',[]))|{target})
payload['backup_activated']=True
atomic_write_json(path,payload)
PY
}

supervise() {
  local executor_pid learner_pid committer_pid
  local executor_killed=0 committer_killed=0 whole_killed=0
  CUDA_VISIBLE_DEVICES="" "${executor[@]}" >> "$ARTIFACT_ROOT/${member_id}_executor.log" 2>&1 & executor_pid=$!
  CUDA_VISIBLE_DEVICES=0 "${learner[@]}" > "$ARTIFACT_ROOT/${member_id}_learner.log" 2>&1 & learner_pid=$!
  CUDA_VISIBLE_DEVICES="" "${committer[@]}" >> "$ARTIFACT_ROOT/${member_id}_committer.log" 2>&1 & committer_pid=$!
  while [[ ! -f "$SHARED_ROOT/control/stop.json" ]]; do
    if [[ -f "$faults/kill_executor" ]] && [[ "$(<"$faults/kill_executor")" == "$member_id" ]] && [[ "$executor_killed" -eq 0 ]]; then
      kill -KILL "$executor_pid" 2>/dev/null || true
      wait "$executor_pid" 2>/dev/null || true
      executor_killed=1
      write_event executor_process_killed "$member_id"
      touch "$faults/${member_id}_executor_killed"
      while [[ ! -f "$faults/${member_id}_release_executor" ]]; do sleep 0.1; done
      CUDA_VISIBLE_DEVICES="" "${executor[@]}" >> "$ARTIFACT_ROOT/${member_id}_executor.log" 2>&1 & executor_pid=$!
    fi
    if [[ -f "$faults/kill_committer" ]] && [[ "$(<"$faults/kill_committer")" == "$member_id" ]] && [[ "$committer_killed" -eq 0 ]]; then
      kill -KILL "$committer_pid" 2>/dev/null || true
      wait "$committer_pid" 2>/dev/null || true
      committer_killed=1
      write_event committer_process_killed "$member_id"
      touch "$faults/${member_id}_committer_killed"
      sleep 2
      standby_committer=("${committer[@]}")
      standby_committer+=(--standby)
      CUDA_VISIBLE_DEVICES="" "${standby_committer[@]}" >> "$ARTIFACT_ROOT/${member_id}_committer.log" 2>&1 & committer_pid=$!
    fi
    if [[ -f "$faults/kill_whole_member" ]] && [[ "$(<"$faults/kill_whole_member")" == "$member_id" ]] && [[ "$whole_killed" -eq 0 ]]; then
      kill -KILL "$executor_pid" "$learner_pid" "$committer_pid" 2>/dev/null || true
      wait "$executor_pid" 2>/dev/null || true
      wait "$learner_pid" 2>/dev/null || true
      wait "$committer_pid" 2>/dev/null || true
      whole_killed=1
      write_event whole_learner_member_killed "$member_id"
      touch "$faults/${member_id}_whole_killed"
    fi
    sleep 0.1
  done
  kill "$executor_pid" "$learner_pid" "$committer_pid" 2>/dev/null || true
  wait "$executor_pid" 2>/dev/null || true
  wait "$learner_pid" 2>/dev/null || true
  wait "$committer_pid" 2>/dev/null || true
}

supervise &
supervisor_pid=$!
if [[ "$rank" -eq 0 ]]; then
  log="$SHARED_ROOT/logs/distributed_committer.jsonl"
  deadline=$((SECONDS + 240))
  wait_for_count() {
    local wanted="$1"
    while [[ ! -f "$log" ]] || [[ "$(grep -c 'distributed_transition_committed' "$log" || true)" -lt "$wanted" ]]; do
      [[ "$SECONDS" -lt "$deadline" ]]
      sleep 0.1
    done
  }
  wait_for_new_order() {
    local previous="${1:-}"
    while true; do
      current=$("$PYTHON_BIN" - "$SHARED_ROOT/distributed/active_work_order.json" <<'PY'
import sys
from fs_diloco.atomic_io import safe_read_json
value=safe_read_json(sys.argv[1])
print(value.get('work_order_id','') if isinstance(value,dict) else '')
PY
)
      [[ -n "$current" && "$current" != "$previous" ]] && break
      [[ "$SECONDS" -lt "$deadline" ]]
      sleep 0.1
    done
  }
  owner_role() {
    "$PYTHON_BIN" - "$SHARED_ROOT/distributed/active_work_order.json" "$1" <<'PY'
import sys
from fs_diloco.atomic_io import safe_read_json
value=safe_read_json(sys.argv[1]); index=int(sys.argv[2])
print(value['owner_member_ids'][index])
PY
  }

  static_owner_role() {
    "$PYTHON_BIN" - "$RUN_ID" "$NODE_IDS" "$1" <<'PY'
import sys
from fs_diloco.distributed_syncer.bootstrap import revision_zero_membership
from fs_diloco.distributed_syncer.executor import ExecutorBudget
from fs_diloco.distributed_syncer.ownership import derive_ownership
run_id,raw,index=sys.argv[1:]
nodes=tuple(raw.split(',')); learners=tuple(f'learner_{i:03d}' for i in range(2))
membership=revision_zero_membership(run_id=run_id,learner_ids=learners,node_ids=nodes,budget=ExecutorBudget(threads=4))
print(derive_ownership(membership,fragment_ids=(0,),replication_factor=2).owner_ids(0)[int(index)])
PY
  }

  primary=$(static_owner_role 0)
  printf '%s\n' "$primary" > "$faults/kill_executor"
  while [[ ! -f "$faults/${primary}_executor_killed" ]]; do [[ "$SECONDS" -lt "$deadline" ]]; sleep 0.1; done
  wait_for_new_order
  order1="$current"
  mark_dispatch_failed "$primary"
  wait_for_count 1
  touch "$faults/${primary}_release_executor"

  rm -f "$faults/kill_executor"
  backup=$(static_owner_role 1)
  printf '%s\n' "$backup" > "$faults/kill_executor"
  while [[ ! -f "$faults/${backup}_executor_killed" ]]; do [[ "$SECONDS" -lt "$deadline" ]]; sleep 0.1; done
  wait_for_new_order "$order1"
  order2="$current"
  mark_dispatch_failed "$backup"
  wait_for_count 2
  touch "$faults/${backup}_release_executor"

  rm -f "$faults/kill_executor"
  printf '%s\n' member-000 > "$faults/kill_committer"
  while [[ ! -f "$faults/member-000_committer_killed" ]]; do [[ "$SECONDS" -lt "$deadline" ]]; sleep 0.1; done
  wait_for_count 3

  printf '%s\n' member-001 > "$faults/kill_whole_member"
  while [[ ! -f "$faults/member-001_whole_killed" ]]; do [[ "$SECONDS" -lt "$deadline" ]]; sleep 0.1; done
  wait_for_new_order "$order2"
  mark_dispatch_failed member-001
  wait_for_count 4
  while [[ ! -f "$SHARED_ROOT/control/stop.json" ]]; do [[ "$SECONDS" -lt "$deadline" ]]; sleep 0.1; done
fi
wait "$supervisor_pid"
