from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from fs_diloco.coordination import OwnerToken
from fs_diloco.log import CommitConflict
from fs_diloco.log.codec import content_ref
from fs_diloco.log.snapshot import SnapshotManifestV1
from fs_diloco.protocol.schemas import ControlCommitManifest, SnapshotProjection
from tests.coordination.test_production_fencing import _initialize, _prepare, _proposal


def _activate(log) -> OwnerToken:
    token = OwnerToken("syncer-a", "session-a", 1)
    log.activate_owner(token=token, request_id="activate-a")
    return token


def _published_snapshot(log):
    replay = log.replay(force_full=True)
    snapshot = SnapshotManifestV1.create(replay)
    data = snapshot.canonical_bytes()
    ref = content_ref(log.layout.snapshot_key(snapshot.snapshot_id), data)
    log.backend.put_immutable(ref.key, data, sha256=ref.sha256)
    projection = SnapshotProjection(
        snapshot_ref=ref,
        snapshot_id=snapshot.snapshot_id,
        covered_commit_seq=snapshot.covered_head.commit_seq,
        covered_commit_id=snapshot.covered_head.commit_id,
        covered_state_digest=snapshot.covered_state_digest,
    )
    return snapshot, projection


def test_snapshot_is_immutable_side_object_pinned_by_one_head_transition():
    backend, log = _initialize("p07-snapshot-pin")
    _activate(log)
    covered = log.replay(force_full=True)

    result = log.commit_snapshot(request_id="snapshot-a")
    replay = log.replay(force_full=True)

    assert result.status == "committed"
    assert replay.head_frontier.commit_seq == covered.head_frontier.commit_seq + 1
    pin = replay.commits[-1]
    assert isinstance(pin, ControlCommitManifest)
    assert pin.control_kind == "snapshot_pin"
    assert pin.snapshot is not None
    assert pin.snapshot.covered_commit_id == covered.head_frontier.commit_id
    assert pin.snapshot.snapshot_ref.key in replay.reachable_keys
    assert backend.get(log.layout.head_key) != backend.get(pin.snapshot.snapshot_ref.key)


def test_snapshot_publication_can_be_prepared_without_worker_head_cas():
    _backend, log = _initialize("p08r-snapshot-prepare-only")
    _activate(log)
    before = log.load_head().manifest

    prepared = log.prepare_snapshot_transition(request_id="snapshot-prepare")

    assert log.load_head().manifest == before
    assert prepared.parent_head.manifest == before
    assert prepared.commit.control_kind == "snapshot_pin"
    result = log.commit_prepared(prepared)
    assert result.status == "committed"
    assert log.replay_from_snapshot().mode == "snapshot_suffix"


@pytest.mark.parametrize("failure", ["missing", "corrupt"])
def test_bad_snapshot_never_blocks_empty_cache_strict_replay(failure):
    backend, log = _initialize(f"p07-snapshot-fallback-{failure}")
    _activate(log)
    log.commit_snapshot(request_id="snapshot-a")
    pin = log.replay(force_full=True).commits[-1]
    assert isinstance(pin, ControlCommitManifest) and pin.snapshot is not None
    key = pin.snapshot.snapshot_ref.key
    if failure == "missing":
        del backend._objects[key]
    else:
        original = backend._objects[key]
        damaged = bytearray(original.data)
        damaged[-1] ^= 1
        backend._objects[key] = replace(original, data=bytes(damaged))

    strict = log.replay(force_full=True)
    assert strict.head_frontier.commit_id == pin.commit_id


def test_stale_snapshot_cannot_be_pinned_after_parent_advance():
    _backend, log = _initialize("p07-snapshot-stale")
    token = _activate(log)
    _snapshot, stale_projection = _published_snapshot(log)
    proposal = _proposal(log)
    log.commit_prepared(_prepare(log, proposal, "optimizer-a"))

    with pytest.raises(CommitConflict, match="does not cover the current parent"):
        log.prepare_control_transition(
            control_kind="snapshot_pin",
            token=token,
            request_id="snapshot-stale",
            snapshot=stale_projection,
        )


def test_snapshot_identity_detects_partial_or_conflicting_content():
    _backend, log = _initialize("p07-snapshot-identity")
    _activate(log)
    snapshot = SnapshotManifestV1.create(log.replay(force_full=True))
    payload = snapshot.to_dict()
    payload["covered_state_digest"] = hashlib.sha256(b"different").hexdigest()
    with pytest.raises(ValueError, match="state digest"):
        SnapshotManifestV1.from_dict(payload)

    control = log.replay(force_full=True).commits[-1].to_dict()
    control["snapshot"] = None
    with pytest.raises(Exception, match="snapshot"):
        ControlCommitManifest.from_dict(control)


def test_snapshot_suffix_matches_strict_replay_and_avoids_covered_tensor_reads():
    backend, log = _initialize("p07-snapshot-suffix")
    _activate(log)
    first = _proposal(log, learner="learner-before-snapshot")
    log.commit_prepared(_prepare(log, first, "optimizer-before-snapshot"))
    log.commit_snapshot(request_id="snapshot-a")
    second = _proposal(log, learner="learner-after-snapshot")
    log.commit_prepared(_prepare(log, second, "optimizer-after-snapshot"))

    history_start = len(backend.history)
    accelerated = log.replay_from_snapshot()
    accelerated_records = backend.history[history_start:]
    accelerated_reads = sum(
        record.operation == "get" for record in accelerated_records
    )
    history_start = len(backend.history)
    strict = log.replay(force_full=True)
    strict_reads = sum(
        record.operation == "get" for record in backend.history[history_start:]
    )

    assert accelerated.mode == "snapshot_suffix"
    assert accelerated.covered_commit_seq == 2
    assert accelerated.suffix_length == 2
    assert accelerated.replay == strict
    assert accelerated.storage_get_count == accelerated_reads
    assert accelerated_reads < strict_reads
    covered_large_keys = {
        first.payload_key,
        *(
            ref.key
            for fragment in accelerated.replay.frontiers[2].fragments.values()
            for ref in (fragment.params_ref, fragment.outer_state_ref)
        ),
    }
    assert not any(
        record.operation == "get" and record.key in covered_large_keys
        for record in accelerated_records
    )


def test_snapshot_mode_corruption_falls_back_to_equal_strict_replay():
    backend, log = _initialize("p07-snapshot-mode-fallback")
    _activate(log)
    log.commit_snapshot(request_id="snapshot-a")
    pin = log.replay(force_full=True).commits[-1]
    assert isinstance(pin, ControlCommitManifest) and pin.snapshot is not None
    original = backend._objects[pin.snapshot.snapshot_ref.key]
    damaged = bytearray(original.data)
    damaged[-1] ^= 1
    backend._objects[pin.snapshot.snapshot_ref.key] = replace(
        original, data=bytes(damaged)
    )

    replayed = log.replay_from_snapshot()
    assert replayed.mode == "strict_fallback"
    assert replayed.snapshot_id is None
    assert replayed.fallback_reason is not None
    assert replayed.replay == log.replay(force_full=True)
