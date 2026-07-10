"""Production safetensors transitions committed through the P04 head CAS."""

from __future__ import annotations

import hashlib
from typing import Iterable, Mapping

from fs_diloco.protocol.canonical_json import canonical_bytes, canonical_digest
from fs_diloco.protocol.schemas import (
    FragmentState,
    HeadManifest,
    ObjectRef,
    ProposalManifest,
    ProposalSelection,
)
from fs_diloco.protocol.safetensors_validation import validate_tensor_payload
from fs_diloco.storage import ImmutableConflict, NotFound
from fs_diloco.storage.base import StorageBackend
from fs_diloco.testing.deterministic_reference import normalized_weights

from .codec import content_ref, verified_get
from .commit import (
    CommitResult,
    PreparedLogTransition,
    TransactionalLog,
    _fire,
    _head_bytes,
    _logical_head_version,
    _make_commit,
    _make_frontier,
)
from .errors import CommitConflict, RunInitializationError, VerificationError
from .layout import LogLayout
from .production_codec import (
    PRODUCTION_CODEC,
    decode_production_outer_state,
    decode_production_params,
)
from .replay import replay_log
from .run import RunManifest, RunSpec


class ProductionTransactionalLog:
    """A production tensor adapter whose only authority mutation is head CAS."""

    def __init__(self, transactional: TransactionalLog) -> None:
        if transactional.spec.payload_codec != PRODUCTION_CODEC:
            raise RunInitializationError("run is not a production safetensors generation")
        self.transactional = transactional

    @property
    def backend(self) -> StorageBackend:
        return self.transactional.backend

    @property
    def manifest(self) -> RunManifest:
        return self.transactional.manifest

    @property
    def spec(self) -> RunSpec:
        return self.transactional.spec

    @property
    def layout(self) -> LogLayout:
        return self.transactional.layout

    @classmethod
    def initialize(
        cls,
        backend: StorageBackend,
        spec: RunSpec,
        initial_fragments: Mapping[int, tuple[bytes, bytes]],
    ) -> "ProductionTransactionalLog":
        if spec.payload_codec != PRODUCTION_CODEC:
            raise RunInitializationError(f"production log requires {PRODUCTION_CODEC}")
        if not initial_fragments or sorted(initial_fragments) != list(range(len(initial_fragments))):
            raise RunInitializationError("initial fragments must be contiguous from zero")
        layout = LogLayout(spec.run_id, spec.run_generation)
        fragment_states: dict[int, FragmentState] = {}
        for fragment_id, (params_data, outer_data) in sorted(initial_fragments.items()):
            params = decode_production_params(params_data)
            outer = decode_production_outer_state(outer_data)
            vector_sizes = {
                int(value.numel()) for key, value in outer.items() if key != "step"
            }
            if vector_sizes != {int(params.numel())}:
                raise RunInitializationError("params and outer-state vector sizes differ")
            params_digest = hashlib.sha256(params_data).hexdigest()
            outer_digest = hashlib.sha256(outer_data).hexdigest()
            params_ref = content_ref(
                layout.production_params_key(fragment_id, params_digest), params_data
            )
            outer_ref = content_ref(
                layout.production_outer_state_key(fragment_id, outer_digest), outer_data
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
        genesis_ref = content_ref(layout.frontier_key(0, genesis.frontier_sha256), genesis_data)
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
            backend.put_immutable(genesis_ref.key, genesis_data, sha256=genesis_ref.sha256)
            backend.put_immutable(layout.run_manifest_key, run_manifest.canonical_bytes())
        except ImmutableConflict as exc:
            raise RunInitializationError("run generation conflicts with existing genesis") from exc
        try:
            backend.head(layout.head_key)
        except NotFound:
            try:
                backend.put_if_absent(layout.head_key, _head_bytes(head))
            except ImmutableConflict as exc:
                raise RunInitializationError("run head conflicts with genesis") from exc
        opened = cls.open(backend, spec.run_id, spec.run_generation)
        if opened.spec != spec:
            raise RunInitializationError("existing production run specification differs")
        return opened

    @classmethod
    def open(
        cls,
        backend: StorageBackend,
        run_id: str,
        run_generation: int = 0,
    ) -> "ProductionTransactionalLog":
        return cls(TransactionalLog.open(backend, run_id, run_generation))

    def load_head(self):
        return self.transactional.load_head()

    def publish_proposal(self, proposal: ProposalManifest, payload: bytes) -> ObjectRef:
        if proposal.run_id != self.spec.run_id or proposal.run_generation != self.spec.run_generation:
            raise CommitConflict("proposal belongs to another run generation")
        expected_payload_key = self.layout.proposal_payload_key(proposal.payload_sha256)
        if proposal.payload_key != expected_payload_key:
            raise CommitConflict("proposal payload key is not canonical for its content")
        if len(payload) != proposal.payload_size or hashlib.sha256(payload).hexdigest() != proposal.payload_sha256:
            raise CommitConflict("proposal payload bytes differ from its manifest")
        validate_tensor_payload(
            payload,
            tensor_key=proposal.tensor_key,
            shape=proposal.shape,
            dtype=proposal.dtype,
            require_finite=True,
        )
        data = proposal.canonical_bytes()
        ref = content_ref(self.layout.proposal_key(proposal.proposal_id), data)
        self.backend.put_immutable(proposal.payload_key, payload, sha256=proposal.payload_sha256)
        self.backend.put_immutable(ref.key, data, sha256=ref.sha256)
        return ref

    def read_proposal(self, proposal_id: str, *, commit_seq: int | None = None) -> ProposalManifest:
        try:
            data = self.backend.get(self.layout.proposal_key(proposal_id))
            from fs_diloco.protocol.manifests import load_manifest_bytes

            manifest = load_manifest_bytes(data)
        except Exception as exc:
            raise VerificationError(
                f"cannot read production proposal {proposal_id}: {exc}",
                commit_seq=commit_seq,
            ) from exc
        if not isinstance(manifest, ProposalManifest) or manifest.proposal_id != proposal_id:
            raise VerificationError("production proposal identity mismatch", commit_seq=commit_seq)
        return manifest

    def prepare_transition(
        self,
        *,
        fragment_id: int,
        selected_proposal_ids: Iterable[str],
        new_params: bytes,
        new_outer_state: bytes,
        aggregate_digest: str,
        outer_optimizer_impl_digest: str,
        crash_at: str | None = None,
    ) -> PreparedLogTransition:
        replay = replay_log(self.transactional)
        selected_ids = tuple(sorted(set(selected_proposal_ids)))
        if not selected_ids:
            raise CommitConflict("cannot commit an empty proposal selection")
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
            if proposal.base_frontier_digest != base.frontier_sha256:
                raise CommitConflict("proposal base frontier digest mismatch")
            base_fragment = base.fragments.get(fragment_id)
            if base_fragment is None or base_fragment.version != proposal.base_fragment_version:
                raise CommitConflict("proposal base fragment version mismatch")
            if replay.head_frontier.commit_seq - base.commit_seq > self.spec.max_global_staleness:
                raise CommitConflict("proposal exceeds global staleness")
            if current_fragment.version - proposal.base_fragment_version > self.spec.max_fragment_staleness:
                raise CommitConflict("proposal exceeds fragment staleness")
            for consumed in replay.proposals.values():
                consumed_session = getattr(
                    consumed,
                    "learner_session_id",
                    getattr(consumed, "session_id", None),
                )
                same_lineage = (
                    consumed.learner_id,
                    consumed_session,
                    consumed.fragment_id,
                ) == (
                    proposal.learner_id,
                    proposal.learner_session_id,
                    proposal.fragment_id,
                )
                if same_lineage and consumed.sequence >= proposal.sequence:
                    raise CommitConflict("proposal lineage sequence is not monotonic")
                if same_lineage and (
                    consumed.base_commit_id,
                    consumed.base_fragment_version,
                ) == (
                    proposal.base_commit_id,
                    proposal.base_fragment_version,
                ):
                    raise CommitConflict("proposal overlaps a consumed same-base interval")

        weights = normalized_weights(
            {item.proposal_id: item.target_tokens_since_base for item in proposals},
            staleness={
                item.proposal_id: current_fragment.version - item.base_fragment_version
                for item in proposals
            },
            config=self.spec.weighting_config,
        )
        _fire(crash_at, "before_params_put")
        params = decode_production_params(new_params)
        params_digest = hashlib.sha256(new_params).hexdigest()
        params_ref = content_ref(
            self.layout.production_params_key(fragment_id, params_digest), new_params
        )
        self.backend.put_immutable(params_ref.key, new_params, sha256=params_ref.sha256)
        _fire(crash_at, "after_params_put")
        _fire(crash_at, "before_outer_state_put")
        outer = decode_production_outer_state(new_outer_state)
        vector_sizes = {int(value.numel()) for key, value in outer.items() if key != "step"}
        if vector_sizes != {int(params.numel())}:
            raise CommitConflict("new params and outer-state vector sizes differ")
        outer_digest = hashlib.sha256(new_outer_state).hexdigest()
        outer_ref = content_ref(
            self.layout.production_outer_state_key(fragment_id, outer_digest), new_outer_state
        )
        self.backend.put_immutable(outer_ref.key, new_outer_state, sha256=outer_ref.sha256)
        _fire(crash_at, "after_outer_state_put")

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
                        proposal_id=item.proposal_id,
                        learner_id=item.learner_id,
                        learner_session_id=item.learner_session_id,
                        sequence=item.sequence,
                        base_commit_seq=item.base_commit_seq,
                        base_fragment_version=item.base_fragment_version,
                        target_tokens=item.target_tokens_since_base,
                        staleness=current_fragment.version - item.base_fragment_version,
                        weight_fp64_hex=weights[item.proposal_id].hex(),
                    ).to_dict()
                    for item in proposals
                ],
                "aggregate_digest": aggregate_digest,
                "outer_optimizer_impl_digest": outer_optimizer_impl_digest,
                "new_params_ref": params_ref.to_dict(),
                "new_outer_state_ref": outer_ref.to_dict(),
            }
        )
        _fire(crash_at, "before_commit_put")
        commit_data = canonical_bytes(commit.to_dict())
        commit_ref = content_ref(self.layout.commit_key(commit.commit_seq, commit.commit_id), commit_data)
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
        self.backend.put_immutable(frontier_ref.key, frontier_data, sha256=frontier_ref.sha256)
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
            request_id="m00-" + commit.commit_id.removeprefix("c-")[:64],
        )

    def commit_prepared(
        self,
        prepared: PreparedLogTransition,
        *,
        crash_at: str | None = None,
    ) -> CommitResult:
        return self.transactional.commit_prepared(prepared, crash_at=crash_at)

    def resolve_prepared(self, prepared: PreparedLogTransition) -> CommitResult | None:
        return self.transactional.resolve_prepared(prepared)

    def commit_transition(self, **kwargs) -> CommitResult:
        crash_at = kwargs.get("crash_at")
        prepared = self.prepare_transition(**kwargs)
        return self.commit_prepared(prepared, crash_at=crash_at)


def verify_production_payload_refs(log: TransactionalLog, refs: Iterable[ObjectRef]) -> None:
    for ref in refs:
        verified_get(log.backend, ref)
