from __future__ import annotations

import inspect
from types import SimpleNamespace
import time

import fs_diloco.syncer as syncer_module


class _Logger:
    def __init__(self):
        self.events = []

    def event(self, event_type, **fields):
        self.events.append((event_type, fields))


def test_non_authoritative_substage_renews_until_worker_finishes(monkeypatch):
    renewals = []

    def fake_renew(**kwargs):
        sequence = len(renewals) + 2
        renewed = SimpleNamespace(record=SimpleNamespace(lease_sequence=sequence))
        renewals.append((kwargs["loaded_lease"], renewed))
        return renewed

    monkeypatch.setattr(syncer_module, "_renew_owner_lease", fake_renew)
    initial = SimpleNamespace(record=SimpleNamespace(lease_sequence=1))
    config = SimpleNamespace(
        coordination=SimpleNamespace(renew_interval_seconds=0.01)
    )
    logger = _Logger()

    def slow_read_only_work():
        time.sleep(0.045)
        return "verified"

    result, lease = syncer_module._run_non_authoritative_substage(
        slow_read_only_work,
        substage="strict_replay",
        lease_manager="manager",
        loaded_lease=initial,
        config=config,
        logger=logger,
    )
    assert result == "verified"
    assert lease is renewals[-1][1]
    assert len(renewals) >= 3
    assert any(event == "transaction_substage_heartbeat" for event, _ in logger.events)


def test_authoritative_cas_has_a_final_renew_and_lease_loss_cannot_publish_stop():
    source = inspect.getsource(syncer_module.run_syncer)
    prepare = source.index('substage="successor_prepare"')
    final_renew = source.index("loaded_lease = _renew_owner_lease(", prepare)
    cas = source.index("log.commit_prepared(prepared)", final_renew)
    assert prepare < final_renew < cas
    assert 'substage="post_cas_replay"' in source[cas:]
    assert "if not lease_authority_lost and view.authoritative_stop is None" in source

    stop_source = inspect.getsource(syncer_module._commit_stop_with_lease_guard)
    stop_prepare = stop_source.index('substage="stop_prepare"')
    stop_renew = stop_source.index("loaded_lease = _renew_owner_lease(", stop_prepare)
    stop_cas = stop_source.index("log.commit_prepared(prepared)", stop_renew)
    assert stop_prepare < stop_renew < stop_cas
    assert 'substage="stop_post_cas_replay"' in stop_source[stop_cas:]


def test_guarded_stop_heartbeats_prepare_then_renews_before_cas(monkeypatch):
    timeline = []

    def lease(sequence):
        return SimpleNamespace(
            record=SimpleNamespace(
                lease_sequence=sequence,
                owner_token=SimpleNamespace(owner_id="owner", fencing_epoch=1),
            )
        )

    def fake_renew(**_kwargs):
        renewed = lease(2 + sum(item == "renew" for item in timeline))
        timeline.append("renew")
        return renewed

    before = SimpleNamespace(commit_id="before", commit_seq=7)
    stopped = SimpleNamespace(
        commit_id="after",
        commit_seq=8,
        authoritative_stop=SimpleNamespace(reason="completed"),
    )

    class Log:
        def prepare_control_transition(self, **_kwargs):
            time.sleep(0.045)
            timeline.append("prepared")
            return "prepared-stop"

        def commit_prepared(self, prepared):
            assert prepared == "prepared-stop"
            timeline.append("cas")
            return SimpleNamespace(commit_id="after", commit_seq=8)

    monkeypatch.setattr(syncer_module, "_renew_owner_lease", fake_renew)
    monkeypatch.setattr(syncer_module, "build_runtime_view", lambda _log: stopped)
    config = SimpleNamespace(
        coordination=SimpleNamespace(renew_interval_seconds=0.01)
    )
    result, final_lease = syncer_module._commit_stop_with_lease_guard(
        log=Log(),
        view=before,
        reason="completed",
        request_id="stop",
        lease_manager="manager",
        loaded_lease=lease(1),
        config=config,
        logger=_Logger(),
    )
    assert result is stopped
    assert final_lease.record.lease_sequence >= 2
    assert timeline.count("renew") >= 4
    assert timeline.index("prepared") < max(
        index for index, event in enumerate(timeline) if event == "renew"
    ) < timeline.index("cas")
