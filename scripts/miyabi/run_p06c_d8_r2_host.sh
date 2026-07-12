#!/bin/bash
set -eEuo pipefail
: "${PROJECT_ROOT:?}" "${PYTHON_BIN:?}" "${CONFIG:?}" "${RUN_ID:?}" "${SHARED_ROOT:?}" "${ARTIFACT_ROOT:?}" "${NODE_IDS:?}"
LIFECYCLE_CADENCE="${LIFECYCLE_CADENCE:-0}"
REQUIRED_CAPSULES="${REQUIRED_CAPSULES:-0}"
D8_DEADLINE_SECONDS="${D8_DEADLINE_SECONDS:-840}"
[[ "$D8_DEADLINE_SECONDS" =~ ^[0-9]+$ ]] && [[ "$D8_DEADLINE_SECONDS" -ge 840 ]]
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
run_id,raw=sys.argv[1:]; nodes=tuple(raw.split(',')); learners=tuple(f'learner_{i:03d}' for i in range(8))
membership=revision_zero_membership(run_id=run_id,learner_ids=learners,node_ids=nodes,budget=ExecutorBudget(threads=8))
owners=derive_ownership(membership,fragment_ids=(0,),replication_factor=2).owner_ids(0)
print(*(int(value.split('-')[-1]) for value in owners))
PY
)
primary_member=$(printf 'member-%03d' "$primary_rank")

executor=("$PYTHON_BIN" -m fs_diloco.distributed_syncer.cli executor --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" --num-learners 8 --member-id "$member_id" --executor-id "$executor_id" --executor-session-id "$RUN_ID-$executor_id-session" --threads 8)
learner=("$PYTHON_BIN" -m fs_diloco.learner --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" --learner-id "$learner_id" --num-learners 8 --session-id "$RUN_ID-$learner_id-session")
committer=()
if [[ "$rank" -eq "$primary_rank" || "$rank" -eq "$backup_rank" ]]; then
  committer=("$PYTHON_BIN" -m fs_diloco.distributed_syncer.cli committer --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" --num-learners 8 --node-ids "$NODE_IDS" --member-id "$member_id" --owner-session-id "$RUN_ID-$member_id-committer-session" --threads 8 --replication-factor 2 --execution-mode hedged --hedge-delay-ms 6000)
  if [[ "$LIFECYCLE_CADENCE" -gt 0 ]]; then
    committer+=(--lifecycle-cadence "$LIFECYCLE_CADENCE")
  fi
  [[ "$rank" -eq "$primary_rank" ]] || committer+=(--standby)
fi

write_event() {
  "$PYTHON_BIN" - "$faults/fault_sequence.jsonl" "$1" "$2" <<'PY'
import json,sys,time
with open(sys.argv[1],'a',encoding='utf-8') as handle:
    handle.write(json.dumps({'event':sys.argv[2],'target_member_id':sys.argv[3],'timestamp':time.time()},sort_keys=True)+'\n')
PY
}

mark_dispatch_failed() {
  "$PYTHON_BIN" - "$SHARED_ROOT/distributed/active_work_order.json" "$1" <<'PY'
import sys
from fs_diloco.atomic_io import atomic_write_json, safe_read_json
path,target=sys.argv[1:]; payload=safe_read_json(path)
if not isinstance(payload,dict) or target not in payload.get('owner_member_ids',[]):
    raise SystemExit('D8 failure target is not an active redundant owner')
payload['failed_member_ids']=sorted(set(payload.get('failed_member_ids',[]))|{target})
payload['backup_activated']=True
atomic_write_json(path,payload)
PY
}

supervise() {
  local executor_pid learner_pid committer_pid=""
  local executor_killed=0 whole_killed=0
  CUDA_VISIBLE_DEVICES="" "${executor[@]}" >> "$ARTIFACT_ROOT/${member_id}_executor.log" 2>&1 & executor_pid=$!
  CUDA_VISIBLE_DEVICES=0 "${learner[@]}" > "$ARTIFACT_ROOT/${member_id}_learner.log" 2>&1 & learner_pid=$!
  if [[ "${#committer[@]}" -gt 0 ]]; then
    CUDA_VISIBLE_DEVICES="" "${committer[@]}" >> "$ARTIFACT_ROOT/${member_id}_committer.log" 2>&1 & committer_pid=$!
  fi
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
    if [[ -f "$faults/kill_whole_member" ]] && [[ "$(<"$faults/kill_whole_member")" == "$member_id" ]] && [[ "$whole_killed" -eq 0 ]]; then
      kill -KILL "$executor_pid" "$learner_pid" 2>/dev/null || true
      [[ -z "$committer_pid" ]] || kill -KILL "$committer_pid" 2>/dev/null || true
      wait "$executor_pid" 2>/dev/null || true
      wait "$learner_pid" 2>/dev/null || true
      [[ -z "$committer_pid" ]] || wait "$committer_pid" 2>/dev/null || true
      whole_killed=1
      write_event whole_learner_member_killed "$member_id"
      touch "$faults/${member_id}_whole_killed"
    fi
    sleep 0.1
  done
  kill "$executor_pid" "$learner_pid" 2>/dev/null || true
  [[ -z "$committer_pid" ]] || kill "$committer_pid" 2>/dev/null || true
  wait "$executor_pid" 2>/dev/null || true
  wait "$learner_pid" 2>/dev/null || true
  [[ -z "$committer_pid" ]] || wait "$committer_pid" 2>/dev/null || true
}

supervise &
supervisor_pid=$!
if [[ "$rank" -eq 0 ]]; then
  log="$SHARED_ROOT/logs/distributed_committer.jsonl"
  deadline=$((SECONDS + D8_DEADLINE_SECONDS))
  wait_for_count() {
    local wanted="$1"
    while [[ ! -f "$log" ]] || [[ "$(grep -c 'distributed_transition_committed' "$log" || true)" -lt "$wanted" ]]; do
      [[ "$SECONDS" -lt "$deadline" ]]
      sleep 0.2
    done
  }
  wait_for_new_order() {
    local previous="$1"
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
      sleep 0.2
    done
  }
  write_reconfiguration() {
    "$PYTHON_BIN" - "$SHARED_ROOT/distributed/reconfigure_membership.json" "$RUN_ID" "$NODE_IDS" "$primary_member" <<'PY'
import sys
from fs_diloco.atomic_io import atomic_write_json
from fs_diloco.distributed_syncer.bootstrap import revision_zero_membership
from fs_diloco.distributed_syncer.executor import ExecutorBudget
from fs_diloco.distributed_syncer.failure_evidence import FailureEvidenceV1
from fs_diloco.distributed_syncer.reconfiguration import ReconfigurationRequestV1
from fs_diloco.protocol.canonical_json import canonical_digest
path,run_id,raw,target=sys.argv[1:]
nodes=tuple(raw.split(',')); learners=tuple(f'learner_{i:03d}' for i in range(8))
membership=revision_zero_membership(run_id=run_id,learner_ids=learners,node_ids=nodes,budget=ExecutorBudget(threads=8))
reporters=[item.member_id for item in membership.members if item.member_id != target][:2]
evidence=FailureEvidenceV1.create({'run_id':run_id,'run_generation':0,'membership_revision':0,'suspected_member_id':target,'reason':'learner_node_loss','reporter_member_ids':reporters,'observation_digest':canonical_digest({'fault_tape':'d8-r2-whole-node','target':target})})
request=ReconfigurationRequestV1.create({'expected_membership_revision':0,'expected_membership_digest':membership.membership_digest,'remove_member_id':target,'evidence':evidence})
atomic_write_json(path,request.to_dict())
PY
  }

  wait_for_count 1
  if [[ "$REQUIRED_CAPSULES" -gt 0 ]]; then
    capsule_dir="$SHARED_ROOT/authority/runs/$RUN_ID/generations/00000000/immutable/lifecycle/capsules/markers"
    while [[ ! -d "$capsule_dir" ]] || [[ "$(find "$capsule_dir" -maxdepth 1 -type f | wc -l)" -lt "$REQUIRED_CAPSULES" ]]; do
      [[ "$SECONDS" -lt "$deadline" ]]
      sleep 0.2
    done
  fi
  previous_order=$("$PYTHON_BIN" - "$log" <<'PY'
import json,sys
events=[json.loads(line) for line in open(sys.argv[1],encoding='utf-8')]
print([item for item in events if item.get('event_type')=='distributed_transition_committed'][-1]['work_order_id'])
PY
)
  printf '%s\n' "$primary_member" > "$faults/kill_executor"
  while [[ ! -f "$faults/${primary_member}_executor_killed" ]]; do [[ "$SECONDS" -lt "$deadline" ]]; sleep 0.1; done
  wait_for_new_order "$previous_order"
  mark_dispatch_failed "$primary_member"
  wait_for_count 2
  touch "$faults/${primary_member}_release_executor"
  rm -f "$faults/kill_executor"

  printf '%s\n' "$primary_member" > "$faults/kill_whole_member"
  while [[ ! -f "$faults/${primary_member}_whole_killed" ]]; do [[ "$SECONDS" -lt "$deadline" ]]; sleep 0.1; done
  write_reconfiguration
  while [[ ! -f "$log" ]] || ! grep -q 'membership_reconfigured' "$log"; do [[ "$SECONDS" -lt "$deadline" ]]; sleep 0.2; done
  wait_for_count 10
  while [[ ! -f "$SHARED_ROOT/control/stop.json" ]]; do [[ "$SECONDS" -lt "$deadline" ]]; sleep 0.2; done
fi
wait "$supervisor_pid"
