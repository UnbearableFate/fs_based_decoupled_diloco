from __future__ import annotations

import os

import pytest

from fs_diloco.log.model import ReferenceProposal
from fs_diloco.testing.model_checker import run_seeded_traces
from fs_diloco.testing.trace import Trace, TraceEvent, generate_trace, minimize_failure, replay_trace


def test_quick_suite_covers_one_thousand_seeded_traces():
    report = run_seeded_traces(count=1000, steps=10)
    assert report["count"] == 1000
    assert report["unique_state_digests"] > 1
    assert len(report["suite_digest"]) == 64
    assert report["action_counts"]["invalid_unknown_selection"] > 0


@pytest.mark.skipif(os.environ.get("DURALOCO_NIGHTLY") != "1", reason="explicit nightly suite")
def test_nightly_suite_covers_ten_thousand_traces():
    assert run_seeded_traces(count=10_000, steps=12)["count"] == 10_000


def test_trace_replay_digest_is_stable():
    trace = generate_trace(20260710, steps=30)
    assert replay_trace(trace).state_digest() == replay_trace(trace).state_digest()


def test_trace_commit_uses_oldest_first_quorum_policy_not_proposal_id_order():
    older = ReferenceProposal.create(
        learner_id="learner-000",
        session_id="session-000",
        sequence=0,
        fragment_id=0,
        base_commit_id="genesis",
        base_commit_seq=0,
        base_fragment_version=0,
        target_tokens=10,
        values=(1.0, 0.0),
    )
    newer = next(
        candidate
        for index in range(2, 1000)
        if (
            candidate := ReferenceProposal.create(
                learner_id="learner-000",
                session_id="session-000",
                sequence=1,
                fragment_id=0,
                base_commit_id="genesis",
                base_commit_seq=0,
                base_fragment_version=0,
                target_tokens=10,
                values=(float(index), 0.0),
            )
        ).proposal_id
        < older.proposal_id
    )
    trace = Trace(
        seed=4242,
        events=(
            TraceEvent(
                action="publish",
                learner=0,
                fragment=0,
                sequence=older.sequence,
                tokens=older.target_tokens,
                value_hex=tuple(value.hex() for value in older.values),
            ),
            TraceEvent(
                action="publish",
                learner=0,
                fragment=0,
                sequence=newer.sequence,
                tokens=newer.target_tokens,
                value_hex=tuple(value.hex() for value in newer.values),
            ),
            TraceEvent(action="commit", fragment=0),
        ),
    )

    replayed = replay_trace(trace)

    assert replayed.commits[0].selected_proposal_ids == (older.proposal_id,)
    assert newer.proposal_id not in replayed.consumed_proposal_ids
    assert newer.proposal_id not in replayed.dropped_proposal_ids


def test_failure_minimizer_removes_irrelevant_events():
    trace = Trace(
        seed=1,
        events=(
            TraceEvent("restart"),
            TraceEvent("restart"),
            TraceEvent("publish", value_hex=(0.0.hex(), 1.0.hex())),
        ),
    )
    minimized = minimize_failure(trace, lambda candidate: any(e.action == "publish" for e in candidate.events))
    assert len(minimized.events) == 1
    assert minimized.events[0].action == "publish"


def test_replay_failure_is_reproducible_and_minimized_to_the_causal_event():
    trace = Trace(
        seed=7,
        events=(
            TraceEvent("restart"),
            TraceEvent("unknown_action"),
            TraceEvent("restart"),
        ),
    )

    def fails(candidate: Trace) -> bool:
        try:
            replay_trace(candidate)
        except ValueError as exc:
            return "unknown trace action" in str(exc)
        return False

    assert fails(trace) and fails(trace)
    minimized = minimize_failure(trace, fails)
    assert minimized.events == (TraceEvent("unknown_action"),)
    assert fails(minimized)
