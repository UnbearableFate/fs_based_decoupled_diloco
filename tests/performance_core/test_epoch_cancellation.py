from __future__ import annotations

from threading import Event

import pytest

from fs_diloco.distributed_syncer.prefetch import (
    BoundedPrefetch,
    PlanningScope,
    PrefetchCancelled,
)
from fs_diloco.distributed_syncer.scanner import DiscoveryCursor
from fs_diloco.protocol.schemas import ObjectRef


def _scope(head="head-a", epoch=1):
    return PlanningScope(
        head_commit_id=head,
        fencing_epoch=epoch,
        membership_revision=0,
        owner_session_id="owner-session",
    )


def test_head_or_epoch_jump_cancels_prefetch_and_forces_new_scope():
    gate = Event()
    started = Event()
    ref = ObjectRef(key="immutable/object", sha256="a" * 64, size=4)
    prefetch = BoundedPrefetch(scope=_scope(), max_workers=1, max_bytes=4)

    def load(_ref):
        started.set()
        gate.wait(timeout=2)
        return b"data"

    future = prefetch.submit(ref, scope=_scope(), load=load)
    assert started.wait(timeout=2)
    assert prefetch.invalidate(_scope(head="head-b"))
    gate.set()
    with pytest.raises(PrefetchCancelled):
        future.result(timeout=2)
    with pytest.raises(PrefetchCancelled):
        prefetch.submit(ref, scope=_scope(), load=lambda _ref: b"data")
    prefetch.close()


def test_prefetch_byte_budget_and_scope_are_hard_bounds():
    ref = ObjectRef(key="immutable/object", sha256="b" * 64, size=8)
    prefetch = BoundedPrefetch(scope=_scope(), max_workers=1, max_bytes=4)
    with pytest.raises(MemoryError, match="byte budget"):
        prefetch.submit(ref, scope=_scope(), load=lambda _ref: b"12345678")
    with pytest.raises(PrefetchCancelled, match="scope"):
        prefetch.submit(
            ObjectRef(key="immutable/small", sha256="c" * 64, size=1),
            scope=_scope(epoch=2),
            load=lambda _ref: b"x",
        )
    prefetch.close()


def test_discovery_cursor_never_filters_inventory_and_restart_is_equivalent():
    cursor = DiscoveryCursor()
    first = cursor.observe(["b", "a", "b"])
    assert first.keys == ("a", "b")
    assert first.newly_observed == ("a", "b")
    second = cursor.observe(["c", "a"])
    assert second.keys == ("a", "c")
    assert second.newly_observed == ("c",)
    restarted = DiscoveryCursor().observe(["c", "a"])
    assert restarted.keys == second.keys
    assert restarted.inventory_digest == second.inventory_digest
