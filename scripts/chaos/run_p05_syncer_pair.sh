#!/usr/bin/env bash
set -eEuo pipefail

: "${PROJECT_ROOT:?PROJECT_ROOT is required}"
: "${PYTHON_BIN:?PYTHON_BIN is required}"
: "${CONFIG:?CONFIG is required}"
: "${RUN_ID:?RUN_ID is required}"
: "${SHARED_ROOT:?SHARED_ROOT is required}"
: "${ARTIFACT_ROOT:?ARTIFACT_ROOT is required}"
: "${NUM_LEARNERS:?NUM_LEARNERS is required}"

mkdir -p "$ARTIFACT_ROOT"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"
export CUDA_VISIBLE_DEVICES=0

"$PYTHON_BIN" -m fs_diloco.syncer \
  --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" \
  --num-learners "$NUM_LEARNERS" \
  --owner-id terminal-active --owner-session-id terminal-active-session \
  > "$ARTIFACT_ROOT/syncer_active.log" 2>&1 &
active_pid=$!

sleep 2
"$PYTHON_BIN" -m fs_diloco.syncer \
  --config "$CONFIG" --run-id "$RUN_ID" --shared-root "$SHARED_ROOT" \
  --num-learners "$NUM_LEARNERS" \
  --owner-id terminal-standby --owner-session-id terminal-standby-session \
  --standby > "$ARTIFACT_ROOT/syncer_standby.log" 2>&1 &
standby_pid=$!

observed_count=-1
for _ in $(seq 1 1200); do
  if ! kill -0 "$active_pid" 2>/dev/null; then
    echo "active syncer exited before injected kill" >&2
    wait "$active_pid"
    exit 1
  fi
  observed_count=$(
    "$PYTHON_BIN" - "$SHARED_ROOT/control/latest.json" <<'PY' 2>/dev/null || true
import json
from pathlib import Path
import sys

try:
    value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(int(value.get("optimizer_transition_count", -1)))
except Exception:
    print(-1)
PY
  )
  if [[ "$observed_count" -ge 2 ]]; then
    break
  fi
  sleep 0.5
done
if [[ "$observed_count" -lt 2 ]]; then
  echo "timed out before active syncer reached two optimizer transitions" >&2
  exit 1
fi

kill_epoch=$(date +%s.%N)
kill -KILL "$active_pid"
set +e
wait "$active_pid"
active_exit=$?
set -e
if [[ "$active_exit" -ne 137 ]]; then
  echo "active syncer kill exit was $active_exit, expected 137" >&2
  exit 1
fi
"$PYTHON_BIN" - "$ARTIFACT_ROOT/active_kill.json" "$active_pid" \
  "$active_exit" "$observed_count" "$kill_epoch" <<'PY'
import json
from pathlib import Path
import sys

output, pid, exit_code, count, timestamp = sys.argv[1:]
Path(output).write_text(
    json.dumps(
        {
            "signal": "SIGKILL",
            "pid": int(pid),
            "exit_code": int(exit_code),
            "observed_optimizer_transition_count": int(count),
            "injected_at_unix_seconds": float(timestamp),
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY

wait "$standby_pid"
