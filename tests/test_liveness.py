import time

from fs_diloco.atomic_io import atomic_write_json
from fs_diloco.constants import FORMAT_VERSION
from fs_diloco.liveness import build_liveness_view, liveness_counts, no_progress_timed_out


def _heartbeat(path, *, timestamp, status="active"):
    atomic_write_json(
        path,
        {
            "format_version": FORMAT_VERSION,
            "run_id": "run",
            "learner_id": "learner_000",
            "hostname": "host",
            "pid": 123,
            "timestamp": timestamp,
            "status": status,
            "phase": "inner_steps",
            "last_loaded_global_version": 0,
            "last_local_step": 2,
            "last_update_id": None,
            "tokens_per_sec": 10.0,
        },
    )


def test_heartbeat_view_is_rebuilt_without_persistent_state(tmp_path):
    now = time.time()
    path = tmp_path / "heartbeats" / "learner_000.json"
    _heartbeat(path, timestamp=now)
    stale = build_liveness_view(
        path.parent,
        run_id="run",
        num_learners=1,
        stale_after_seconds=1.0,
        dead_after_seconds=2.0,
        now=now + 1.5,
    )
    assert liveness_counts(stale)["stale"] == 1
    dead = build_liveness_view(
        path.parent,
        run_id="run",
        num_learners=1,
        stale_after_seconds=1.0,
        dead_after_seconds=2.0,
        now=now + 3.0,
    )
    assert liveness_counts(dead)["dead"] == 1


def test_stopped_is_preserved_and_no_progress_timeout(tmp_path):
    now = time.time()
    path = tmp_path / "heartbeats" / "learner_000.json"
    _heartbeat(path, timestamp=now - 1000, status="stopped")
    view = build_liveness_view(
        path.parent,
        run_id="run",
        num_learners=1,
        stale_after_seconds=1.0,
        dead_after_seconds=2.0,
        now=now,
    )
    assert liveness_counts(view)["stopped"] == 1
    assert no_progress_timed_out(0.0, 1.0, now=2.0)
