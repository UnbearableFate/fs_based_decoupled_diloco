"""Deterministic trace grammar, generation, replay, and failure minimization."""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Callable

from fs_diloco.log.model import (
    ReferenceProposal,
    SystemState,
    TransitionError,
    assert_invariants,
    prepare_transition,
)
from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.testing.reference_simulator import (
    CRASH_POINTS,
    DECISION_CRASH_POINTS,
    PUBLICATION_CRASH_POINTS,
    ReferenceSimulator,
)


@dataclass(frozen=True)
class TraceEvent:
    action: str
    learner: int = 0
    fragment: int = 0
    sequence: int = 0
    tokens: int = 1
    value_hex: tuple[str, ...] = ()
    crash_point: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "learner": self.learner,
            "fragment": self.fragment,
            "sequence": self.sequence,
            "tokens": self.tokens,
            "value_hex": list(self.value_hex),
            "crash_point": self.crash_point,
        }


@dataclass(frozen=True)
class Trace:
    seed: int
    events: tuple[TraceEvent, ...]

    @property
    def digest(self) -> str:
        return canonical_digest(
            {"seed": self.seed, "events": [event.to_dict() for event in self.events]}
        )


def generate_trace(seed: int, *, steps: int = 12, fragments: int = 2) -> Trace:
    rng = random.Random(seed)
    events: list[TraceEvent] = []
    publish_sequence = 0
    for index in range(steps):
        choice = rng.random()
        if index == 0 or choice < 0.58:
            fragment = rng.randrange(fragments)
            values = tuple(
                rng.uniform(-1.0, 1.0).hex()
                for _ in range(2)
            )
            events.append(
                TraceEvent(
                    action="publish",
                    learner=publish_sequence % 4,
                    fragment=fragment,
                    sequence=publish_sequence,
                    tokens=rng.randint(1, 100),
                    value_hex=values,
                    crash_point=(
                        rng.choice(PUBLICATION_CRASH_POINTS)
                        if rng.random() < 0.08
                        else None
                    ),
                )
            )
            publish_sequence += 1
        elif choice < 0.66:
            events.append(
                TraceEvent(
                    action="invalid_unknown_selection",
                    fragment=rng.randrange(fragments),
                )
            )
        elif choice < 0.76:
            crash_point = (
                rng.choice((None, *DECISION_CRASH_POINTS))
                if rng.random() < 0.45
                else None
            )
            events.append(TraceEvent(action="decide", crash_point=crash_point))
        else:
            crash_point = rng.choice((None, *CRASH_POINTS)) if rng.random() < 0.45 else None
            events.append(
                TraceEvent(
                    action="commit",
                    fragment=rng.randrange(fragments),
                    crash_point=crash_point,
                )
            )
        if rng.random() < 0.12:
            events.append(TraceEvent(action="restart"))
    return Trace(seed=seed, events=tuple(events))


def replay_trace(trace: Trace) -> SystemState:
    simulator = ReferenceSimulator(SystemState.genesis(fragment_count=2, vector_size=2))
    for event in trace.events:
        if event.action == "publish":
            current = simulator.durable_state
            fragment = current.fragments[event.fragment]
            proposal = ReferenceProposal.create(
                learner_id=f"learner-{event.learner:03d}",
                session_id=f"session-{event.learner:03d}",
                sequence=event.sequence,
                fragment_id=event.fragment,
                base_commit_id=current.head_commit_id,
                base_commit_seq=current.head_commit_seq,
                base_fragment_version=fragment.version,
                target_tokens=event.tokens,
                values=tuple(float.fromhex(value) for value in event.value_hex),
            )
            simulator.attempt_publish(proposal, crash_at=event.crash_point)
        elif event.action == "commit":
            state = simulator.durable_state
            eligible = sorted(
                proposal.proposal_id
                for proposal in state.proposals.values()
                if proposal.fragment_id == event.fragment and state.eligible(proposal)
            )
            if eligible:
                simulator.attempt_commit(
                    fragment_id=event.fragment,
                    selected_proposal_ids=(eligible[0],),
                    crash_at=event.crash_point,
                )
        elif event.action == "restart":
            simulator.restart()
        elif event.action == "decide":
            state = simulator.durable_state
            candidates = sorted(
                proposal.proposal_id
                for proposal in state.proposals.values()
                if state.eligible(proposal)
            )
            if candidates:
                simulator.attempt_decision(
                    proposal_id=candidates[0],
                    decision="superseded",
                    reason="seeded_trace_policy",
                    crash_at=event.crash_point,
                )
        elif event.action == "invalid_unknown_selection":
            before = simulator.durable_state.state_digest()
            try:
                prepare_transition(
                    simulator.durable_state,
                    fragment_id=event.fragment,
                    selected_proposal_ids=("missing-proposal",),
                )
            except TransitionError:
                pass
            else:  # pragma: no cover - deliberate negative oracle
                raise AssertionError("unknown proposal selection unexpectedly succeeded")
            if simulator.durable_state.state_digest() != before:
                raise AssertionError("rejected transition mutated durable state")
        else:
            raise ValueError(f"unknown trace action: {event.action}")
        assert_invariants(simulator.durable_state)
    return simulator.durable_state


def minimize_failure(trace: Trace, fails: Callable[[Trace], bool]) -> Trace:
    """Greedily remove events while preserving a caller-defined failure."""
    events = list(trace.events)
    changed = True
    while changed and len(events) > 1:
        changed = False
        for index in range(len(events)):
            candidate = Trace(trace.seed, tuple(events[:index] + events[index + 1 :]))
            if fails(candidate):
                events = list(candidate.events)
                changed = True
                break
    return Trace(trace.seed, tuple(events))
