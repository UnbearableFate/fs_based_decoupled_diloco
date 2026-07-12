from __future__ import annotations

import pytest

from fs_diloco.fragment_scheduler import select_fragment
from fs_diloco.learner import _record_fragment_training_step, write_fragment_update
from fs_diloco.learner_protocol import (
    AuthorityFrontier,
    ContributionInterval,
    DataCursor,
    LearnerSession,
    RngCursor,
)


def _interval(sequence: int, fragment_id: int) -> ContributionInterval:
    session = LearnerSession.new(
        "multi-fragment-run",
        4,
        "learner_000",
        session_id="multi-fragment-session",
    )
    return ContributionInterval.start(
        session=session,
        sequence=sequence,
        fragment_id=fragment_id,
        base=AuthorityFrontier(
            commit_id="genesis",
            commit_seq=0,
            frontier_sha256="a" * 64,
            fragment_versions={0: 0, 1: 0, 2: 0},
            fencing_epoch=0,
            owner_id=None,
            owner_session_id=None,
        ),
        start_step=sequence - 1,
        start_cursor=DataCursor(sequence - 1, 0),
        rng_cursor=RngCursor(7, sequence - 1),
        transport_dtype="bfloat16",
    )


def test_fragment_learner_round_robin_preserves_interval_fragment_metadata():
    tokens_since_fragment_load = {0: 0, 1: 0, 2: 0}
    observed = []
    for update_index in range(6):
        selected_fragment = select_fragment(update_index, 3, schedule="round_robin_global")
        interval = _record_fragment_training_step(
            _interval(update_index + 1, selected_fragment),
            tokens_since_fragment_load,
            tokens=11,
            examples=1,
        ).close(end_cursor=DataCursor(update_index + 1, 0))
        observed.append(interval.fragment_id)
        assert interval.fragment_id == selected_fragment

    assert observed == [0, 1, 2, 0, 1, 2]
    assert tokens_since_fragment_load == {0: 66, 1: 66, 2: 66}

    with pytest.raises(ValueError, match="metadata must match"):
        write_fragment_update(
            paths=None,
            config=None,
            learner_id="learner_000",
            interval=_interval(1, 0),
            fragment_id=1,
            base_fragment_version=0,
            base_global_merge_event=0,
            base_commit_id="genesis",
            base_commit_seq=0,
            base_frontier_digest="a" * 64,
            interval_start_step=0,
            local_step=1,
            inner_steps=1,
            tokens_this_update=1,
            tokens_since_fragment_load=1,
            num_examples=1,
            train_loss=1.0,
            grad_norm=None,
            param_norm=1.0,
            fragment_norm=1.0,
            fragment_tensor=None,
        )
