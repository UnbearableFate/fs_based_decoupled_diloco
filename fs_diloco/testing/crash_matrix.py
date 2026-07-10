"""Reference crash-point enumeration."""

from __future__ import annotations

from fs_diloco.log.model import ReferenceProposal, SystemState
from fs_diloco.testing.reference_simulator import CRASH_POINTS, AttemptResult, ReferenceSimulator


def enumerate_single_commit_crashes() -> tuple[AttemptResult, ...]:
    results = []
    for crash_point in CRASH_POINTS:
        state = SystemState.genesis()
        proposal = ReferenceProposal.create(
            learner_id="learner-000",
            session_id="session-000",
            sequence=0,
            fragment_id=0,
            base_commit_id="genesis",
            base_commit_seq=0,
            base_fragment_version=0,
            target_tokens=10,
            values=(1.0, -1.0),
        )
        simulator = ReferenceSimulator(state)
        simulator.publish(proposal)
        results.append(
            simulator.attempt_commit(
                fragment_id=0,
                selected_proposal_ids=(proposal.proposal_id,),
                crash_at=crash_point,
            )
        )
    return tuple(results)
