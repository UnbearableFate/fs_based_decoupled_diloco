from __future__ import annotations

import pytest
import torch

from fs_diloco.optimizer.streaming_reduce import reduce_fragment_streaming
from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.syncer_core.aggregation import reduce_fragment
from fs_diloco.syncer_core.types import FragmentPlan


def _plan(quorum: int) -> FragmentPlan:
    ids = tuple(f"proposal-{index}" for index in range(quorum))
    return FragmentPlan(
        fragment_id=0,
        parent_commit_id="parent",
        parent_commit_seq=0,
        parent_frontier_digest="a" * 64,
        selected_proposal_ids=ids,
        payload_sha256=tuple(f"{index:064x}" for index in range(quorum)),
        weights_hex=tuple(float(1 / quorum).hex() for _ in ids),
        aggregate_digest=canonical_digest({"quorum": quorum}),
        selection_digest=canonical_digest({"ids": list(ids)}),
    )


def test_streaming_reducer_is_exact_and_peak_does_not_scale_with_quorum():
    numel = 4096
    current = torch.zeros(numel, dtype=torch.float32)
    peaks = []
    for quorum in (1, 2, 4, 8):
        plan = _plan(quorum)
        proposals = {
            proposal_id: torch.full((numel,), index + 1.0)
            for index, proposal_id in enumerate(plan.selected_proposal_ids)
        }
        loaded = []

        def load(proposal_id, *, observed=loaded, inputs=proposals):
            observed.append(proposal_id)
            return inputs[proposal_id]

        actual, stats = reduce_fragment_streaming(
            plan=plan,
            load_proposal=load,
            current_params=current,
            max_inflight_bytes=numel * 4,
        )
        expected = reduce_fragment(
            plan=plan,
            proposal_tensors=proposals,
            current_params=current,
        )
        assert torch.equal(actual, expected)
        assert loaded == list(plan.selected_proposal_ids)
        assert stats.load_count == quorum
        assert stats.finite_check_count == quorum
        peaks.append(stats.peak_working_bytes)
    assert len(set(peaks)) == 1
    assert peaks[0] == numel * 4 * 2


def test_streaming_reducer_fails_closed_on_budget_and_nonfinite_payload():
    plan = _plan(1)
    current = torch.zeros(8)
    with pytest.raises(MemoryError, match="in-flight"):
        reduce_fragment_streaming(
            plan=plan,
            load_proposal=lambda _proposal_id: torch.ones(8),
            current_params=current,
            max_inflight_bytes=4,
        )
    with pytest.raises(ValueError, match="not finite"):
        reduce_fragment_streaming(
            plan=plan,
            load_proposal=lambda _proposal_id: torch.tensor(
                [float("nan"), *([0.0] * 7)]
            ),
            current_params=current,
        )
