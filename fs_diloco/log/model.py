"""Pure immutable transition system used as the DuraLoCo reference oracle."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from types import MappingProxyType
from typing import Iterable, Mapping

from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.testing.deterministic_reference import (
    ReferenceOptimizerConfig,
    ReferenceOptimizerState,
    ReferenceWeightingConfig,
    Vector,
    initial_state,
    normalized_weights,
    optimizer_state_digest,
    outer_step,
    vector_identity,
    weighted_reduce,
)


class TransitionError(RuntimeError):
    pass


class TransitionConflict(TransitionError):
    pass


@dataclass(frozen=True)
class ReferenceProtocolConfig:
    max_global_staleness: int = 64
    max_fragment_staleness: int = 4

    def __post_init__(self) -> None:
        if type(self.max_global_staleness) is not int or self.max_global_staleness < 0:
            raise ValueError("max_global_staleness must be a non-negative integer")
        if type(self.max_fragment_staleness) is not int or self.max_fragment_staleness < 0:
            raise ValueError("max_fragment_staleness must be a non-negative integer")

    def identity(self) -> dict[str, int]:
        return {
            "max_global_staleness": self.max_global_staleness,
            "max_fragment_staleness": self.max_fragment_staleness,
        }


@dataclass(frozen=True)
class ReferenceProposal:
    proposal_id: str
    learner_id: str
    session_id: str
    sequence: int
    fragment_id: int
    base_commit_id: str
    base_commit_seq: int
    base_fragment_version: int
    target_tokens: int
    values: Vector

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", tuple(self.values))

    @classmethod
    def create(
        cls,
        *,
        learner_id: str,
        session_id: str,
        sequence: int,
        fragment_id: int,
        base_commit_id: str,
        base_commit_seq: int,
        base_fragment_version: int,
        target_tokens: int,
        values: Iterable[float],
    ) -> "ReferenceProposal":
        for value, field_name in (
            (learner_id, "learner_id"),
            (session_id, "session_id"),
            (base_commit_id, "base_commit_id"),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        for value, field_name, minimum in (
            (sequence, "sequence", 0),
            (fragment_id, "fragment_id", 0),
            (base_commit_seq, "base_commit_seq", 0),
            (base_fragment_version, "base_fragment_version", 0),
            (target_tokens, "target_tokens", 1),
        ):
            if type(value) is not int or value < minimum:
                raise ValueError(f"{field_name} must be an integer >= {minimum}")
        values_tuple = tuple(float(value) for value in values)
        if not values_tuple:
            raise ValueError("proposal values must be non-empty")
        body = {
            "learner_id": learner_id,
            "session_id": session_id,
            "sequence": sequence,
            "fragment_id": fragment_id,
            "base_commit_id": base_commit_id,
            "base_commit_seq": base_commit_seq,
            "base_fragment_version": base_fragment_version,
            "target_tokens": target_tokens,
            "values": vector_identity(values_tuple),
        }
        return cls(
            proposal_id="rp-" + canonical_digest(body),
            learner_id=learner_id,
            session_id=session_id,
            sequence=sequence,
            fragment_id=fragment_id,
            base_commit_id=base_commit_id,
            base_commit_seq=base_commit_seq,
            base_fragment_version=base_fragment_version,
            target_tokens=target_tokens,
            values=values_tuple,
        )

    def identity(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "learner_id": self.learner_id,
            "session_id": self.session_id,
            "sequence": self.sequence,
            "fragment_id": self.fragment_id,
            "base_commit_id": self.base_commit_id,
            "base_commit_seq": self.base_commit_seq,
            "base_fragment_version": self.base_fragment_version,
            "target_tokens": self.target_tokens,
            "values": vector_identity(self.values),
        }


@dataclass(frozen=True)
class FragmentState:
    version: int
    params: Vector
    outer_state: ReferenceOptimizerState
    params_commit_id: str
    outer_state_commit_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", tuple(self.params))

    def identity(self) -> dict[str, object]:
        return {
            "version": self.version,
            "params": vector_identity(self.params),
            "outer_state": self.outer_state.identity(),
            "params_commit_id": self.params_commit_id,
            "outer_state_commit_id": self.outer_state_commit_id,
        }


@dataclass(frozen=True)
class CommitEvent:
    commit_seq: int
    commit_id: str
    parent_commit_id: str
    fragment_id: int
    previous_fragment_version: int
    new_fragment_version: int
    selected_proposal_ids: tuple[str, ...]
    weights_hex: tuple[tuple[str, str], ...]
    new_params: Vector
    new_outer_state: ReferenceOptimizerState
    transition_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "selected_proposal_ids", tuple(self.selected_proposal_ids))
        object.__setattr__(self, "weights_hex", tuple(tuple(item) for item in self.weights_hex))
        object.__setattr__(self, "new_params", tuple(self.new_params))

    def identity_body(self) -> dict[str, object]:
        return {
            "commit_seq": self.commit_seq,
            "parent_commit_id": self.parent_commit_id,
            "fragment_id": self.fragment_id,
            "previous_fragment_version": self.previous_fragment_version,
            "new_fragment_version": self.new_fragment_version,
            "selected_proposal_ids": list(self.selected_proposal_ids),
            "weights_hex": [list(item) for item in self.weights_hex],
            "new_params": vector_identity(self.new_params),
            "new_outer_state": self.new_outer_state.identity(),
            "transition_digest": self.transition_digest,
        }


@dataclass(frozen=True)
class DecisionEvent:
    commit_seq: int
    commit_id: str
    parent_commit_id: str
    proposal_id: str
    decision: str
    reason: str

    def identity_body(self) -> dict[str, object]:
        return {
            "event_type": "proposal_decision",
            "commit_seq": self.commit_seq,
            "parent_commit_id": self.parent_commit_id,
            "proposal_id": self.proposal_id,
            "decision": self.decision,
            "reason": self.reason,
        }


LogEvent = CommitEvent | DecisionEvent


@dataclass(frozen=True)
class PreparedTransition:
    parent_commit_id: str
    parent_commit_seq: int
    fragment_id: int
    selected_proposal_ids: tuple[str, ...]
    event: CommitEvent

    def __post_init__(self) -> None:
        object.__setattr__(self, "selected_proposal_ids", tuple(self.selected_proposal_ids))


@dataclass(frozen=True)
class ProposalDecision:
    proposal_id: str
    decision: str
    reason: str
    decided_at_commit_seq: int

    def identity(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "decision": self.decision,
            "reason": self.reason,
            "decided_at_commit_seq": self.decided_at_commit_seq,
        }


@dataclass(frozen=True)
class SystemState:
    run_id: str
    run_generation: int
    optimizer_config: ReferenceOptimizerConfig
    weighting_config: ReferenceWeightingConfig
    protocol_config: ReferenceProtocolConfig
    head_commit_id: str
    head_commit_seq: int
    genesis_fragments: Mapping[int, FragmentState]
    fragments: Mapping[int, FragmentState]
    proposals: Mapping[str, ReferenceProposal]
    consumed_proposal_ids: frozenset[str]
    dropped_proposal_ids: frozenset[str]
    proposal_decisions: Mapping[str, ProposalDecision]
    commits: tuple[LogEvent, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "genesis_fragments",
            MappingProxyType(dict(self.genesis_fragments)),
        )
        object.__setattr__(self, "fragments", MappingProxyType(dict(self.fragments)))
        object.__setattr__(self, "proposals", MappingProxyType(dict(self.proposals)))
        object.__setattr__(
            self,
            "proposal_decisions",
            MappingProxyType(dict(self.proposal_decisions)),
        )
        object.__setattr__(self, "consumed_proposal_ids", frozenset(self.consumed_proposal_ids))
        object.__setattr__(self, "dropped_proposal_ids", frozenset(self.dropped_proposal_ids))
        object.__setattr__(self, "commits", tuple(self.commits))

    @classmethod
    def genesis(
        cls,
        *,
        fragment_count: int = 1,
        vector_size: int = 2,
        initial_value: float = 0.0,
        optimizer_config: ReferenceOptimizerConfig | None = None,
        weighting_config: ReferenceWeightingConfig | None = None,
        protocol_config: ReferenceProtocolConfig | None = None,
        run_id: str = "reference-run",
    ) -> "SystemState":
        if fragment_count < 1:
            raise ValueError("fragment_count must be positive")
        if not isinstance(initial_value, (int, float)) or not math.isfinite(initial_value):
            raise ValueError("initial_value must be finite")
        config = optimizer_config or ReferenceOptimizerConfig()
        weights = weighting_config or ReferenceWeightingConfig()
        protocol = protocol_config or ReferenceProtocolConfig()
        fragments = {
            fragment_id: FragmentState(
                version=0,
                params=(float(initial_value),) * vector_size,
                outer_state=initial_state(vector_size, config),
                params_commit_id="genesis",
                outer_state_commit_id="genesis",
            )
            for fragment_id in range(fragment_count)
        }
        return cls(
            run_id=run_id,
            run_generation=0,
            optimizer_config=config,
            weighting_config=weights,
            protocol_config=protocol,
            head_commit_id="genesis",
            head_commit_seq=0,
            genesis_fragments=dict(fragments),
            fragments=fragments,
            proposals={},
            consumed_proposal_ids=frozenset(),
            dropped_proposal_ids=frozenset(),
            proposal_decisions={},
            commits=(),
        )

    @property
    def ancestor_commit_ids(self) -> frozenset[str]:
        return frozenset({"genesis", *(event.commit_id for event in self.commits)})

    def publish(self, proposal: ReferenceProposal) -> "SystemState":
        existing = self.proposals.get(proposal.proposal_id)
        if existing is not None:
            if existing != proposal:
                raise TransitionError("reference proposal identity-content conflict")
            return self
        for observed in self.proposals.values():
            if (
                observed.learner_id,
                observed.session_id,
                observed.fragment_id,
                observed.sequence,
            ) == (
                proposal.learner_id,
                proposal.session_id,
                proposal.fragment_id,
                proposal.sequence,
            ):
                raise TransitionError("learner/session/fragment sequence maps to different content")
        proposals = dict(self.proposals)
        proposals[proposal.proposal_id] = proposal
        result = replace(self, proposals=proposals)
        assert_invariants(result)
        return result

    def eligible(
        self,
        proposal: ReferenceProposal,
        *,
        max_staleness: int | None = None,
        max_fragment_staleness: int | None = None,
    ) -> bool:
        if max_staleness is None:
            max_staleness = self.protocol_config.max_global_staleness
        if max_fragment_staleness is None:
            max_fragment_staleness = self.protocol_config.max_fragment_staleness
        if proposal.proposal_id in self.consumed_proposal_ids | self.dropped_proposal_ids:
            return False
        for consumed_id in self.consumed_proposal_ids:
            consumed = self.proposals.get(consumed_id)
            if consumed is not None and (
                consumed.learner_id,
                consumed.session_id,
                consumed.fragment_id,
                consumed.base_commit_id,
                consumed.base_fragment_version,
            ) == (
                proposal.learner_id,
                proposal.session_id,
                proposal.fragment_id,
                proposal.base_commit_id,
                proposal.base_fragment_version,
            ):
                return False
        if proposal.fragment_id not in self.fragments:
            return False
        if proposal.base_commit_id not in self.ancestor_commit_ids:
            return False
        commit_sequences = {
            "genesis": 0,
            **{event.commit_id: event.commit_seq for event in self.commits},
        }
        if commit_sequences.get(proposal.base_commit_id) != proposal.base_commit_seq:
            return False
        if proposal.base_commit_seq > self.head_commit_seq:
            return False
        if self.head_commit_seq - proposal.base_commit_seq > max_staleness:
            return False
        fragment = self.fragments[proposal.fragment_id]
        base_fragment_version = self.genesis_fragments[proposal.fragment_id].version
        for event in self.commits[: proposal.base_commit_seq]:
            if isinstance(event, CommitEvent) and event.fragment_id == proposal.fragment_id:
                base_fragment_version = event.new_fragment_version
        if proposal.base_fragment_version != base_fragment_version:
            return False
        if proposal.base_fragment_version > fragment.version:
            return False
        if fragment.version - proposal.base_fragment_version > max_fragment_staleness:
            return False
        return True

    def committed_identity(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "run_generation": self.run_generation,
            "optimizer_config": self.optimizer_config.identity(),
            "weighting_config": self.weighting_config.identity(),
            "protocol_config": self.protocol_config.identity(),
            "head_commit_id": self.head_commit_id,
            "head_commit_seq": self.head_commit_seq,
            "genesis_fragments": {
                str(key): value.identity()
                for key, value in sorted(self.genesis_fragments.items())
            },
            "fragments": {
                str(key): value.identity() for key, value in sorted(self.fragments.items())
            },
            "consumed_proposal_ids": sorted(self.consumed_proposal_ids),
            "dropped_proposal_ids": sorted(self.dropped_proposal_ids),
            "proposal_decisions": {
                key: value.identity() for key, value in sorted(self.proposal_decisions.items())
            },
            "commits": [event.identity_body() | {"commit_id": event.commit_id} for event in self.commits],
        }

    def state_identity(self) -> dict[str, object]:
        return {
            **self.committed_identity(),
            "proposals": {
                key: value.identity() for key, value in sorted(self.proposals.items())
            },
        }

    def committed_digest(self) -> str:
        return canonical_digest(self.committed_identity())

    def state_digest(self) -> str:
        return canonical_digest(self.state_identity())


def prepare_transition(
    state: SystemState,
    *,
    fragment_id: int,
    selected_proposal_ids: Iterable[str],
) -> PreparedTransition:
    selected_ids = tuple(sorted(selected_proposal_ids))
    if not selected_ids or len(selected_ids) != len(set(selected_ids)):
        raise TransitionError("selection must contain unique proposal IDs")
    try:
        selected = [state.proposals[proposal_id] for proposal_id in selected_ids]
    except KeyError as exc:
        raise TransitionError(f"unknown proposal: {exc.args[0]}") from exc
    if any(proposal.fragment_id != fragment_id for proposal in selected):
        raise TransitionError("selection mixes fragments")
    if any(not state.eligible(proposal) for proposal in selected):
        raise TransitionError("selection contains an ineligible proposal")
    learner_ids = [proposal.learner_id for proposal in selected]
    if len(learner_ids) != len(set(learner_ids)):
        raise TransitionError("selection contains multiple proposals from one learner")
    weights = normalized_weights(
        {proposal.proposal_id: proposal.target_tokens for proposal in selected},
        staleness={
            proposal.proposal_id: state.fragments[fragment_id].version
            - proposal.base_fragment_version
            for proposal in selected
        },
        config=state.weighting_config,
    )
    aggregate = weighted_reduce(
        {proposal.proposal_id: proposal.values for proposal in selected}, weights
    )
    current = state.fragments[fragment_id]
    new_params, new_outer = outer_step(
        current.params,
        aggregate,
        current.outer_state,
        state.optimizer_config,
    )
    transition_digest = optimizer_state_digest(
        new_params, new_outer, state.optimizer_config
    )
    body = {
        "commit_seq": state.head_commit_seq + 1,
        "parent_commit_id": state.head_commit_id,
        "fragment_id": fragment_id,
        "previous_fragment_version": current.version,
        "new_fragment_version": current.version + 1,
        "selected_proposal_ids": list(selected_ids),
        "weights_hex": [[key, weights[key].hex()] for key in selected_ids],
        "new_params": vector_identity(new_params),
        "new_outer_state": new_outer.identity(),
        "transition_digest": transition_digest,
    }
    commit_id = "rc-" + canonical_digest(body)
    event = CommitEvent(
        commit_seq=state.head_commit_seq + 1,
        commit_id=commit_id,
        parent_commit_id=state.head_commit_id,
        fragment_id=fragment_id,
        previous_fragment_version=current.version,
        new_fragment_version=current.version + 1,
        selected_proposal_ids=selected_ids,
        weights_hex=tuple((key, weights[key].hex()) for key in selected_ids),
        new_params=new_params,
        new_outer_state=new_outer,
        transition_digest=transition_digest,
    )
    return PreparedTransition(
        parent_commit_id=state.head_commit_id,
        parent_commit_seq=state.head_commit_seq,
        fragment_id=fragment_id,
        selected_proposal_ids=selected_ids,
        event=event,
    )


def select_quorum(
    state: SystemState,
    *,
    fragment_id: int,
    quorum_min: int,
    quorum_max: int,
) -> tuple[str, ...]:
    if quorum_min < 1 or quorum_max < quorum_min:
        raise ValueError("quorum bounds are invalid")
    oldest_by_learner: dict[str, ReferenceProposal] = {}
    for proposal in state.proposals.values():
        if proposal.fragment_id != fragment_id or not state.eligible(proposal):
            continue
        existing = oldest_by_learner.get(proposal.learner_id)
        if existing is None or (proposal.sequence, proposal.proposal_id) < (
            existing.sequence,
            existing.proposal_id,
        ):
            oldest_by_learner[proposal.learner_id] = proposal
    selected = sorted(
        (proposal.proposal_id for proposal in oldest_by_learner.values())
    )[:quorum_max]
    return tuple(selected) if len(selected) >= quorum_min else ()


def decide_proposal(
    state: SystemState,
    *,
    proposal_id: str,
    decision: str,
    reason: str,
) -> SystemState:
    if not isinstance(decision, str) or decision not in {
        "dropped",
        "superseded",
        "quarantined",
        "expired",
    }:
        raise ValueError(f"unsupported proposal decision: {decision}")
    if not isinstance(reason, str) or not reason:
        raise ValueError("proposal decision reason must be a non-empty string")
    if proposal_id not in state.proposals:
        raise TransitionError("cannot decide an unknown proposal")
    if proposal_id in state.consumed_proposal_ids:
        raise TransitionError("cannot drop/supersede a committed proposal")
    existing = state.proposal_decisions.get(proposal_id)
    if existing is not None:
        if existing.decision != decision or existing.reason != reason:
            raise TransitionError("proposal already has a conflicting terminal decision")
        return state
    event_body = {
        "event_type": "proposal_decision",
        "commit_seq": state.head_commit_seq + 1,
        "parent_commit_id": state.head_commit_id,
        "proposal_id": proposal_id,
        "decision": decision,
        "reason": reason,
    }
    event = DecisionEvent(
        commit_seq=state.head_commit_seq + 1,
        commit_id="rd-" + canonical_digest(event_body),
        parent_commit_id=state.head_commit_id,
        proposal_id=proposal_id,
        decision=decision,
        reason=reason,
    )
    record = ProposalDecision(proposal_id, decision, reason, event.commit_seq)
    decisions = dict(state.proposal_decisions)
    decisions[proposal_id] = record
    result = replace(
        state,
        head_commit_id=event.commit_id,
        head_commit_seq=event.commit_seq,
        dropped_proposal_ids=state.dropped_proposal_ids | {proposal_id},
        proposal_decisions=decisions,
        commits=state.commits + (event,),
    )
    assert_invariants(result)
    return result


def commit_prepared(state: SystemState, prepared: PreparedTransition) -> SystemState:
    if (
        prepared.parent_commit_id != state.head_commit_id
        or prepared.parent_commit_seq != state.head_commit_seq
    ):
        raise TransitionConflict("prepared transition parent is stale")
    if set(prepared.selected_proposal_ids) & state.consumed_proposal_ids:
        raise TransitionConflict("proposal was already consumed")
    try:
        expected = prepare_transition(
            state,
            fragment_id=prepared.fragment_id,
            selected_proposal_ids=prepared.selected_proposal_ids,
        )
    except TransitionError as exc:
        raise TransitionConflict(f"prepared transition no longer validates: {exc}") from exc
    if prepared != expected:
        raise TransitionConflict("prepared event differs from the deterministic transition")
    current = state.fragments[prepared.fragment_id]
    event = prepared.event
    if event.previous_fragment_version != current.version:
        raise TransitionConflict("prepared fragment version is stale")
    fragments = dict(state.fragments)
    fragments[prepared.fragment_id] = FragmentState(
        version=event.new_fragment_version,
        params=event.new_params,
        outer_state=event.new_outer_state,
        params_commit_id=event.commit_id,
        outer_state_commit_id=event.commit_id,
    )
    result = replace(
        state,
        head_commit_id=event.commit_id,
        head_commit_seq=event.commit_seq,
        fragments=fragments,
        consumed_proposal_ids=state.consumed_proposal_ids
        | frozenset(prepared.selected_proposal_ids),
        commits=state.commits + (event,),
    )
    assert_invariants(result)
    return result


def check_invariants(state: SystemState) -> tuple[str, ...]:
    violations: list[str] = []
    expected_parent = "genesis"
    ancestors = {"genesis"}
    ancestor_sequences = {"genesis": 0}
    seen: set[str] = set()
    seen_interval_bases: set[tuple[str, str, int, str, int]] = set()
    expected_versions = {fragment_id: 0 for fragment_id in state.fragments}
    expected_fragments = dict(state.genesis_fragments)
    fragment_versions_by_commit = {
        "genesis": {
            fragment_id: fragment.version
            for fragment_id, fragment in state.genesis_fragments.items()
        }
    }
    expected_decisions: dict[str, ProposalDecision] = {}
    for expected_seq, event in enumerate(state.commits, start=1):
        if event.commit_seq != expected_seq:
            violations.append("I-002: commit sequence is not contiguous")
        if event.parent_commit_id != expected_parent:
            violations.append("I-002: commit parent chain is not linear")
        expected_parent = event.commit_id

        if isinstance(event, DecisionEvent):
            if event.decision not in {"dropped", "superseded", "quarantined", "expired"}:
                violations.append("I-003: decision event has an invalid terminal state")
            if not event.reason:
                violations.append("I-003: decision event has no reason")
            if event.proposal_id not in state.proposals:
                violations.append("I-001: decision names an unavailable proposal")
            if event.proposal_id in seen:
                violations.append("I-003: committed proposal also has a terminal decision")
            if event.proposal_id in expected_decisions:
                violations.append("I-003: proposal has multiple terminal decisions")
            expected_decisions[event.proposal_id] = ProposalDecision(
                event.proposal_id,
                event.decision,
                event.reason,
                event.commit_seq,
            )
            expected_id = "rd-" + canonical_digest(event.identity_body())
            if event.commit_id != expected_id:
                violations.append("I-009: decision identity is not deterministic")
            ancestors.add(event.commit_id)
            ancestor_sequences[event.commit_id] = event.commit_seq
            fragment_versions_by_commit[event.commit_id] = dict(expected_versions)
            continue

        duplicate = seen & set(event.selected_proposal_ids)
        if duplicate:
            violations.append("I-003: proposal appears in multiple commits")
        seen.update(event.selected_proposal_ids)
        selected: list[ReferenceProposal] = []
        for proposal_id in event.selected_proposal_ids:
            proposal = state.proposals.get(proposal_id)
            if proposal is None:
                violations.append("I-001: commit selects an unavailable proposal")
                continue
            selected.append(proposal)
            if (
                proposal.base_commit_id not in ancestors
                or proposal.base_commit_seq != ancestor_sequences.get(proposal.base_commit_id)
            ):
                violations.append("I-004: selected proposal has an invalid causal base")
            if proposal.fragment_id != event.fragment_id:
                violations.append("I-004: selected proposal targets a different fragment")
            base_versions = fragment_versions_by_commit.get(proposal.base_commit_id)
            if (
                base_versions is None
                or base_versions.get(proposal.fragment_id)
                != proposal.base_fragment_version
            ):
                violations.append(
                    "I-004: selected proposal fragment version differs from its base commit"
                )
            interval_base = (
                proposal.learner_id,
                proposal.session_id,
                proposal.fragment_id,
                proposal.base_commit_id,
                proposal.base_fragment_version,
            )
            if interval_base in seen_interval_bases:
                violations.append("I-003: overlapping same-base learner interval is included twice")
            seen_interval_bases.add(interval_base)
            if (
                event.previous_fragment_version - proposal.base_fragment_version
                > state.protocol_config.max_fragment_staleness
            ):
                violations.append("I-004: selected proposal exceeds fragment staleness")
            if (
                event.commit_seq - 1 - proposal.base_commit_seq
                > state.protocol_config.max_global_staleness
            ):
                violations.append("I-004: selected proposal exceeds global staleness")
        if len({proposal.learner_id for proposal in selected}) != len(selected):
            violations.append("I-004: commit selects multiple proposals from one learner")
        previous = expected_versions.get(event.fragment_id)
        if previous is None or event.previous_fragment_version != previous:
            violations.append("I-005: previous fragment version mismatch")
        if event.new_fragment_version != event.previous_fragment_version + 1:
            violations.append("I-005: fragment version does not increment by one")
        expected_versions[event.fragment_id] = event.new_fragment_version
        expected_fragment = expected_fragments.get(event.fragment_id)
        if (
            expected_fragment is not None
            and selected
            and len(selected) == len(event.selected_proposal_ids)
            and all(
                proposal.base_fragment_version <= expected_fragment.version
                for proposal in selected
            )
        ):
            try:
                weights = normalized_weights(
                    {proposal.proposal_id: proposal.target_tokens for proposal in selected},
                    staleness={
                        proposal.proposal_id: expected_fragment.version
                        - proposal.base_fragment_version
                        for proposal in selected
                    },
                    config=state.weighting_config,
                )
                expected_weights = tuple(
                    (proposal_id, weights[proposal_id].hex())
                    for proposal_id in event.selected_proposal_ids
                )
                aggregate = weighted_reduce(
                    {proposal.proposal_id: proposal.values for proposal in selected},
                    weights,
                )
                expected_params, expected_outer = outer_step(
                    expected_fragment.params,
                    aggregate,
                    expected_fragment.outer_state,
                    state.optimizer_config,
                )
                expected_transition_digest = optimizer_state_digest(
                    expected_params,
                    expected_outer,
                    state.optimizer_config,
                )
            except (ValueError, OverflowError):
                violations.append("I-009: committed numeric transition differs from oracle")
            else:
                if (
                    event.weights_hex != expected_weights
                    or event.new_params != expected_params
                    or event.new_outer_state != expected_outer
                    or event.transition_digest != expected_transition_digest
                ):
                    violations.append("I-009: committed numeric transition differs from oracle")
                expected_fragments[event.fragment_id] = FragmentState(
                    version=event.new_fragment_version,
                    params=event.new_params,
                    outer_state=event.new_outer_state,
                    params_commit_id=event.commit_id,
                    outer_state_commit_id=event.commit_id,
                )
        expected_id = "rc-" + canonical_digest(event.identity_body())
        if event.commit_id != expected_id:
            violations.append("I-009: commit identity is not deterministic")
        ancestors.add(event.commit_id)
        ancestor_sequences[event.commit_id] = event.commit_seq
        fragment_versions_by_commit[event.commit_id] = dict(expected_versions)
    if state.head_commit_seq != len(state.commits) or state.head_commit_id != expected_parent:
        violations.append("I-002: head does not name the committed chain tip")
    if seen != set(state.consumed_proposal_ids):
        violations.append("I-003: consumption set differs from committed selections")
    if dict(state.proposal_decisions) != expected_decisions:
        violations.append("I-003: terminal decisions differ from committed decision events")
    if set(expected_decisions) != set(state.dropped_proposal_ids):
        violations.append("I-003: terminal decisions differ from dropped proposal set")
    if state.consumed_proposal_ids & state.dropped_proposal_ids:
        violations.append("I-003: proposal is both consumed and terminally dropped")
    for fragment_id, fragment in state.fragments.items():
        if fragment.version != expected_versions.get(fragment_id, 0):
            violations.append("I-005: frontier fragment version differs from history")
        if fragment.params_commit_id != fragment.outer_state_commit_id:
            violations.append("I-005: parameter and outer state commit IDs differ")
        if fragment != expected_fragments.get(fragment_id):
            violations.append("I-005: frontier state differs from folded commit history")
        if fragment.version > 0 and fragment.params_commit_id not in {
            event.commit_id for event in state.commits if isinstance(event, CommitEvent)
        }:
            violations.append("I-001: fragment references an unknown producing commit")
    return tuple(dict.fromkeys(violations))


def assert_invariants(state: SystemState) -> None:
    violations = check_invariants(state)
    if violations:
        raise TransitionError("; ".join(violations))


def fold_commits(genesis: SystemState, commits: Iterable[LogEvent]) -> SystemState:
    state = replace(
        genesis,
        head_commit_id="genesis",
        head_commit_seq=0,
        fragments=dict(genesis.genesis_fragments),
        consumed_proposal_ids=frozenset(),
        dropped_proposal_ids=frozenset(),
        proposal_decisions={},
        commits=(),
    )
    for event in commits:
        if event.parent_commit_id != state.head_commit_id:
            raise TransitionError("cannot fold non-linear commit history")
        if isinstance(event, DecisionEvent):
            if event.proposal_id not in state.proposals:
                raise TransitionError("cannot fold decision for an unknown proposal")
            if event.proposal_id in state.consumed_proposal_ids:
                raise TransitionError("cannot fold decision for a consumed proposal")
            if event.proposal_id in state.proposal_decisions:
                raise TransitionError("cannot fold duplicate proposal decision")
            decisions = dict(state.proposal_decisions)
            decisions[event.proposal_id] = ProposalDecision(
                event.proposal_id,
                event.decision,
                event.reason,
                event.commit_seq,
            )
            state = replace(
                state,
                head_commit_id=event.commit_id,
                head_commit_seq=event.commit_seq,
                dropped_proposal_ids=state.dropped_proposal_ids | {event.proposal_id},
                proposal_decisions=decisions,
                commits=state.commits + (event,),
            )
            assert_invariants(state)
            continue
        if set(event.selected_proposal_ids) & state.consumed_proposal_ids:
            raise TransitionError("cannot fold double-included proposal")
        current = state.fragments[event.fragment_id]
        if event.previous_fragment_version != current.version:
            raise TransitionError("cannot fold wrong fragment parent version")
        fragments = dict(state.fragments)
        fragments[event.fragment_id] = FragmentState(
            version=event.new_fragment_version,
            params=event.new_params,
            outer_state=event.new_outer_state,
            params_commit_id=event.commit_id,
            outer_state_commit_id=event.commit_id,
        )
        state = replace(
            state,
            head_commit_id=event.commit_id,
            head_commit_seq=event.commit_seq,
            fragments=fragments,
            consumed_proposal_ids=state.consumed_proposal_ids
            | frozenset(event.selected_proposal_ids),
            commits=state.commits + (event,),
        )
        assert_invariants(state)
    assert_invariants(state)
    return state


def recover_prefix(state: SystemState, commit_seq: int | None = None) -> SystemState:
    if commit_seq is None:
        commit_seq = state.head_commit_seq
    if commit_seq < 0 or commit_seq > state.head_commit_seq:
        raise ValueError("invalid recovery prefix")
    genesis = replace(
        state,
        head_commit_id="genesis",
        head_commit_seq=0,
        fragments=dict(state.genesis_fragments),
        proposals=dict(state.proposals),
        consumed_proposal_ids=frozenset(),
        dropped_proposal_ids=frozenset(),
        proposal_decisions={},
        commits=(),
    )
    return fold_commits(genesis, state.commits[:commit_seq])
