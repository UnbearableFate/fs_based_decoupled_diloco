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
