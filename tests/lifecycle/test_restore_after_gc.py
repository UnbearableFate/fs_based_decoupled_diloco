from __future__ import annotations

from dataclasses import replace

from fs_diloco.coordination import OwnerToken
from fs_diloco.log import ProductionTransactionalLog
from fs_diloco.log.gc import apply_gc, approval_token_for, create_gc_mark
from fs_diloco.log.replay import find_valid_snapshots
from tests.coordination.test_production_fencing import _initialize, _prepare, _proposal


def _commit(log, *, learner: str, request_id: str) -> None:
    proposal = _proposal(log, learner=learner)
    log.commit_prepared(_prepare(log, proposal, request_id))


def test_two_snapshot_compaction_restores_falls_back_and_allows_takeover():
    backend, log = _initialize("synthetic-two-restore-points")
    log.activate_owner(
        token=OwnerToken("syncer-a", "session-a", 1), request_id="activate-a"
    )
    _commit(log, learner="learner-before-a", request_id="optimizer-a")
    log.commit_snapshot(request_id="snapshot-a")
    _commit(log, learner="learner-before-b", request_id="optimizer-b")
    log.commit_snapshot(request_id="snapshot-b")

    pins, failures = find_valid_snapshots(log.transactional, limit=2)
    assert not failures
    assert len(pins) == 2
    assert pins[0].snapshot.covered_head.commit_seq > pins[1].snapshot.covered_head.commit_seq

    mark, report = create_gc_mark(log)
    assert report.candidates
    assert all(pin.snapshot_key not in report.candidates for pin in pins)
    applied = apply_gc(
        log,
        mark,
        approval_token=approval_token_for(mark, namespace="synthetic"),
        namespace="synthetic",
        grace_eligible_keys=(),
        request_id="compact-prefix",
    )
    assert applied.deleted

    newest = ProductionTransactionalLog.open(backend, log.spec.run_id, 0)
    newest_replay = newest.replay_from_snapshot()
    assert newest_replay.mode == "snapshot_suffix"
    assert newest_replay.snapshot_id == pins[0].snapshot.snapshot_id

    # The older retained point is independently live: damage to the newest
    # accelerator changes only the selected restore base, never authority.
    latest_key = pins[0].snapshot_key
    original = backend._objects[latest_key]
    damaged = bytearray(original.data)
    damaged[-1] ^= 1
    backend._objects[latest_key] = replace(original, data=bytes(damaged))
    fallback = ProductionTransactionalLog.open(backend, log.spec.run_id, 0)
    fallback_replay = fallback.replay_from_snapshot()
    assert fallback_replay.mode == "snapshot_suffix"
    assert fallback_replay.snapshot_id == pins[1].snapshot.snapshot_id
    assert fallback_replay.replay.head_frontier == newest_replay.replay.head_frontier

    fallback.activate_owner(
        token=OwnerToken("syncer-b", "session-b", 2), request_id="activate-b"
    )
    _commit(fallback, learner="learner-after-gc", request_id="optimizer-after-gc")
    continued = fallback.replay_from_snapshot().replay
    assert continued.head_frontier.fencing_epoch == 2
    assert continued.head_frontier.coordination is not None
    assert continued.head_frontier.coordination.owner_id == "syncer-b"


def test_repeated_snapshot_gc_reaches_a_bounded_active_object_window():
    backend, log = _initialize("synthetic-bounded-window")
    log.activate_owner(
        token=OwnerToken("syncer-a", "session-a", 1), request_id="activate-a"
    )
    counts = []
    nonsnapshot_bytes = []
    for index in range(8):
        _commit(
            log,
            learner=f"learner-{index}",
            request_id=f"optimizer-{index}",
        )
        log.commit_snapshot(request_id=f"snapshot-{index}")
        mark, _report = create_gc_mark(log)
        apply_gc(
            log,
            mark,
            approval_token=approval_token_for(mark, namespace="synthetic"),
            namespace="synthetic",
            grace_eligible_keys=(),
            request_id=f"compact-{index}",
        )
        inventory = backend.list_prefix(log.layout.immutable_prefix)
        counts.append(len(inventory))
        nonsnapshot_bytes.append(
            sum(
                backend.head(key).size
                for key in inventory
                if not key.startswith(log.layout.snapshot_prefix)
            )
        )
        assert log.replay_from_snapshot().mode == "snapshot_suffix"

    # Once two restore bases exist, the active object/tensor window depends on
    # cadence rather than the total number of optimizer transitions.  Snapshot
    # manifests separately retain the compacted logical audit prefix.
    assert max(counts[-3:]) - min(counts[-3:]) <= 3
    assert max(nonsnapshot_bytes[-3:]) - min(nonsnapshot_bytes[-3:]) <= 4096
