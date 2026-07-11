#!/bin/bash
set -eEuo pipefail
: "${PROJECT_ROOT:?}" "${PYTHON_BIN:?}" "${CONFIG:?}" "${RUN_ID:?}" "${SHARED_ROOT:?}" "${ARTIFACT_ROOT:?}" "${NODE_IDS:?}"
rank="${OMPI_COMM_WORLD_RANK:?}"
member_id=$(printf 'member-%03d' "$rank")
learner_id=$(printf 'learner_%03d' "$rank")
executor_id=$(printf 'executor-%03d' "$rank")
mkdir -p "$SHARED_ROOT/distributed/faults"
owner_member=$("$PYTHON_BIN" - "$RUN_ID" "$NODE_IDS" <<'PY'
import sys
from fs_diloco.distributed_syncer.bootstrap import revision_zero_membership
from fs_diloco.distributed_syncer.executor import ExecutorBudget
from fs_diloco.distributed_syncer.ownership import derive_ownership
run_id, raw = sys.argv[1:]
nodes = tuple(raw.split(','))
learners = tuple(f'learner_{i:03d}' for i in range(len(nodes)))
m = revision_zero_membership(run_id=run_id, learner_ids=learners, node_ids=nodes, budget=ExecutorBudget(threads=4))
print(derive_ownership(m, fragment_ids=(0,), replication_factor=1).owner_ids(0)[0])
PY
)
committer=("$PYTHON_BIN" -m fs_diloco.distributed_syncer.cli committer --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" --num-learners 2 --node-ids "$NODE_IDS" --member-id "$member_id" --owner-session-id "$RUN_ID-$member_id-committer-session" --threads 4)
[[ "$member_id" == "$owner_member" ]] || committer+=(--standby)
executor=("$PYTHON_BIN" -m fs_diloco.distributed_syncer.cli executor --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" --num-learners 2 --member-id "$member_id" --executor-id "$executor_id" --executor-session-id "$RUN_ID-$executor_id-session" --threads 4)
learner=("$PYTHON_BIN" -m fs_diloco.learner --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" --learner-id "$learner_id" --num-learners 2 --session-id "$RUN_ID-$learner_id-session")

supervise() {
  local executor_pid learner_pid committer_pid
  local executor_killed=0 committer_killed=0 whole_killed=0
  CUDA_VISIBLE_DEVICES="" "${executor[@]}" >> "$ARTIFACT_ROOT/${member_id}_executor.log" 2>&1 & executor_pid=$!
  CUDA_VISIBLE_DEVICES=0 "${learner[@]}" > "$ARTIFACT_ROOT/${member_id}_learner.log" 2>&1 & learner_pid=$!
  CUDA_VISIBLE_DEVICES="" "${committer[@]}" > "$ARTIFACT_ROOT/${member_id}_committer.log" 2>&1 & committer_pid=$!
  while [[ ! -f "$SHARED_ROOT/control/stop.json" ]]; do
    if [[ -f "$SHARED_ROOT/distributed/faults/kill_executor" ]] && [[ "$(<"$SHARED_ROOT/distributed/faults/kill_executor")" == "$member_id" ]] && [[ "$executor_killed" -eq 0 ]]; then
      kill -KILL "$executor_pid" 2>/dev/null || true; wait "$executor_pid" 2>/dev/null || true; executor_killed=1
      "$PYTHON_BIN" - "$SHARED_ROOT/distributed/faults/${member_id}_executor_killed.json" <<'PY'
from fs_diloco.atomic_io import atomic_write_json
import sys,time
atomic_write_json(sys.argv[1], {'event':'executor_killed','timestamp':time.time()})
PY
      sleep 1
      CUDA_VISIBLE_DEVICES="" "${executor[@]}" >> "$ARTIFACT_ROOT/${member_id}_executor.log" 2>&1 & executor_pid=$!
    fi
    if [[ -f "$SHARED_ROOT/distributed/faults/kill_committer" ]] && [[ "$(<"$SHARED_ROOT/distributed/faults/kill_committer")" == "$member_id" ]] && [[ "$committer_killed" -eq 0 ]]; then
      kill -KILL "$committer_pid" 2>/dev/null || true; wait "$committer_pid" 2>/dev/null || true; committer_killed=1
      "$PYTHON_BIN" - "$SHARED_ROOT/distributed/faults/${member_id}_committer_killed.json" <<'PY'
from fs_diloco.atomic_io import atomic_write_json
import sys,time
atomic_write_json(sys.argv[1], {'event':'committer_killed','timestamp':time.time()})
PY
    fi
    if [[ -f "$SHARED_ROOT/distributed/faults/kill_whole_member" ]] && [[ "$(<"$SHARED_ROOT/distributed/faults/kill_whole_member")" == "$member_id" ]] && [[ "$whole_killed" -eq 0 ]]; then
      kill -KILL "$executor_pid" "$learner_pid" 2>/dev/null || true
      [[ "$committer_killed" -eq 1 ]] || kill -KILL "$committer_pid" 2>/dev/null || true
      wait "$executor_pid" 2>/dev/null || true; wait "$learner_pid" 2>/dev/null || true; whole_killed=1
      "$PYTHON_BIN" - "$SHARED_ROOT/distributed/faults/${member_id}_whole_killed.json" <<'PY'
from fs_diloco.atomic_io import atomic_write_json
import sys,time
atomic_write_json(sys.argv[1], {'event':'whole_member_killed','timestamp':time.time()})
PY
    fi
    sleep 0.1
  done
  kill "$executor_pid" "$learner_pid" "$committer_pid" 2>/dev/null || true
  wait "$executor_pid" 2>/dev/null || true; wait "$learner_pid" 2>/dev/null || true; wait "$committer_pid" 2>/dev/null || true
}

supervise &
supervisor_pid=$!
if [[ "$rank" -eq 0 ]]; then
  faults="$SHARED_ROOT/distributed/faults"; log="$SHARED_ROOT/logs/distributed_committer.jsonl"; deadline=$((SECONDS + 150))
  while [[ ! -f "$SHARED_ROOT/distributed/active_work_order.json" ]]; do [[ "$SECONDS" -lt "$deadline" ]]; sleep 0.1; done
  printf '%s\n' "$owner_member" > "$faults/kill_executor"
  while [[ ! -f "$faults/${owner_member}_executor_killed.json" ]]; do [[ "$SECONDS" -lt "$deadline" ]]; sleep 0.1; done
  while [[ ! -f "$log" ]] || [[ "$(grep -c 'distributed_transition_committed' "$log" || true)" -lt 1 ]]; do [[ "$SECONDS" -lt "$deadline" ]]; sleep 0.1; done
  printf '%s\n' "$owner_member" > "$faults/kill_committer"
  while [[ ! -f "$faults/${owner_member}_committer_killed.json" ]]; do [[ "$SECONDS" -lt "$deadline" ]]; sleep 0.1; done
  while [[ "$(grep -c 'distributed_transition_committed' "$log" || true)" -lt 2 ]]; do [[ "$SECONDS" -lt "$deadline" ]]; sleep 0.1; done
  printf '%s\n' "$owner_member" > "$faults/kill_whole_member"
  while [[ ! -f "$faults/${owner_member}_whole_killed.json" ]]; do [[ "$SECONDS" -lt "$deadline" ]]; sleep 0.1; done
  "$PYTHON_BIN" - "$SHARED_ROOT/distributed/reconfigure_membership.json" "$owner_member" <<'PY'
from fs_diloco.atomic_io import atomic_write_json
from fs_diloco.protocol.canonical_json import canonical_digest
import sys,time
m=sys.argv[2]
atomic_write_json(sys.argv[1], {'remove_member_id':m,'evidence_digest':canonical_digest({'whole_node_loss':m}),'timestamp':time.time()})
PY
  while [[ ! -f "$SHARED_ROOT/control/stop.json" ]]; do [[ "$SECONDS" -lt "$deadline" ]]; sleep 0.1; done
fi
wait "$supervisor_pid"
