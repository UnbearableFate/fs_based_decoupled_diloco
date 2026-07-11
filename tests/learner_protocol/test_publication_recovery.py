from __future__ import annotations

import json

import pytest

from fs_diloco.learner_protocol.data_cursor import DataCursor
from fs_diloco.learner_protocol.interval import AuthorityFrontier, ContributionInterval
from fs_diloco.learner_protocol.publication import LearnerPublisher
from fs_diloco.learner_protocol.recovery import recover_learner
from fs_diloco.learner_protocol.rng_state import RngCursor
from fs_diloco.learner_protocol.session import LearnerSession
from fs_diloco.log.layout import LogLayout
from fs_diloco.storage import FailureRule, ImmutableConflict, InMemoryStorageBackend


def _interval(session: LearnerSession, *, sequence: int = 1) -> ContributionInterval:
    base = AuthorityFrontier(
        commit_id="commit-1",
        commit_seq=1,
        frontier_sha256="1" * 64,
        fragment_versions={0: 1},
        fencing_epoch=1,
        owner_id="syncer-a",
        owner_session_id="owner-a",
    )
    return (
        ContributionInterval.start(
            session=session,
            sequence=sequence,
            fragment_id=0,
            base=base,
            start_step=0,
            start_cursor=DataCursor(0, 0),
            rng_cursor=RngCursor(7, 0),
            transport_dtype="bfloat16",
        )
        .record_step(tokens=16, examples=1)
        .close(end_cursor=DataCursor(1, 0))
    )


def test_marker_last_response_loss_retry_is_idempotent():
    backend = InMemoryStorageBackend()
    layout = LogLayout("run-a", 0)
    session = LearnerSession.new("run-a", 0, "learner_000", session_id="session-a")
    publisher = LearnerPublisher(backend, layout)
    interval = _interval(session)
    payload = b"proposal-tensor-bytes"
    result = publisher.publish(interval, payload, tensor_key="fragment_params", shape=(4,))
    again = publisher.publish(interval, payload, tensor_key="fragment_params", shape=(4,))
    assert result == again
    operations = [record for record in backend.history if record.operation == "put_immutable"]
    first_created = [record.key for record in operations if record.outcome == "created"]
    assert first_created == [
        result.session_ref.key,
        result.payload_ref.key,
        result.request_ref.key,
        result.marker_ref.key,
    ]
    assert not any(record.operation == "conditional_replace" for record in backend.history)


def test_after_effect_timeout_retries_by_request_identity():
    backend = InMemoryStorageBackend()
    backend.inject_failure(FailureRule("put_immutable", "after", occurrence=4))
    layout = LogLayout("run-a", 0)
    session = LearnerSession.new("run-a", 0, "learner_000", session_id="session-a")
    publisher = LearnerPublisher(backend, layout)
    interval = _interval(session)
    with pytest.raises(Exception):
        publisher.publish(interval, b"payload", tensor_key="fragment_params", shape=(1,))
    backend.clear_failures()
    recovered = publisher.publish(interval, b"payload", tensor_key="fragment_params", shape=(1,))
    assert backend.get(recovered.marker_ref.key) == recovered.marker_bytes


@pytest.mark.parametrize("timing", ["before", "after"])
@pytest.mark.parametrize("occurrence", [1, 2, 3, 4])
def test_publication_crash_response_loss_matrix_recovers(timing: str, occurrence: int):
    backend = InMemoryStorageBackend()
    backend.inject_failure(FailureRule("put_immutable", timing, occurrence=occurrence))
    layout = LogLayout("run-a", 0)
    session = LearnerSession.new("run-a", 0, "learner_000", session_id="session-a")
    publisher = LearnerPublisher(backend, layout)
    interval = _interval(session)
    with pytest.raises(Exception):
        publisher.publish(interval, b"payload", tensor_key="fragment_params", shape=(1,))
    backend.clear_failures()
    result = publisher.publish(
        interval, b"payload", tensor_key="fragment_params", shape=(1,)
    )
    markers = backend.list_prefix(layout.learner_publication_prefix)
    assert [key for key in markers if "/markers/" in key] == [result.marker_ref.key]
    assert backend.get(result.marker_ref.key) == result.marker_bytes
    assert not any(record.operation == "conditional_replace" for record in backend.history)


def test_request_identity_matrix_and_canonical_optional_omission():
    backend = InMemoryStorageBackend()
    layout = LogLayout("run-a", 0)
    session = LearnerSession.new("run-a", 0, "learner_000", session_id="session-a")
    publisher = LearnerPublisher(backend, layout)
    first = publisher.publish(
        _interval(session), b"same", tensor_key="fragment_params", shape=(1,)
    )
    marker = json.loads(first.marker_bytes)
    assert "previous_interval_proposal_id" not in marker
    assert marker["request_id"] == first.request_id
    with pytest.raises(ImmutableConflict):
        publisher.publish(
            _interval(session), b"conflict", tensor_key="fragment_params", shape=(1,)
        )
    different_session = LearnerSession.new(
        "run-a", 0, "learner_000", session_id="session-b"
    )
    distinct = publisher.publish(
        _interval(different_session), b"same", tensor_key="fragment_params", shape=(1,)
    )
    assert distinct.request_id != first.request_id
    with pytest.raises(ValueError, match="null"):
        publisher.publish(
            _interval(different_session, sequence=2),
            b"same",
            tensor_key="fragment_params",
            shape=(1,),
            previous_interval_proposal_id=None,
        )


def test_recovery_from_empty_local_state_never_reuses_session_sequence():
    backend = InMemoryStorageBackend()
    layout = LogLayout("run-a", 0)
    old_session = LearnerSession.new("run-a", 0, "learner_000", session_id="session-a")
    publisher = LearnerPublisher(backend, layout)
    result = publisher.publish(
        _interval(old_session), b"payload", tensor_key="fragment_params", shape=(1,)
    )
    report = recover_learner(
        backend,
        layout,
        learner_id="learner_000",
        committed_proposal_ids=frozenset({result.proposal_id}),
        new_session_id="session-b",
    )
    assert report.new_session.session_id == "session-b"
    assert report.published_intervals == 1
    assert report.committed_intervals == 1
    assert report.lost_tokens == 0
    assert report.repeated_tokens_estimate == 0
    assert report.next_sequence == 1
    assert report.uncommitted_intervals == 0


def test_uncommitted_interval_is_reported_as_lost_not_exactly_resumed():
    backend = InMemoryStorageBackend()
    layout = LogLayout("run-a", 0)
    session = LearnerSession.new("run-a", 0, "learner_000", session_id="session-a")
    LearnerPublisher(backend, layout).publish(
        _interval(session), b"payload", tensor_key="fragment_params", shape=(1,)
    )
    report = recover_learner(
        backend,
        layout,
        learner_id="learner_000",
        committed_proposal_ids=frozenset(),
        new_session_id="session-b",
    )
    assert report.warm_not_exact is True
    assert report.lost_tokens == 16
    assert report.repeated_tokens_estimate == 0
    assert report.uncommitted_intervals == 1
    assert report.max_uncommitted_base_commit_seq == 1


def test_committed_interval_identity_prevents_false_lost_work_report():
    backend = InMemoryStorageBackend()
    layout = LogLayout("run-a", 0)
    session = LearnerSession.new("run-a", 0, "learner_000", session_id="session-a")
    LearnerPublisher(backend, layout).publish(
        _interval(session), b"payload", tensor_key="fragment_params", shape=(1,)
    )
    report = recover_learner(
        backend,
        layout,
        learner_id="learner_000",
        committed_proposal_ids=frozenset(),
        committed_interval_identities=frozenset(
            {("learner_000", "session-a", 0, 1)}
        ),
        new_session_id="session-b",
    )
    assert report.committed_intervals == 1
    assert report.lost_tokens == 0
    assert report.uncommitted_intervals == 0
