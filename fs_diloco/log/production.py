"""Production safetensors transitions committed through the P04 head CAS."""

from __future__ import annotations

import hashlib
from typing import Iterable, Mapping

from fs_diloco.protocol.canonical_json import canonical_bytes, canonical_digest
from fs_diloco.protocol.schemas import (
    CommitManifest,
    ControlCommitManifest,
    CoordinationProjection,
    FragmentState,
    HeadManifest,
    ObjectRef,
    ProposalManifest,
    ProposalSelection,
    StopProjection,
)
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
    ValidatedProductionPayload,
    decode_production_outer_state,
    decode_production_params,
    validate_production_tensor_payload,
)
from .replay import ProductionReplayCache, ReplayResult, replay_log
from .run import RunManifest, RunSpec
from fs_diloco.coordination.state_machine import OwnerToken


class ProductionTransactionalLog:
    """A production tensor adapter whose only authority mutation is head CAS."""

    def __init__(self, transactional: TransactionalLog) -> None:
        if transactional.spec.payload_codec != PRODUCTION_CODEC:
            raise RunInitializationError("run is not a production safetensors generation")
        self.transactional = transactional
        self._replay_cache = ProductionReplayCache.empty()
        self._replay_validation_device = None
        self._owner_token: OwnerToken | None = None

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

    def set_replay_validation_device(self, device) -> None:
        """Select the device used for large finite checks during this process."""

        self._replay_validation_device = device

    def replay(self, *, force_full: bool = False) -> ReplayResult:
        """Replay authority, memoizing only verified immutable tensor objects.

        Manifests and causal rules are checked on every call.  The cache avoids
        rereading and decoding large content-addressed tensors whose complete
        object identity was already verified in this process.
        """

        cache = ProductionReplayCache.empty() if force_full else self._replay_cache
        result = replay_log(
            self.transactional,
            production_cache=cache,
            production_validation_device=self._replay_validation_device,
        )
        if force_full:
            self._replay_cache = cache
        return result

    def clear_owner_state(self) -> None:
        """Discard every process/owner-scoped optimization and tentative fact."""

        self._owner_token = None
        self._replay_cache = ProductionReplayCache.empty()

    @staticmethod
    def _optimizer_transition_count(replay: ReplayResult) -> int:
        coordination = replay.head_frontier.coordination
        if coordination is not None:
            return coordination.optimizer_transition_count
        return sum(isinstance(item, CommitManifest) for item in replay.commits)

    @staticmethod
    def _control_request_body(
        *,
        control_kind: str,
        request_id: str,
        token: OwnerToken,
        parent_commit_id: str,
        stop_reason: str | None = None,
    ) -> dict[str, object]:
        body: dict[str, object] = {
            "operation": control_kind,
            "request_id": request_id,
            "owner_id": token.owner_id,
            "owner_session_id": token.owner_session_id,
            "fencing_epoch": token.fencing_epoch,
            "parent_commit_id": parent_commit_id,
        }
        if stop_reason is not None:
            body["stop_reason"] = stop_reason
        return body

    def prepare_control_transition(
        self,
        *,
        control_kind: str,
        token: OwnerToken,
        request_id: str,
        stop_reason: str | None = None,
        crash_at: str | None = None,
    ) -> PreparedLogTransition:
        """Prepare an epoch-bump or stop fact without changing optimizer state."""

        if self.spec.coordination_protocol != "head-fenced-v1":
            raise CommitConflict("run generation does not enable fenced coordination")
        if control_kind not in {"epoch_bump", "stop"}:
            raise ValueError(f"unsupported control transition: {control_kind}")
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("control request_id must be non-empty")
        replay = self.replay(force_full=True)
        previous = replay.head_frontier
        prior_coordination = previous.coordination
        if previous.coordination is not None and previous.coordination.stop is not None:
            raise CommitConflict("authoritative stop is already committed")
        if control_kind == "epoch_bump":
            if token.fencing_epoch <= previous.fencing_epoch:
                resolved = replay.control_requests.get(request_id)
                if resolved is not None:
                    raise CommitConflict("control request is already committed")
                raise CommitConflict("takeover fencing epoch is not newer")
        else:
            if (
                prior_coordination is None
                or prior_coordination.owner_id != token.owner_id
                or prior_coordination.owner_session_id != token.owner_session_id
                or previous.fencing_epoch != token.fencing_epoch
            ):
                raise CommitConflict("stop requester is not the committed fenced owner")
            if not isinstance(stop_reason, str) or not stop_reason:
                raise ValueError("stop transition requires a non-empty reason")

        request_body = self._control_request_body(
            control_kind=control_kind,
            request_id=request_id,
            token=token,
            parent_commit_id=previous.commit_id,
            stop_reason=stop_reason,
        )
        request_digest = canonical_digest(request_body)
        committed_request = replay.control_requests.get(request_id)
        if committed_request is not None:
            if committed_request[0] != request_digest:
                raise CommitConflict("control request identity conflicts with committed content")
            raise CommitConflict("control request is already committed")
        commit_body: dict[str, object] = {
            "manifest_type": "control_commit",
            "protocol_version": 2,
            "run_id": self.spec.run_id,
            "run_generation": self.spec.run_generation,
            "commit_seq": previous.commit_seq + 1,
            "parent_commit_id": previous.commit_id,
            "parent_head_version": _logical_head_version(replay.loaded_head.manifest),
            "control_kind": control_kind,
            "prior_fencing_epoch": previous.fencing_epoch,
            "fencing_epoch": token.fencing_epoch,
            "owner_id": token.owner_id,
            "owner_session_id": token.owner_session_id,
            "request_id": request_id,
            "request_digest": request_digest,
            "optimizer_transition_count": self._optimizer_transition_count(replay),
        }
        if stop_reason is not None:
            commit_body["stop_reason"] = stop_reason
        commit_body["commit_id"] = "c-" + canonical_digest(commit_body)
        commit = ControlCommitManifest.from_dict(commit_body)

        _fire(crash_at, "before_commit_put")
        commit_data = canonical_bytes(commit.to_dict())
        commit_ref = content_ref(
            self.layout.commit_key(commit.commit_seq, commit.commit_id), commit_data
        )
        self.backend.put_immutable(commit_ref.key, commit_data, sha256=commit_ref.sha256)
        _fire(crash_at, "after_commit_put")
        coordination = CoordinationProjection(
            optimizer_transition_count=commit.optimizer_transition_count,
            owner_id=commit.owner_id,
            owner_session_id=commit.owner_session_id,
            stop=(
                StopProjection(
                    request_id=commit.request_id,
                    request_digest=commit.request_digest,
                    reason=commit.stop_reason or "",
                    committed_at_seq=commit.commit_seq,
                )
                if control_kind == "stop"
                else None
            ),
        )
        frontier = _make_frontier(
            {
                "manifest_type": "frontier",
                "protocol_version": 2,
                "run_id": self.spec.run_id,
                "run_generation": self.spec.run_generation,
                "commit_seq": commit.commit_seq,
                "commit_id": commit.commit_id,
                "parent_frontier_sha256": previous.frontier_sha256,
                "fencing_epoch": commit.fencing_epoch,
                "fragments": {
                    str(key): value.to_dict()
                    for key, value in sorted(previous.fragments.items())
                },
                "scheduler_state": dict(previous.scheduler_state),
                "consumed_proposal_ids": list(previous.consumed_proposal_ids),
                "coordination": coordination.to_dict(),
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
            request_id=request_id,
        )

    def activate_owner(
        self,
        *,
        token: OwnerToken,
        request_id: str,
        crash_at: str | None = None,
    ) -> CommitResult:
        """Strictly replay, commit the ownership epoch, then enable writes."""

        self.clear_owner_state()
        prepared = self.prepare_control_transition(
            control_kind="epoch_bump",
            token=token,
            request_id=request_id,
            crash_at=crash_at,
        )
        result = self.commit_prepared(prepared, crash_at=crash_at)
        verified = self.replay(force_full=True)
        projection = verified.head_frontier.coordination
        if (
            projection is None
            or projection.owner_id != token.owner_id
            or projection.owner_session_id != token.owner_session_id
            or verified.head_frontier.fencing_epoch != token.fencing_epoch
        ):
            raise VerificationError("committed ownership differs after strict replay")
        self._owner_token = token
        return result

    def commit_stop(
        self,
        *,
        reason: str,
        request_id: str,
        crash_at: str | None = None,
    ) -> CommitResult:
        token = self._require_owner_token()
        prepared = self.prepare_control_transition(
            control_kind="stop",
            token=token,
            request_id=request_id,
            stop_reason=reason,
            crash_at=crash_at,
        )
        return self.commit_prepared(prepared, crash_at=crash_at)

    def _require_owner_token(self) -> OwnerToken:
        if self.spec.coordination_protocol != "head-fenced-v1":
            raise CommitConflict("run generation does not require fenced ownership")
        if self._owner_token is None:
            raise CommitConflict("production writer has no activated owner token")
        return self._owner_token

    def publish_proposal(self, proposal: ProposalManifest, payload: bytes) -> ObjectRef:
        if proposal.run_id != self.spec.run_id or proposal.run_generation != self.spec.run_generation:
            raise CommitConflict("proposal belongs to another run generation")
        expected_payload_key = self.layout.proposal_payload_key(proposal.payload_sha256)
        if proposal.payload_key != expected_payload_key:
            raise CommitConflict("proposal payload key is not canonical for its content")
        if len(payload) != proposal.payload_size or hashlib.sha256(payload).hexdigest() != proposal.payload_sha256:
            raise CommitConflict("proposal payload bytes differ from its manifest")
        validated = validate_production_tensor_payload(
            payload,
            tensor_key=proposal.tensor_key,
            shape=proposal.shape,
            dtype=proposal.dtype,
            require_finite=True,
        )
        return self.publish_validated_proposal(proposal, validated)

    def publish_validated_proposal(
        self,
        proposal: ProposalManifest,
        payload: ValidatedProductionPayload,
    ) -> ObjectRef:
        """Publish a codec-validated immutable payload without revalidating its bytes."""

        if proposal.run_id != self.spec.run_id or proposal.run_generation != self.spec.run_generation:
            raise CommitConflict("proposal belongs to another run generation")
        expected_payload_key = self.layout.proposal_payload_key(proposal.payload_sha256)
        if proposal.payload_key != expected_payload_key:
            raise CommitConflict("proposal payload key is not canonical for its content")
        if (
            payload.sha256 != proposal.payload_sha256
            or len(payload.data) != proposal.payload_size
            or payload.tensor_key != proposal.tensor_key
            or payload.shape != proposal.shape
            or payload.dtype != proposal.dtype
            or not payload.finite_checked
        ):
            raise CommitConflict("validated proposal payload differs from its manifest")
        data = proposal.canonical_bytes()
        ref = content_ref(self.layout.proposal_key(proposal.proposal_id), data)
        self.backend.put_immutable(
            proposal.payload_key,
            payload.data,
            sha256=proposal.payload_sha256,
        )
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
        request_id: str | None = None,
        crash_at: str | None = None,
    ) -> PreparedLogTransition:
        replay = self.replay()
        owner_token: OwnerToken | None = None
        if self.spec.coordination_protocol == "head-fenced-v1":
            owner_token = self._require_owner_token()
            coordination = replay.head_frontier.coordination
            if (
                coordination is None
                or coordination.stop is not None
                or coordination.owner_id != owner_token.owner_id
                or coordination.owner_session_id != owner_token.owner_session_id
                or replay.head_frontier.fencing_epoch != owner_token.fencing_epoch
            ):
                raise CommitConflict("activated owner token differs from committed head")
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

        commit_body: dict[str, object] = {
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
        if owner_token is not None:
            if not isinstance(request_id, str) or not request_id:
                raise CommitConflict("fenced optimizer transition requires request_id")
            optimizer_request_body = {
                "operation": "optimizer",
                "request_id": request_id,
                "owner_id": owner_token.owner_id,
                "owner_session_id": owner_token.owner_session_id,
                "fencing_epoch": owner_token.fencing_epoch,
                "parent_commit_id": replay.head_frontier.commit_id,
                "selected_proposal_ids": list(selected_ids),
                "aggregate_digest": aggregate_digest,
            }
            commit_body.update(
                {
                    "owner_id": owner_token.owner_id,
                    "owner_session_id": owner_token.owner_session_id,
                    "request_id": request_id,
                    "request_digest": canonical_digest(optimizer_request_body),
                    "optimizer_transition_count": self._optimizer_transition_count(replay)
                    + 1,
                }
            )
        commit = _make_commit(commit_body)
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
        frontier_body: dict[str, object] = {
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
        if owner_token is not None:
            frontier_body["coordination"] = CoordinationProjection(
                optimizer_transition_count=commit.optimizer_transition_count or 0,
                owner_id=owner_token.owner_id,
                owner_session_id=owner_token.owner_session_id,
            ).to_dict()
        frontier = _make_frontier(frontier_body)
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
            request_id=(
                request_id
                if request_id is not None
                else "m00-" + commit.commit_id.removeprefix("c-")[:64]
            ),
        )

    def commit_prepared(
        self,
        prepared: PreparedLogTransition,
        *,
        crash_at: str | None = None,
    ) -> CommitResult:
        if self.spec.coordination_protocol == "head-fenced-v1":
            current = self.transactional.load_head()
            if current.manifest != prepared.parent_head.manifest:
                resolved = self.resolve_prepared(prepared)
                if resolved is not None:
                    return resolved
                self.clear_owner_state()
                raise CommitConflict("prepared fenced transition lost its parent head")
        result = self.transactional.commit_prepared(prepared, crash_at=crash_at)
        if isinstance(prepared.commit, ControlCommitManifest):
            self._owner_token = OwnerToken(
                owner_id=prepared.commit.owner_id,
                owner_session_id=prepared.commit.owner_session_id,
                fencing_epoch=prepared.commit.fencing_epoch,
            )
        return result

    def resolve_prepared(self, prepared: PreparedLogTransition) -> CommitResult | None:
        return self.transactional.resolve_prepared(prepared)

    def resolve_mutation(self, *, request_id: str, request_digest: str) -> CommitResult | None:
        replay = self.replay(force_full=True)
        observed = replay.control_requests.get(request_id)
        if observed is None:
            return None
        if observed[0] != request_digest:
            raise CommitConflict("mutation request identity conflicts with committed ancestry")
        commit_seq = observed[1]
        commit = replay.commits[commit_seq - 1]
        return CommitResult(
            status="already_committed",
            commit_id=commit.commit_id,
            commit_seq=commit.commit_seq,
            head_version=replay.loaded_head.metadata.version,
        )

    def commit_transition(self, **kwargs) -> CommitResult:
        crash_at = kwargs.get("crash_at")
        prepared = self.prepare_transition(**kwargs)
        return self.commit_prepared(prepared, crash_at=crash_at)


def verify_production_payload_refs(log: TransactionalLog, refs: Iterable[ObjectRef]) -> None:
    for ref in refs:
        verified_get(log.backend, ref)
