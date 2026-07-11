#!/bin/bash
set -eEuo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"
: "${PYTHON_BIN:?PYTHON_BIN is required}"
: "${CONFIG:?CONFIG is required}"
: "${RUN_ID:?RUN_ID is required}"
: "${SHARED_ROOT:?SHARED_ROOT is required}"
: "${ARTIFACT_ROOT:?ARTIFACT_ROOT is required}"
: "${NUM_LEARNERS:?NUM_LEARNERS is required}"

cd "$PROJECT_ROOT"
export CUDA_VISIBLE_DEVICES=0
learner_id=learner_000
log="$SHARED_ROOT/logs/$learner_id.jsonl"
"$PYTHON_BIN" -m fs_diloco.learner \
  --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" \
  --learner-id "$learner_id" --num-learners "$NUM_LEARNERS" &
pid=$!
for _ in $(seq 1 1800); do
  if grep -q '"event_type": "update_written"' "$log" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
    "$PYTHON_BIN" - "$ARTIFACT_ROOT/learner_kill.json" "$pid" <<'PY'
import json
from pathlib import Path
import socket
import sys
import time
Path(sys.argv[1]).write_text(json.dumps({
    "signal": "SIGKILL",
    "pid": int(sys.argv[2]),
    "hostname": socket.gethostname(),
    "after_first_publication": True,
    "injected_at_unix_seconds": time.time(),
}, indent=2, sort_keys=True) + "\n")
PY
    break
  fi
  if ! kill -0 "$pid" 2>/dev/null; then
    wait "$pid"
    echo "terminal learner exited before restart injection" >&2
    exit 1
  fi
  sleep 0.1
done
[[ -f "$ARTIFACT_ROOT/learner_kill.json" ]]
exec "$PYTHON_BIN" -m fs_diloco.learner \
  --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" \
  --learner-id "$learner_id" --num-learners "$NUM_LEARNERS"
