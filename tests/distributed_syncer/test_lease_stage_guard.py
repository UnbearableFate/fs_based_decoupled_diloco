from __future__ import annotations

import inspect

import pytest

import fs_diloco.distributed_syncer.committer as committer_module


class _Logger:
    def __init__(self):
        self.events = []

    def event(self, event_type, **fields):
        self.events.append((event_type, fields))


def test_authoritative_stage_guard_renews_and_records_stage(monkeypatch):
    renewed = object()
    calls = []

    def fake_renew(**kwargs):
        calls.append(kwargs)
        return renewed

    monkeypatch.setattr(committer_module, "_renew_owner_lease", fake_renew)
    logger = _Logger()
    result = committer_module._renew_for_authoritative_stage(
        lease_manager="manager",
        loaded_lease="lease",
        config="config",
        logger=logger,
        stage="membership_transition",
    )
    assert result is renewed
    assert calls == [
        {
            "lease_manager": "manager",
            "loaded_lease": "lease",
            "config": "config",
            "logger": logger,
        }
    ]
    assert logger.events == [
        ("lease_stage_guard", {"stage": "membership_transition"})
    ]
    with pytest.raises(ValueError, match="unknown"):
        committer_module._renew_for_authoritative_stage(
            lease_manager=None,
            loaded_lease=None,
            config=None,
            logger=logger,
            stage="unbounded_stage",
        )


def test_committer_guards_takeover_reconfiguration_and_dispatch():
    source = inspect.getsource(committer_module.run_committer)
    for stage in ("post_activation", "membership_transition", "work_dispatch"):
        assert f'stage="{stage}"' in source
    assert source.index('stage="membership_transition"') < source.index(
        "log.commit_membership("
    )
    assert source.index('stage="work_dispatch"') < source.index(
        "publish_work_order("
    )
