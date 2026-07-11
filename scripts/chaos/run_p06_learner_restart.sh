#!/bin/bash
set -eEuo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"
: "${PYTHON_BIN:?PYTHON_BIN is required}"
: "${CONFIG:?CONFIG is required}"
: "${RUN_ID:?RUN_ID is required}"
: "${SHARED_ROOT:?SHARED_ROOT is required}"
: "${ARTIFACT_ROOT:?ARTIFACT_ROOT is required}"

cd "$PROJECT_ROOT"
export CUDA_VISIBLE_DEVICES=0
learner_log="$SHARED_ROOT/logs/learner_000.jsonl"
learner_stdout="$ARTIFACT_ROOT/learner_000_stdout.log"
"$PYTHON_BIN" -m fs_diloco.learner \
  --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" \
  --learner-id learner_000 --num-learners 1 \
  >> "$learner_stdout" 2>&1 &
learner_pid=$!
for _ in $(seq 1 600); do
  if grep -q '"event_type": "update_written"' "$learner_log" 2>/dev/null; then
    kill -9 "$learner_pid" 2>/dev/null || true
    wait "$learner_pid" 2>/dev/null || true
    printf '{"killed_pid":%s,"hostname":"%s","after_first_publication":true}\n' \
      "$learner_pid" "$(hostname)" > "$ARTIFACT_ROOT/learner_kill.json"
    break
  fi
  if ! kill -0 "$learner_pid" 2>/dev/null; then
    wait "$learner_pid"
    echo "first learner exited before restart injection" >&2
    exit 1
  fi
  sleep 0.1
done
[[ -f "$ARTIFACT_ROOT/learner_kill.json" ]]
"$PYTHON_BIN" -m fs_diloco.learner \
  --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" \
  --learner-id learner_000 --num-learners 1 \
  >> "$learner_stdout" 2>&1
