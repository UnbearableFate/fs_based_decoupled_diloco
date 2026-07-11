"""Prepare immutable transition objects and commit them with one head CAS."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable, Mapping

from fs_diloco.log.model import ReferenceProposal
from fs_diloco.optimizer.reference_adapter import transition
from fs_diloco.protocol.canonical_json import canonical_bytes, canonical_digest
from fs_diloco.protocol.identities import commit_id_for, frontier_digest_for
from fs_diloco.protocol.schemas import (
    CommitManifest,
    CommittedManifest,
    FragmentState,
    FrontierManifest,
    HeadManifest,
    ObjectRef,
    ProposalSelection,
)
from fs_diloco.storage import (
    ImmutableConflict,
    InjectedTimeout,
    NotFound,
    PreconditionFailed,
)
from fs_diloco.storage.base import ObjectMetadata, StorageBackend
from fs_diloco.testing.deterministic_reference import initial_state, vector_identity

from .codec import (
    canonical_object,
    content_ref,
    decode_outer_state,
    decode_params,
    encode_outer_state,
    encode_params,
    verified_get,
)
from .errors import CommitConflict, InjectedLogCrash, RunInitializationError, VerificationError
from .layout import LogLayout
from .run import RunManifest, RunSpec


CRASH_POINTS = (
    "before_params_put",
    "after_params_put",
    "before_outer_state_put",
    "after_outer_state_put",
    "before_commit_put",
    "after_commit_put",
    "before_frontier_put",
    "after_frontier_put",
    "before_head_cas",
    "after_head_cas",
)


def _fire(requested: str | None, point: str) -> None:
    if requested == point:
        raise InjectedLogCrash(point)


def _make_frontier(body: dict[str, object]) -> FrontierManifest:
    payload = dict(body)
    payload["frontier_sha256"] = frontier_digest_for(payload)
    return FrontierManifest.from_dict(payload)


def _make_commit(body: dict[str, object]) -> CommitManifest:
    payload = dict(body)
    payload["commit_id"] = commit_id_for(payload)
    return CommitManifest.from_dict(payload)


def _head_bytes(head: HeadManifest) -> bytes:
    return canonical_bytes(head.to_dict())


def _logical_head_version(head: HeadManifest) -> str:
    return "sha256:" + hashlib.sha256(_head_bytes(head)).hexdigest()


def _proposal_bytes(proposal: ReferenceProposal) -> bytes:
    return canonical_bytes(proposal.identity())


def _proposal_from_bytes(data: bytes) -> ReferenceProposal:
    payload = canonical_object(data)
    required = {
        "proposal_id",
        "learner_id",
        "session_id",
        "sequence",
        "fragment_id",
        "base_commit_id",
        "base_commit_seq",
        "base_fragment_version",
        "target_tokens",
        "values",
    }
    if set(payload) != required or not isinstance(payload["values"], list):
        raise VerificationError("invalid durable proposal fields")
    try:
        values = tuple(float.fromhex(value) for value in payload["values"])
        proposal = ReferenceProposal.create(
            learner_id=payload["learner_id"],
            session_id=payload["session_id"],
            sequence=payload["sequence"],
            fragment_id=payload["fragment_id"],
            base_commit_id=payload["base_commit_id"],
            base_commit_seq=payload["base_commit_seq"],
            base_fragment_version=payload["base_fragment_version"],
            target_tokens=payload["target_tokens"],
            values=values,
        )
    except Exception as exc:
        raise VerificationError(f"invalid durable proposal: {exc}") from exc
    if proposal.proposal_id != payload["proposal_id"] or proposal.identity() != payload:
        raise VerificationError("durable proposal identity mismatch")
    return proposal


@dataclass(frozen=True)
class LoadedHead:
    manifest: HeadManifest
    metadata: ObjectMetadata


@dataclass(frozen=True)
class PreparedLogTransition:
    parent_head: LoadedHead
    commit: CommittedManifest
    commit_ref: ObjectRef
    frontier: FrontierManifest
    frontier_ref: ObjectRef
    new_head: HeadManifest
    request_id: str


@dataclass(frozen=True)
class CommitResult:
    status: str
    commit_id: str
    commit_seq: int
    head_version: str


class TransactionalLog:
    """A backend-neutral event log whose only transition mutation is head CAS."""

    def __init__(self, backend: StorageBackend, manifest: RunManifest) -> None:
        self.backend = backend
        self.manifest = manifest
        self.spec = manifest.spec
        self.layout = LogLayout(self.spec.run_id, self.spec.run_generation)

    @classmethod
    def initialize(
        cls,
        backend: StorageBackend,
        spec: RunSpec,
        initial_fragments: Mapping[int, Iterable[float]],
    ) -> "TransactionalLog":
        layout = LogLayout(spec.run_id, spec.run_generation)
        if not initial_fragments or sorted(initial_fragments) != list(range(len(initial_fragments))):
            raise RunInitializationError(
                "initial fragments must use contiguous IDs starting at zero"
            )
        fragment_states: dict[int, FragmentState] = {}
        for fragment_id, values in sorted(initial_fragments.items()):
            params = tuple(float(value) for value in values)
            if not params:
                raise RunInitializationError("initial fragment vectors must be non-empty")
            params_data = encode_params(params)
            params_ref = content_ref(
                layout.params_key(fragment_id, hashlib.sha256(params_data).hexdigest()),
                params_data,
            )
            outer_data = encode_outer_state(initial_state(len(params), spec.optimizer_config))
            outer_ref = content_ref(
                layout.outer_state_key(fragment_id, hashlib.sha256(outer_data).hexdigest()),
                outer_data,
            )
            try:
                backend.put_immutable(params_ref.key, params_data, sha256=params_ref.sha256)
                backend.put_immutable(outer_ref.key, outer_data, sha256=outer_ref.sha256)
            except ImmutableConflict as exc:
                raise RunInitializationError(str(exc)) from exc
            fragment_states[fragment_id] = FragmentState(
                version=0,
                params_ref=params_ref,
                outer_state_ref=outer_ref,
                producing_commit_id="pending-genesis",
            )

        genesis_identity = {
            "spec_digest": spec.digest,
            "fragments": {
                str(key): {
                    "params_ref": value.params_ref.to_dict(),
                    "outer_state_ref": value.outer_state_ref.to_dict(),
                }
                for key, value in sorted(fragment_states.items())
            },
        }
        genesis_commit_id = "genesis-" + canonical_digest(genesis_identity)
        fragment_states = {
            key: FragmentState(
                version=0,
                params_ref=value.params_ref,
                outer_state_ref=value.outer_state_ref,
                producing_commit_id=genesis_commit_id,
            )
            for key, value in fragment_states.items()
        }
        genesis = _make_frontier(
            {
                "manifest_type": "frontier",
                "protocol_version": 2,
                "run_id": spec.run_id,
                "run_generation": spec.run_generation,
                "commit_seq": 0,
                "commit_id": genesis_commit_id,
                "parent_frontier_sha256": None,
                "fencing_epoch": 0,
                "fragments": {
                    str(key): value.to_dict() for key, value in sorted(fragment_states.items())
                },
                "scheduler_state": {"next_fragment_cursor": 0},
                "consumed_proposal_ids": [],
            }
        )
        genesis_data = canonical_bytes(genesis.to_dict())
        genesis_ref = content_ref(
            layout.frontier_key(0, genesis.frontier_sha256), genesis_data
        )
        run_manifest = RunManifest(spec, genesis_commit_id, genesis_ref)
        head = HeadManifest(
            protocol_version=2,
            run_id=spec.run_id,
            run_generation=spec.run_generation,
            fencing_epoch=0,
            commit_seq=0,
            commit_id=genesis_commit_id,
            frontier_ref=genesis_ref,
        )
        try:
            backend.put_immutable(
                genesis_ref.key, genesis_data, sha256=genesis_ref.sha256
            )
            backend.put_immutable(layout.run_manifest_key, run_manifest.canonical_bytes())
        except ImmutableConflict as exc:
            raise RunInitializationError(
                "run generation already has a different manifest or genesis"
            ) from exc
        try:
            backend.head(layout.head_key)
        except NotFound:
            try:
                backend.put_if_absent(layout.head_key, _head_bytes(head))
            except ImmutableConflict as exc:
                raise RunInitializationError("run head conflicts with genesis") from exc
        log = cls.open(backend, spec.run_id, spec.run_generation)
        if log.spec != spec:
            raise RunInitializationError("existing run specification differs")
        current = log.load_head().manifest
        if current.run_id != spec.run_id or current.run_generation != spec.run_generation:
            raise RunInitializationError("existing head belongs to another run generation")
        return log

    @classmethod
    def open(
        cls,
        backend: StorageBackend,
        run_id: str,
        run_generation: int = 0,
    ) -> "TransactionalLog":
        layout = LogLayout(run_id, run_generation)
        try:
            manifest = RunManifest.from_bytes(backend.get(layout.run_manifest_key))
        except Exception as exc:
            if isinstance(exc, VerificationError):
                raise
            raise RunInitializationError(f"cannot open run manifest: {exc}") from exc
        if manifest.spec.run_id != run_id or manifest.spec.run_generation != run_generation:
            raise RunInitializationError("run manifest identity differs from requested layout")
        return cls(backend, manifest)

    def load_head(self) -> LoadedHead:
        last_error: Exception | None = None
        for _ in range(5):
            try:
                metadata = self.backend.head(self.layout.head_key)
                data = self.backend.get(
                    self.layout.head_key, expected_version=metadata.version
                )
                payload = canonical_object(data)
                manifest = HeadManifest.from_dict(payload)
                if (
                    manifest.run_id != self.spec.run_id
                    or manifest.run_generation != self.spec.run_generation
                ):
                    raise VerificationError("head run identity mismatch")
                return LoadedHead(manifest, metadata)
            except PreconditionFailed as exc:
                last_error = exc
        raise VerificationError(f"head changed repeatedly while reading: {last_error}")

    def publish_proposal(self, proposal: ReferenceProposal) -> ObjectRef:
        data = _proposal_bytes(proposal)
        ref = content_ref(self.layout.proposal_key(proposal.proposal_id), data)
        self.backend.put_immutable(ref.key, data, sha256=ref.sha256)
        return ref

    def read_proposal(self, proposal_id: str, *, commit_seq: int | None = None) -> ReferenceProposal:
        key = self.layout.proposal_key(proposal_id)
        try:
            data = self.backend.get(key)
            proposal = _proposal_from_bytes(data)
        except VerificationError as exc:
            if exc.commit_seq is None and commit_seq is not None:
                raise VerificationError(str(exc), commit_seq=commit_seq) from exc
            raise
        except Exception as exc:
            raise VerificationError(
                f"cannot read proposal {proposal_id}: {exc}", commit_seq=commit_seq
            ) from exc
        if proposal.proposal_id != proposal_id:
            raise VerificationError(
                f"proposal key/identity mismatch for {proposal_id}", commit_seq=commit_seq
            )
        return proposal

    def prepare_transition(
        self,
        *,
        fragment_id: int,
        selected_proposal_ids: Iterable[str],
        crash_at: str | None = None,
    ) -> PreparedLogTransition:
        from .replay import replay_log

        if crash_at is not None and crash_at not in CRASH_POINTS:
            raise ValueError(f"unknown crash point: {crash_at}")
        replay = replay_log(self)
        selected_ids = tuple(sorted(selected_proposal_ids))
        if not selected_ids or len(selected_ids) != len(set(selected_ids)):
            raise CommitConflict("selection must contain unique proposal IDs")
        if fragment_id not in replay.head_frontier.fragments:
            raise CommitConflict("selection targets an unknown fragment")
        proposals = tuple(self.read_proposal(key) for key in selected_ids)
        if any(proposal.fragment_id != fragment_id for proposal in proposals):
            raise CommitConflict("selection mixes fragments")
        if len({proposal.learner_id for proposal in proposals}) != len(proposals):
            raise CommitConflict("selection contains multiple proposals from one learner")
        current_fragment = replay.head_frontier.fragments[fragment_id]
        for proposal in proposals:
            if proposal.proposal_id in replay.consumption:
                raise CommitConflict("selection contains an already-consumed proposal")
            base = replay.frontier_by_commit.get(proposal.base_commit_id)
            if base is None or base.commit_seq != proposal.base_commit_seq:
                raise CommitConflict("proposal has an invalid causal base")
            base_fragment = base.fragments.get(fragment_id)
            if base_fragment is None or base_fragment.version != proposal.base_fragment_version:
                raise CommitConflict("proposal base fragment version mismatch")
            if replay.head_frontier.commit_seq - base.commit_seq > self.spec.max_global_staleness:
                raise CommitConflict("proposal exceeds global staleness")
            if (
                current_fragment.version - proposal.base_fragment_version
                > self.spec.max_fragment_staleness
            ):
                raise CommitConflict("proposal exceeds fragment staleness")
            for consumed in replay.proposals.values():
                same_lineage = (
                    consumed.learner_id,
                    consumed.session_id,
                    consumed.fragment_id,
                ) == (proposal.learner_id, proposal.session_id, proposal.fragment_id)
                if same_lineage and consumed.sequence >= proposal.sequence:
                    raise CommitConflict("proposal lineage sequence is not monotonic")
                if same_lineage and (
                    consumed.base_commit_id,
                    consumed.base_fragment_version,
                ) == (proposal.base_commit_id, proposal.base_fragment_version):
                    raise CommitConflict("proposal overlaps a consumed same-base interval")

        current_params = decode_params(
            verified_get(self.backend, current_fragment.params_ref)
        )
        current_outer = decode_outer_state(
            verified_get(self.backend, current_fragment.outer_state_ref)
        )
        output = transition(
            current_params=current_params,
            current_outer_state=current_outer,
            current_fragment_version=current_fragment.version,
            proposals=proposals,
            optimizer_config=self.spec.optimizer_config,
            weighting_config=self.spec.weighting_config,
        )
        _fire(crash_at, "before_params_put")
        params_data = encode_params(output.new_params)
        params_ref = content_ref(
            self.layout.params_key(fragment_id, hashlib.sha256(params_data).hexdigest()),
            params_data,
        )
        self.backend.put_immutable(params_ref.key, params_data, sha256=params_ref.sha256)
        _fire(crash_at, "after_params_put")
        _fire(crash_at, "before_outer_state_put")
        outer_data = encode_outer_state(output.new_outer_state)
        outer_ref = content_ref(
            self.layout.outer_state_key(fragment_id, hashlib.sha256(outer_data).hexdigest()),
            outer_data,
        )
        self.backend.put_immutable(outer_ref.key, outer_data, sha256=outer_ref.sha256)
        _fire(crash_at, "after_outer_state_put")

        weights = dict(output.weights)
        commit = _make_commit(
            {
                "manifest_type": "commit",
                "protocol_version": 2,
                "run_id": self.spec.run_id,
                "run_generation": self.spec.run_generation,
                "commit_seq": replay.head_frontier.commit_seq + 1,
                "parent_commit_id": replay.head_frontier.commit_id,
                "parent_head_version": _logical_head_version(replay.loaded_head.manifest),
                "fencing_epoch": replay.loaded_head.manifest.fencing_epoch,
                "fragment_id": fragment_id,
                "previous_fragment_version": current_fragment.version,
                "new_fragment_version": current_fragment.version + 1,
                "selected_proposals": [
                    ProposalSelection(
                        proposal_id=proposal.proposal_id,
                        learner_id=proposal.learner_id,
                        learner_session_id=proposal.session_id,
                        sequence=proposal.sequence,
                        base_commit_seq=proposal.base_commit_seq,
                        base_fragment_version=proposal.base_fragment_version,
                        target_tokens=proposal.target_tokens,
                        staleness=current_fragment.version
                        - proposal.base_fragment_version,
                        weight_fp64_hex=weights[proposal.proposal_id].hex(),
                    ).to_dict()
                    for proposal in proposals
                ],
                "aggregate_digest": canonical_digest(vector_identity(output.aggregate)),
                "outer_optimizer_impl_digest": self.spec.optimizer_config.digest,
                "new_params_ref": params_ref.to_dict(),
                "new_outer_state_ref": outer_ref.to_dict(),
            }
        )
        _fire(crash_at, "before_commit_put")
        commit_data = canonical_bytes(commit.to_dict())
        commit_ref = content_ref(
            self.layout.commit_key(commit.commit_seq, commit.commit_id), commit_data
        )
        self.backend.put_immutable(commit_ref.key, commit_data, sha256=commit_ref.sha256)
        _fire(crash_at, "after_commit_put")

        fragments = dict(replay.head_frontier.fragments)
        fragments[fragment_id] = FragmentState(
            version=commit.new_fragment_version,
            params_ref=params_ref,
            outer_state_ref=outer_ref,
            producing_commit_id=commit.commit_id,
        )
        frontier = _make_frontier(
            {
                "manifest_type": "frontier",
                "protocol_version": 2,
                "run_id": self.spec.run_id,
                "run_generation": self.spec.run_generation,
                "commit_seq": commit.commit_seq,
                "commit_id": commit.commit_id,
                "parent_frontier_sha256": replay.head_frontier.frontier_sha256,
                "fencing_epoch": commit.fencing_epoch,
                "fragments": {
                    str(key): value.to_dict() for key, value in sorted(fragments.items())
                },
                "scheduler_state": {
                    "next_fragment_cursor": (
                        replay.head_frontier.scheduler_state["next_fragment_cursor"] + 1
                    )
                    % len(fragments)
                },
                "consumed_proposal_ids": sorted(
                    set(replay.head_frontier.consumed_proposal_ids) | set(selected_ids)
                ),
            }
        )
        _fire(crash_at, "before_frontier_put")
        frontier_data = canonical_bytes(frontier.to_dict())
        frontier_ref = content_ref(
            self.layout.frontier_key(frontier.commit_seq, frontier.frontier_sha256),
            frontier_data,
        )
        self.backend.put_immutable(
            frontier_ref.key, frontier_data, sha256=frontier_ref.sha256
        )
        _fire(crash_at, "after_frontier_put")
        new_head = HeadManifest(
            protocol_version=2,
            run_id=self.spec.run_id,
            run_generation=self.spec.run_generation,
            fencing_epoch=commit.fencing_epoch,
            commit_seq=commit.commit_seq,
            commit_id=commit.commit_id,
            frontier_ref=frontier_ref,
        )
        return PreparedLogTransition(
            parent_head=replay.loaded_head,
            commit=commit,
            commit_ref=commit_ref,
            frontier=frontier,
            frontier_ref=frontier_ref,
            new_head=new_head,
            request_id="p04-" + commit.commit_id.removeprefix("c-")[:64],
        )

    def commit_prepared(
        self,
        prepared: PreparedLogTransition,
        *,
        crash_at: str | None = None,
    ) -> CommitResult:
        if crash_at is not None and crash_at not in CRASH_POINTS:
            raise ValueError(f"unknown crash point: {crash_at}")
        resolved = self.resolve_prepared(prepared)
        if resolved is not None:
            return resolved
        _fire(crash_at, "before_head_cas")
        try:
            metadata = self.backend.conditional_replace(
                self.layout.head_key,
                expected_version=prepared.parent_head.metadata.version,
                data=_head_bytes(prepared.new_head),
                request_id=prepared.request_id,
            )
        except PreconditionFailed as exc:
            resolved = self.resolve_prepared(prepared)
            if resolved is not None:
                return resolved
            raise CommitConflict("prepared transition lost the head CAS") from exc
        except InjectedTimeout:
            resolved = self.resolve_prepared(prepared)
            if resolved is not None:
                return resolved
            raise
        _fire(crash_at, "after_head_cas")
        return CommitResult(
            status="committed",
            commit_id=prepared.commit.commit_id,
            commit_seq=prepared.commit.commit_seq,
            head_version=metadata.version,
        )

    def resolve_prepared(self, prepared: PreparedLogTransition) -> CommitResult | None:
        current = self.load_head()
        if current.manifest == prepared.new_head:
            return CommitResult(
                status="already_committed",
                commit_id=prepared.commit.commit_id,
                commit_seq=prepared.commit.commit_seq,
                head_version=current.metadata.version,
            )
        if current.manifest.commit_seq > prepared.commit.commit_seq:
            from .replay import replay_log

            replay = replay_log(self)
            index = prepared.commit.commit_seq - 1
            if (
                0 <= index < len(replay.commits)
                and replay.commits[index] == prepared.commit
                and replay.frontiers[index + 1] == prepared.frontier
            ):
                return CommitResult(
                    status="already_committed",
                    commit_id=prepared.commit.commit_id,
                    commit_seq=prepared.commit.commit_seq,
                    head_version=replay.loaded_head.metadata.version,
                )
        return None

    def commit_transition(
        self,
        *,
        fragment_id: int,
        selected_proposal_ids: Iterable[str],
        crash_at: str | None = None,
    ) -> CommitResult:
        prepared = self.prepare_transition(
            fragment_id=fragment_id,
            selected_proposal_ids=selected_proposal_ids,
            crash_at=crash_at,
        )
        return self.commit_prepared(prepared, crash_at=crash_at)
