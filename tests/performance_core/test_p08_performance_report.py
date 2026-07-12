import pytest

from scripts.agent.create_p08_performance_report import (
    _distributed_lease_guard,
    _validate_r2_attempt_lineage,
)


def test_r2_lineage_counts_failed_attempt_without_prepared_result():
    assert _validate_r2_attempt_lineage(
        transition_count=10,
        prepared_attempt_count=19,
        timeline_attempt_counts=[2] * 10,
        terminal_loser_count=1,
    ) == {
        "total_attempts": 20,
        "successful_prepared_attempts": 19,
        "terminal_loser_attempts": 1,
    }


@pytest.mark.parametrize(
    ("prepared", "attempt_counts", "losers"),
    [
        (10, [2] * 10, 1),
        (19, [1] + [2] * 9, 1),
        (19, [2] * 10, 0),
    ],
)
def test_r2_lineage_rejects_factor_one_or_incomplete_evidence(
    prepared, attempt_counts, losers
):
    with pytest.raises(AssertionError):
        _validate_r2_attempt_lineage(
            transition_count=10,
            prepared_attempt_count=prepared,
            timeline_attempt_counts=attempt_counts,
            terminal_loser_count=losers,
        )


def test_lease_guard_accepts_fast_substages_without_fabricated_heartbeats(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    events = [
        *[
            {"event_type": "lease_stage_guard", "stage": "optimizer_head_cas"}
            for _ in range(10)
        ],
        {"event_type": "lease_stage_guard", "stage": "stop_head_cas"},
        {
            "event_type": "lease_stage_guard",
            "stage": "lifecycle_substage_heartbeat",
        },
        {
            "event_type": "lifecycle_substage_heartbeat",
            "substage": "strict_replay",
        },
    ]
    path = log_dir / "distributed_committer.jsonl"
    path.write_text("".join(f"{__import__('json').dumps(item)}\n" for item in events))

    report = _distributed_lease_guard(tmp_path)

    assert report["lifecycle_substage_renewals"] == 1
    assert report["successor_prepare_heartbeats"] == 0
    assert report["stop_prepare_heartbeats"] == 0
