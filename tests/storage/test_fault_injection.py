from __future__ import annotations

import errno

import pytest

from fs_diloco.storage import (
    FaultEvent,
    FaultInjectingBackend,
    FaultSchedule,
    InMemoryStorageBackend,
    InjectedTimeout,
    IntegrityError,
    StorageIOError,
)


def test_fault_schedule_round_trips_with_stable_digest_and_history():
    schedule = FaultSchedule.seeded(
        20260710,
        operations=("get", "put_immutable", "conditional_replace", "list_prefix"),
        probability=1.0,
    )
    replay = FaultSchedule.from_json(schedule.to_json())
    assert replay == schedule
    assert replay.digest == schedule.digest


def test_after_effect_timeout_retry_is_idempotent():
    base = InMemoryStorageBackend()
    initial = base.put_if_absent("control/head", b"zero")
    schedule = FaultSchedule(
        1,
        (FaultEvent("conditional_replace", "after", 1, "timeout"),),
    )
    backend = FaultInjectingBackend(base, schedule)
    with pytest.raises(InjectedTimeout):
        backend.conditional_replace(
            "control/head", expected_version=initial.version, data=b"one"
        )
    retry = backend.conditional_replace(
        "control/head", expected_version=initial.version, data=b"one"
    )
    assert base.get("control/head", expected_version=retry.version) == b"one"


@pytest.mark.parametrize("kind", ["short_read", "corrupt_read"])
def test_read_corruption_faults_fail_closed(kind):
    base = InMemoryStorageBackend()
    base.put_immutable("objects/a", b"verified")
    backend = FaultInjectingBackend(
        base,
        FaultSchedule(1, (FaultEvent("get", "after", 1, kind),)),
    )
    with pytest.raises(IntegrityError):
        backend.get("objects/a")


def test_eio_is_typed_and_retryable():
    backend = FaultInjectingBackend(
        InMemoryStorageBackend(),
        FaultSchedule(1, (FaultEvent("put_immutable", "before", 1, "eio"),)),
    )
    with pytest.raises(StorageIOError) as captured:
        backend.put_immutable("objects/a", b"x")
    assert captured.value.errno == errno.EIO
    assert captured.value.retryable


def test_listing_omission_never_controls_head_or_cas():
    base = InMemoryStorageBackend()
    initial = base.put_if_absent("control/head", b"zero")
    backend = FaultInjectingBackend(
        base,
        FaultSchedule(1, (FaultEvent("list_prefix", "after", 1, "omit_list"),)),
    )
    assert backend.list_prefix("control/") == ()
    assert backend.head("control/head") == initial
    updated = backend.conditional_replace(
        "control/head", expected_version=initial.version, data=b"one"
    )
    assert backend.get("control/head", expected_version=updated.version) == b"one"

