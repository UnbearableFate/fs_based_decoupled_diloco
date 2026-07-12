from __future__ import annotations

import inspect
from types import SimpleNamespace
import time

import pytest

import fs_diloco.distributed_syncer.committer as committer_module
from fs_diloco.log import CommitConflict


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


def test_long_lifecycle_substage_renews_until_worker_finishes(monkeypatch):
    renewals = []

    def fake_renew(**kwargs):
        renewed = f"lease-{len(renewals) + 1}"
        renewals.append((kwargs["loaded_lease"], renewed))
        return renewed

    monkeypatch.setattr(committer_module, "_renew_owner_lease", fake_renew)
    logger = _Logger()
    config = SimpleNamespace(
        coordination=SimpleNamespace(renew_interval_seconds=0.01)
    )

    def slow_read():
        time.sleep(0.045)
        return "verified"

    result, lease = committer_module._run_lifecycle_substage(
        slow_read,
        substage="strict_replay",
        lease_manager="manager",
        loaded_lease="lease-0",
        config=config,
        logger=logger,
    )

    assert result == "verified"
    assert lease == renewals[-1][1]
    assert len(renewals) >= 3
    assert any(event == "lifecycle_substage_heartbeat" for event, _ in logger.events)


def test_committer_conflict_finalization_publishes_only_authoritative_stop(monkeypatch):
    logger = _Logger()
    initial = SimpleNamespace(authoritative_stop=None, commit_seq=7, commit_id="c-before")
    stopped = SimpleNamespace(
        authoritative_stop=SimpleNamespace(reason="takeover"),
        commit_seq=8,
        commit_id="c-after",
    )

    class Log:
        def commit_stop(self, **_kwargs):
            raise CommitConflict("stale owner")

    published = []
    monkeypatch.setattr(committer_module, "build_runtime_view", lambda *_args, **_kwargs: stopped)
    monkeypatch.setattr(
        committer_module,
        "_publish_stop",
        lambda paths, **kwargs: published.append((paths, kwargs)),
    )
    result = committer_module._finalize_committer_stop(
        log=Log(),
        view=initial,
        paths="paths",
        config="config",
        reason="error",
        member_id="member-0",
        owner_session_id="session-0",
        logger=logger,
    )
    assert result is stopped
    assert published[0][1]["reason"] == "takeover"

    published.clear()
    monkeypatch.setattr(committer_module, "build_runtime_view", lambda *_args, **_kwargs: initial)
    result = committer_module._finalize_committer_stop(
        log=Log(),
        view=initial,
        paths="paths",
        config="config",
        reason="error",
        member_id="member-0",
        owner_session_id="session-0",
        logger=logger,
    )
    assert result is initial
    assert published == []
    assert any(event == "stop_not_published_without_authority" for event, _ in logger.events)


def test_committer_finalization_never_masks_active_error(monkeypatch):
    logger = _Logger()
    view = object()

    def fail(**_kwargs):
        raise RuntimeError("cleanup failure")

    monkeypatch.setattr(committer_module, "_finalize_committer_stop", fail)
    assert (
        committer_module._finalize_committer_without_masking(
            primary_error=True,
            logger=logger,
            view=view,
            reason="error",
        )
        is view
    )
    with pytest.raises(RuntimeError, match="cleanup failure"):
        committer_module._finalize_committer_without_masking(
            primary_error=False,
            logger=logger,
            view=view,
            reason="completed",
        )


def test_committer_crash_marks_error_before_finalization():
    source = inspect.getsource(committer_module.run_committer)
    exception_offset = source.index("except Exception:")
    finally_offset = source.index("finally:", exception_offset)
    assert 'stop_reason = "error"' in source[exception_offset:finally_offset]
    assert "raise" in source[exception_offset:finally_offset]


def test_committer_prepare_conflict_forces_strict_replay_and_result_wait_renews():
    source = inspect.getsource(committer_module.run_committer)
    assert "except (CommitConflict, InjectedTimeout)" in source
    assert "build_runtime_view(log, force_full=True)" in source
    assert 'substage="executor_result_wait"' in source
