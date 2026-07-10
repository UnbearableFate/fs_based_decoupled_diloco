"""Crash-enumerable reference transition simulator."""

from __future__ import annotations

from dataclasses import dataclass

from fs_diloco.log.model import (
    PreparedTransition,
    ReferenceProposal,
    SystemState,
    assert_invariants,
    commit_prepared,
    decide_proposal,
    prepare_transition,
)


CRASH_POINTS = (
    "before_params_put",
    "after_params_put",
    "before_outer_state_put",
    "after_outer_state_put",
    "before_commit_record_put",
    "after_commit_record_put",
    "before_frontier_put",
    "after_frontier_put",
    "before_head_cas",
    "after_head_cas",
)
PUBLICATION_CRASH_POINTS = ("before_publish", "after_publish")
DECISION_CRASH_POINTS = (
    "before_decision_record_put",
    "after_decision_record_put",
    "before_decision_head_cas",
    "after_decision_head_cas",
)


@dataclass(frozen=True)
class AttemptResult:
    outcome: str
    crash_point: str | None
    old_digest: str
    recovered_digest: str
    new_digest: str
    orphan_objects: int
    prepared: PreparedTransition


@dataclass(frozen=True)
class DecisionAttemptResult:
    outcome: str
    crash_point: str | None
    old_digest: str
    recovered_digest: str
    new_digest: str
    orphan_objects: int


class ReferenceSimulator:
    def __init__(self, state: SystemState | None = None) -> None:
        self.state = state or SystemState.genesis()
        self.durable_state = self.state
        self.orphan_objects = 0

    def publish(self, proposal: ReferenceProposal) -> None:
        self.state = self.state.publish(proposal)
        self.durable_state = self.durable_state.publish(proposal)

    def attempt_publish(self, proposal: ReferenceProposal, *, crash_at: str | None = None) -> str:
        if crash_at not in {None, *PUBLICATION_CRASH_POINTS}:
            raise ValueError(f"unknown publication crash point: {crash_at}")
        if crash_at == "before_publish":
            self.state = self.durable_state
            return "crashed_before_publish"
        self.publish(proposal)
        if crash_at == "after_publish":
            self.state = self.durable_state
            return "crashed_after_publish"
        return "published"

    def attempt_commit(
        self,
        *,
        fragment_id: int,
        selected_proposal_ids: tuple[str, ...],
        crash_at: str | None = None,
    ) -> AttemptResult:
        if crash_at is not None and crash_at not in CRASH_POINTS:
            raise ValueError(f"unknown crash point: {crash_at}")
        old = self.durable_state
        prepared = prepare_transition(
            old,
            fragment_id=fragment_id,
            selected_proposal_ids=selected_proposal_ids,
        )
        new = commit_prepared(old, prepared)
        effects = (
            ("params_put", 1),
            ("outer_state_put", 1),
            ("commit_record_put", 1),
            ("frontier_put", 1),
            ("head_cas", 0),
        )
        completed_objects = 0
        for effect, object_count in effects:
            if crash_at == f"before_{effect}":
                self.orphan_objects += completed_objects
                self.state = self.durable_state
                return self._result("crashed_old_prefix", crash_at, old, new, prepared)
            completed_objects += object_count
            if effect == "head_cas":
                self.durable_state = new
                self.state = new
            if crash_at == f"after_{effect}":
                if effect != "head_cas":
                    self.orphan_objects += completed_objects
                    self.state = self.durable_state
                    return self._result("crashed_old_prefix", crash_at, old, new, prepared)
                return self._result("crashed_new_prefix", crash_at, old, new, prepared)
        return self._result("committed", None, old, new, prepared)

    def attempt_decision(
        self,
        *,
        proposal_id: str,
        decision: str,
        reason: str,
        crash_at: str | None = None,
    ) -> DecisionAttemptResult:
        if crash_at is not None and crash_at not in DECISION_CRASH_POINTS:
            raise ValueError(f"unknown decision crash point: {crash_at}")
        old = self.durable_state
        new = decide_proposal(
            old,
            proposal_id=proposal_id,
            decision=decision,
            reason=reason,
        )
        if crash_at == "before_decision_record_put":
            self.state = old
            return self._decision_result("crashed_old_prefix", crash_at, old, new)
        if crash_at in {"after_decision_record_put", "before_decision_head_cas"}:
            self.orphan_objects += 1
            self.state = old
            return self._decision_result("crashed_old_prefix", crash_at, old, new)
        self.durable_state = new
        self.state = new
        if crash_at == "after_decision_head_cas":
            return self._decision_result("crashed_new_prefix", crash_at, old, new)
        return self._decision_result("committed", None, old, new)

    def _decision_result(
        self,
        outcome: str,
        crash_point: str | None,
        old: SystemState,
        new: SystemState,
    ) -> DecisionAttemptResult:
        return DecisionAttemptResult(
            outcome=outcome,
            crash_point=crash_point,
            old_digest=old.state_digest(),
            recovered_digest=self.durable_state.state_digest(),
            new_digest=new.state_digest(),
            orphan_objects=self.orphan_objects,
        )

    def _result(
        self,
        outcome: str,
        crash_point: str | None,
        old: SystemState,
        new: SystemState,
        prepared: PreparedTransition,
    ) -> AttemptResult:
        return AttemptResult(
            outcome=outcome,
            crash_point=crash_point,
            old_digest=old.state_digest(),
            recovered_digest=self.durable_state.state_digest(),
            new_digest=new.state_digest(),
            orphan_objects=self.orphan_objects,
            prepared=prepared,
        )

    def restart(self) -> SystemState:
        self.state = self.durable_state
        assert_invariants(self.state)
        return self.state
