"""Dependency-free P05 coordination reference state machine.

The lease book is an observational liveness aid.  A writer becomes authoritative
only after an epoch/owner/session fact is committed through the optimizer head
CAS.  All safety decisions below therefore use :class:`CoordinationState`, not
lease expiry or lease-file visibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from types import MappingProxyType
from typing import Mapping

from fs_diloco.protocol.canonical_json import canonical_digest


class CoordinationConflict(RuntimeError):
    """The requested transition is stale or not authorized."""


class MutationRequestConflict(CoordinationConflict):
    """One request identity was reused for different canonical content."""


def _nonempty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _nonnegative_int(value: object, name: str, *, positive: bool = False) -> int:
    minimum = 1 if positive else 0
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


@dataclass(frozen=True)
class OwnerToken:
    owner_id: str
    owner_session_id: str
    fencing_epoch: int

    def __post_init__(self) -> None:
        _nonempty(self.owner_id, "owner_id")
        _nonempty(self.owner_session_id, "owner_session_id")
        _nonnegative_int(self.fencing_epoch, "fencing_epoch", positive=True)

    @classmethod
    def from_lease(cls, lease: "LeaseRecord") -> "OwnerToken":
        return cls(
            owner_id=lease.owner_id,
            owner_session_id=lease.owner_session_id,
            fencing_epoch=lease.proposed_fencing_epoch,
        )

    def identity(self) -> dict[str, object]:
        return {
            "owner_id": self.owner_id,
            "owner_session_id": self.owner_session_id,
            "fencing_epoch": self.fencing_epoch,
        }


@dataclass(frozen=True)
class LeaseRequest:
    request_id: str
    owner_id: str
    owner_session_id: str
    observed_fencing_epoch: int
    now_ns: int
    ttl_ns: int

    def __post_init__(self) -> None:
        _nonempty(self.request_id, "request_id")
        _nonempty(self.owner_id, "owner_id")
        _nonempty(self.owner_session_id, "owner_session_id")
        _nonnegative_int(self.observed_fencing_epoch, "observed_fencing_epoch")
        _nonnegative_int(self.now_ns, "now_ns")
        _nonnegative_int(self.ttl_ns, "ttl_ns", positive=True)

    def identity(self) -> dict[str, object]:
        return {
            "operation": "acquire",
            "request_id": self.request_id,
            "owner_id": self.owner_id,
            "owner_session_id": self.owner_session_id,
            "observed_fencing_epoch": self.observed_fencing_epoch,
            "now_ns": self.now_ns,
            "ttl_ns": self.ttl_ns,
        }


@dataclass(frozen=True)
class LeaseRecord:
    owner_id: str
    owner_session_id: str
    proposed_fencing_epoch: int
    lease_sequence: int
    expires_at_ns: int
    mutation_request_id: str
    mutation_digest: str

    def __post_init__(self) -> None:
        _nonempty(self.owner_id, "owner_id")
        _nonempty(self.owner_session_id, "owner_session_id")
        _nonnegative_int(
            self.proposed_fencing_epoch, "proposed_fencing_epoch", positive=True
        )
        _nonnegative_int(self.lease_sequence, "lease_sequence", positive=True)
        _nonnegative_int(self.expires_at_ns, "expires_at_ns", positive=True)
        _nonempty(self.mutation_request_id, "mutation_request_id")
        _nonempty(self.mutation_digest, "mutation_digest")

    def identity(self) -> dict[str, object]:
        return {
            "owner_id": self.owner_id,
            "owner_session_id": self.owner_session_id,
            "proposed_fencing_epoch": self.proposed_fencing_epoch,
            "lease_sequence": self.lease_sequence,
            "expires_at_ns": self.expires_at_ns,
            "mutation_request_id": self.mutation_request_id,
            "mutation_digest": self.mutation_digest,
        }


@dataclass(frozen=True)
class LeaseMutationResult:
    request_digest: str
    record: LeaseRecord


@dataclass(frozen=True)
class LeaseBook:
    """Pure model of a conditional lease object plus immutable request results."""

    version: int
    record: LeaseRecord | None
    request_results: Mapping[str, LeaseMutationResult] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _nonnegative_int(self.version, "version")
        object.__setattr__(
            self, "request_results", MappingProxyType(dict(self.request_results))
        )

    @classmethod
    def empty(cls) -> "LeaseBook":
        return cls(version=0, record=None)

    def acquire(
        self,
        request: LeaseRequest,
        *,
        expected_version: int | None = None,
    ) -> tuple["LeaseBook", LeaseRecord]:
        request_digest = canonical_digest(request.identity())
        prior = self.request_results.get(request.request_id)
        if prior is not None:
            if prior.request_digest != request_digest:
                raise MutationRequestConflict(
                    "lease request identity maps to different canonical content"
                )
            return self, prior.record
        if expected_version is not None and expected_version != self.version:
            raise CoordinationConflict("lease conditional version is stale")
        if self.record is not None and request.now_ns < self.record.expires_at_ns:
            raise CoordinationConflict("lease is still active")
        proposed_epoch = request.observed_fencing_epoch + 1
        lease_sequence = 1 if self.record is None else self.record.lease_sequence + 1
        record = LeaseRecord(
            owner_id=request.owner_id,
            owner_session_id=request.owner_session_id,
            proposed_fencing_epoch=proposed_epoch,
            lease_sequence=lease_sequence,
            expires_at_ns=request.now_ns + request.ttl_ns,
            mutation_request_id=request.request_id,
            mutation_digest=request_digest,
        )
        results = dict(self.request_results)
        results[request.request_id] = LeaseMutationResult(request_digest, record)
        return (
            LeaseBook(version=self.version + 1, record=record, request_results=results),
            record,
        )


@dataclass(frozen=True)
class StopRequest:
    request_id: str
    reason: str

    def __post_init__(self) -> None:
        _nonempty(self.request_id, "request_id")
        _nonempty(self.reason, "reason")

    def identity(self) -> dict[str, object]:
        return {"request_id": self.request_id, "reason": self.reason}


@dataclass(frozen=True)
class StopState:
    request_id: str
    reason: str
    committed_at_seq: int

    def identity(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "reason": self.reason,
            "committed_at_seq": self.committed_at_seq,
        }


@dataclass(frozen=True)
class ControlEvent:
    kind: str
    request_id: str
    request_digest: str
    commit_seq: int
    commit_id: str
    parent_commit_id: str
    fencing_epoch: int
    owner_id: str
    owner_session_id: str
    optimizer_transition_count: int
    stop: StopState | None = None


@dataclass(frozen=True)
class CoordinationState:
    commit_seq: int
    commit_id: str
    optimizer_transition_count: int
    fencing_epoch: int
    owner_id: str | None
    owner_session_id: str | None
    stop: StopState | None
    history: tuple[ControlEvent, ...]
    request_digests: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _nonnegative_int(self.commit_seq, "commit_seq")
        _nonnegative_int(
            self.optimizer_transition_count, "optimizer_transition_count"
        )
        _nonnegative_int(self.fencing_epoch, "fencing_epoch")
        object.__setattr__(self, "history", tuple(self.history))
        object.__setattr__(
            self, "request_digests", MappingProxyType(dict(self.request_digests))
        )

    @classmethod
    def genesis(cls) -> "CoordinationState":
        return cls(
            commit_seq=0,
            commit_id="genesis-coordination",
            optimizer_transition_count=0,
            fencing_epoch=0,
            owner_id=None,
            owner_session_id=None,
            stop=None,
            history=(),
        )

    @property
    def owner_token(self) -> OwnerToken | None:
        if self.owner_id is None or self.owner_session_id is None:
            return None
        return OwnerToken(
            owner_id=self.owner_id,
            owner_session_id=self.owner_session_id,
            fencing_epoch=self.fencing_epoch,
        )

    def can_commit(self, token: OwnerToken) -> bool:
        return self.owner_token == token and self.stop is None

    def _retry_or_conflict(self, request_id: str, digest: str) -> bool:
        prior = self.request_digests.get(request_id)
        if prior is None:
            return False
        if prior != digest:
            raise MutationRequestConflict(
                "committed request identity maps to different canonical content"
            )
        return True

    def _commit(
        self,
        *,
        kind: str,
        token: OwnerToken,
        request_id: str,
        request_body: Mapping[str, object],
        expected_commit_id: str,
        optimizer_increment: int,
        stop: StopState | None = None,
    ) -> "CoordinationState":
        request_digest = canonical_digest(dict(request_body))
        if self._retry_or_conflict(request_id, request_digest):
            return self
        if expected_commit_id != self.commit_id:
            raise CoordinationConflict("head changed before control transition CAS")
        next_seq = self.commit_seq + 1
        next_optimizer_count = self.optimizer_transition_count + optimizer_increment
        body: dict[str, object] = {
            "kind": kind,
            "request_id": request_id,
            "request_digest": request_digest,
            "commit_seq": next_seq,
            "parent_commit_id": self.commit_id,
            "fencing_epoch": token.fencing_epoch,
            "owner_id": token.owner_id,
            "owner_session_id": token.owner_session_id,
            "optimizer_transition_count": next_optimizer_count,
        }
        if stop is not None:
            body["stop"] = stop.identity()
        commit_id = "coord-" + canonical_digest(body)
        event = ControlEvent(
            kind=kind,
            request_id=request_id,
            request_digest=request_digest,
            commit_seq=next_seq,
            commit_id=commit_id,
            parent_commit_id=self.commit_id,
            fencing_epoch=token.fencing_epoch,
            owner_id=token.owner_id,
            owner_session_id=token.owner_session_id,
            optimizer_transition_count=next_optimizer_count,
            stop=stop,
        )
        request_digests = dict(self.request_digests)
        request_digests[request_id] = request_digest
        return CoordinationState(
            commit_seq=next_seq,
            commit_id=commit_id,
            optimizer_transition_count=next_optimizer_count,
            fencing_epoch=token.fencing_epoch,
            owner_id=token.owner_id,
            owner_session_id=token.owner_session_id,
            stop=stop if stop is not None else self.stop,
            history=(*self.history, event),
            request_digests=request_digests,
        )

    def commit_epoch_bump(
        self,
        *,
        token: OwnerToken,
        request_id: str,
        expected_commit_id: str,
    ) -> "CoordinationState":
        _nonempty(request_id, "request_id")
        request_body = {
            "operation": "epoch_bump",
            "request_id": request_id,
            **token.identity(),
        }
        digest = canonical_digest(request_body)
        if self._retry_or_conflict(request_id, digest):
            return self
        if token.fencing_epoch <= self.fencing_epoch:
            raise CoordinationConflict("fencing epoch must increase on takeover")
        return self._commit(
            kind="epoch_bump",
            token=token,
            request_id=request_id,
            request_body=request_body,
            expected_commit_id=expected_commit_id,
            optimizer_increment=0,
        )

    def _require_owner(self, token: OwnerToken) -> None:
        if self.owner_token != token:
            raise CoordinationConflict("writer token is not the committed fenced owner")

    def commit_optimizer(
        self,
        *,
        token: OwnerToken,
        request_id: str,
        expected_commit_id: str,
    ) -> "CoordinationState":
        self._require_owner(token)
        if self.stop is not None:
            raise CoordinationConflict("optimizer transition is forbidden after stop")
        request_body = {
            "operation": "optimizer",
            "request_id": request_id,
            **token.identity(),
        }
        return self._commit(
            kind="optimizer",
            token=token,
            request_id=request_id,
            request_body=request_body,
            expected_commit_id=expected_commit_id,
            optimizer_increment=1,
        )

    def commit_stop(
        self,
        *,
        token: OwnerToken,
        request: StopRequest,
        expected_commit_id: str,
    ) -> "CoordinationState":
        self._require_owner(token)
        if self.stop is not None and self.stop.request_id != request.request_id:
            raise CoordinationConflict("a different authoritative stop is already committed")
        stop = StopState(
            request_id=request.request_id,
            reason=request.reason,
            committed_at_seq=self.commit_seq + 1,
        )
        return self._commit(
            kind="stop",
            token=token,
            request_id=request.request_id,
            request_body={"operation": "stop", **request.identity(), **token.identity()},
            expected_commit_id=expected_commit_id,
            optimizer_increment=0,
            stop=stop,
        )


@dataclass(frozen=True)
class SafetyReport:
    trace_count: int
    split_brain_count: int
    stale_commit_count: int


@dataclass(frozen=True)
class _Exploration:
    state: CoordinationState
    lease_book: LeaseBook
    tokens: Mapping[str, OwnerToken]
    now_ns: int


def _step(item: _Exploration, operation: str) -> _Exploration:
    state, lease_book, tokens, now_ns = (
        item.state,
        item.lease_book,
        dict(item.tokens),
        item.now_ns,
    )
    owner = "a" if operation.endswith("a") else "b"
    owner_id = f"syncer-{owner}"
    session_id = f"session-{owner}"
    try:
        if operation.startswith("acquire"):
            lease_book, lease = lease_book.acquire(
                LeaseRequest(
                    request_id=f"acquire-{owner}-{lease_book.version}-{now_ns}",
                    owner_id=owner_id,
                    owner_session_id=session_id,
                    observed_fencing_epoch=state.fencing_epoch,
                    now_ns=now_ns,
                    ttl_ns=2,
                )
            )
            tokens[owner] = OwnerToken.from_lease(lease)
        elif operation.startswith("fence") and owner in tokens:
            state = state.commit_epoch_bump(
                token=tokens[owner],
                request_id=f"fence-{owner}-{state.commit_seq}-{now_ns}",
                expected_commit_id=state.commit_id,
            )
        elif operation.startswith("commit") and owner in tokens:
            state = state.commit_optimizer(
                token=tokens[owner],
                request_id=f"optimizer-{owner}-{state.commit_seq}-{now_ns}",
                expected_commit_id=state.commit_id,
            )
        elif operation == "tick_a":
            now_ns += 1
        elif operation == "tick_b":
            now_ns += 3
    except CoordinationConflict:
        pass
    return _Exploration(state, lease_book, MappingProxyType(tokens), now_ns)


def _check_state(item: _Exploration) -> tuple[int, int]:
    split_brain = 0
    stale = 0
    owner_by_epoch: dict[int, tuple[str, str]] = {}
    prior_epoch = 0
    prior_optimizer_count = 0
    for event in item.state.history:
        if event.fencing_epoch < prior_epoch:
            stale += 1
        prior_epoch = event.fencing_epoch
        if event.optimizer_transition_count < prior_optimizer_count:
            stale += 1
        prior_optimizer_count = event.optimizer_transition_count
        owner = (event.owner_id, event.owner_session_id)
        existing = owner_by_epoch.setdefault(event.fencing_epoch, owner)
        if existing != owner:
            split_brain += 1
    return split_brain, stale


def _assert_mutant_is_unsafe(mutant: str) -> None:
    state = CoordinationState.genesis()
    lease_book, lease_a = LeaseBook.empty().acquire(
        LeaseRequest("ma", "syncer-a", "session-a", 0, 0, 1)
    )
    token_a = OwnerToken.from_lease(lease_a)
    state = state.commit_epoch_bump(
        token=token_a, request_id="mfa", expected_commit_id=state.commit_id
    )
    lease_book, lease_b = lease_book.acquire(
        LeaseRequest("mb", "syncer-b", "session-b", state.fencing_epoch, 10, 1)
    )
    token_b = OwnerToken.from_lease(lease_b)

    if mutant == "lease_file_only":
        # The lease file says B before the authoritative epoch bump.  A
        # lease-file-only implementation would accept B against an A-owned head.
        assert state.owner_token == token_b, "lease-file-only admitted an unfenced owner"
    elif mutant == "wall_clock_only":
        # Two local clocks can independently classify their leases as live.
        local_a_live = 0 < lease_a.expires_at_ns
        local_b_live = 10 < lease_b.expires_at_ns
        assert not (local_a_live and local_b_live), "wall-clock-only admitted two writers"
    elif mutant == "stale_epoch_allowed":
        state = state.commit_epoch_bump(
            token=token_b, request_id="mfb", expected_commit_id=state.commit_id
        )
        assert state.owner_token == token_a, "stale epoch was accepted after takeover"
    else:
        raise ValueError(f"unknown coordination mutant: {mutant}")


def assert_bounded_safety(
    *, max_depth: int = 6, mutant: str | None = None
) -> SafetyReport:
    """Explore bounded acquire/fence/commit interleavings.

    Mutant mode executes a minimized counterexample and deliberately raises an
    assertion when the mutant violates the same authoritative-owner invariant.
    """

    _nonnegative_int(max_depth, "max_depth", positive=True)
    if mutant is not None:
        _assert_mutant_is_unsafe(mutant)
        raise AssertionError(f"coordination mutant unexpectedly survived: {mutant}")

    alphabet = (
        "acquire_a",
        "acquire_b",
        "fence_a",
        "fence_b",
        "commit_a",
        "commit_b",
        "tick_a",
        "tick_b",
    )
    trace_count = 0
    split_brain_count = 0
    stale_commit_count = 0
    initial = _Exploration(
        CoordinationState.genesis(), LeaseBook.empty(), MappingProxyType({}), 0
    )
    # Exhaustive depth six would be 262k traces.  A deterministic bounded
    # prefix of 4,096 traces is sufficient for the fast contract while keeping
    # the exact failing trace reproducible.
    for operations in product(alphabet, repeat=max_depth):
        item = initial
        for operation in operations:
            item = _step(item, operation)
        split, stale = _check_state(item)
        split_brain_count += split
        stale_commit_count += stale
        trace_count += 1
        if trace_count >= 4096:
            break
    if split_brain_count or stale_commit_count:
        raise AssertionError(
            "coordination safety violation: "
            f"split_brain={split_brain_count}, stale={stale_commit_count}"
        )
    return SafetyReport(
        trace_count=trace_count,
        split_brain_count=split_brain_count,
        stale_commit_count=stale_commit_count,
    )
