"""Verify and replay the authoritative committed prefix from the current head."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from fs_diloco.optimizer.reference_adapter import transition
from fs_diloco.protocol.canonical_json import canonical_bytes, canonical_digest
from fs_diloco.protocol.schemas import (
    CommitManifest,
    CommittedManifest,
    ControlCommitManifest,
    FrontierManifest,
    HeadManifest,
    ObjectRef,
    StopProjection,
)
from fs_diloco.protocol.manifests import load_manifest_bytes
from fs_diloco.protocol.schemas import ProposalManifest
from fs_diloco.testing.deterministic_reference import normalized_weights
from fs_diloco.testing.deterministic_reference import vector_identity

from .codec import (
    canonical_object,
    content_ref,
    decode_outer_state,
    decode_params,
    verified_get,
)
from .commit import LoadedHead, TransactionalLog
from .errors import VerificationError


@dataclass(frozen=True)
class ReplayResult:
    loaded_head: LoadedHead
    frontiers: tuple[FrontierManifest, ...]
    commits: tuple[CommittedManifest, ...]
    proposals: dict[str, object]
    consumption: dict[str, int]
    prefix_digests: tuple[str, ...]
    committed_state_digest: str
    reachable_keys: frozenset[str]
    control_requests: dict[str, tuple[str, int]]

    @property
    def head_frontier(self) -> FrontierManifest:
        return self.frontiers[-1]

    @property
    def frontier_by_commit(self) -> dict[str, FrontierManifest]:
        return {frontier.commit_id: frontier for frontier in self.frontiers}


@dataclass(frozen=True)
class OrphanReport:
    committed_reachable: tuple[str, ...]
    prepared_orphans: tuple[str, ...]
    uncommitted_proposals: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "committed_reachable_count": len(self.committed_reachable),
            "prepared_orphan_count": len(self.prepared_orphans),
            "uncommitted_proposal_count": len(self.uncommitted_proposals),
            "prepared_orphans": list(self.prepared_orphans),
            "uncommitted_proposals": list(self.uncommitted_proposals),
        }


@dataclass
class ProductionReplayCache:
    """Process-local memoization of verified immutable production tensors."""

    proposal_payloads: set[tuple[str, str, int]]
    params_numels: dict[tuple[str, str, int], int]
    outer_numels: dict[tuple[str, str, int], frozenset[int]]

    @classmethod
    def empty(cls) -> "ProductionReplayCache":
        return cls(set(), {}, {})


def _ref_identity(ref: ObjectRef) -> tuple[str, str, int]:
    return (ref.key, ref.sha256, ref.size)


def _parse_frontier(data: bytes, *, commit_seq: int) -> FrontierManifest:
    try:
        return FrontierManifest.from_dict(canonical_object(data, commit_seq=commit_seq))
    except VerificationError:
        raise
    except Exception as exc:
        raise VerificationError(f"invalid frontier: {exc}", commit_seq=commit_seq) from exc


def _parse_commit(data: bytes, *, commit_seq: int) -> CommittedManifest:
    try:
        payload = canonical_object(data, commit_seq=commit_seq)
        manifest_type = payload.get("manifest_type")
        if manifest_type == CommitManifest.MANIFEST_TYPE:
            return CommitManifest.from_dict(payload)
        if manifest_type == ControlCommitManifest.MANIFEST_TYPE:
            return ControlCommitManifest.from_dict(payload)
        raise ValueError(f"unsupported committed manifest type: {manifest_type!r}")
    except VerificationError:
        raise
    except Exception as exc:
        raise VerificationError(f"invalid commit: {exc}", commit_seq=commit_seq) from exc


def _direct_get(log: TransactionalLog, key: str, *, commit_seq: int) -> bytes:
    try:
        return log.backend.get(key)
    except Exception as exc:
        raise VerificationError(
            f"cannot read committed object {key}: {exc}", commit_seq=commit_seq
        ) from exc


def _logical_head_version(head: HeadManifest) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(head.to_dict())).hexdigest()


def _prefix_digest(
    log: TransactionalLog,
    head: HeadManifest,
    frontiers: tuple[FrontierManifest, ...],
    commits: tuple[CommittedManifest, ...],
) -> str:
    return canonical_digest(
        {
            "spec_digest": log.spec.digest,
            "head": head.to_dict(),
            "frontiers": [frontier.to_dict() for frontier in frontiers],
            "commits": [commit.to_dict() for commit in commits],
        }
    )


def _replay_reference_log(log: TransactionalLog) -> ReplayResult:
    loaded_head = log.load_head()
    head = loaded_head.manifest
    try:
        current_data = verified_get(
            log.backend, head.frontier_ref, commit_seq=head.commit_seq
        )
    except VerificationError:
        raise
    current = _parse_frontier(current_data, commit_seq=head.commit_seq)
    expected_head_key = log.layout.frontier_key(
        current.commit_seq, current.frontier_sha256
    )
    if head.frontier_ref.key != expected_head_key:
        raise VerificationError("head frontier key is not canonical", commit_seq=head.commit_seq)
    if (
        head.commit_seq != current.commit_seq
        or head.commit_id != current.commit_id
        or head.fencing_epoch != current.fencing_epoch
    ):
        raise VerificationError("head and frontier identity differ", commit_seq=head.commit_seq)

    reversed_frontiers = [current]
    reversed_frontier_data = [current_data]
    reversed_commits: list[CommittedManifest] = []
    while current.commit_seq > 0:
        seq = current.commit_seq
        commit_key = log.layout.commit_key(seq, current.commit_id)
        commit = _parse_commit(_direct_get(log, commit_key, commit_seq=seq), commit_seq=seq)
        reversed_commits.append(commit)
        parent_digest = current.parent_frontier_sha256
        if parent_digest is None:
            raise VerificationError("non-genesis frontier has no parent", commit_seq=seq)
        parent_key = log.layout.frontier_key(seq - 1, parent_digest)
        parent_data = _direct_get(log, parent_key, commit_seq=seq - 1)
        parent = _parse_frontier(parent_data, commit_seq=seq - 1)
        if parent.frontier_sha256 != parent_digest:
            raise VerificationError("parent frontier digest mismatch", commit_seq=seq)
        reversed_frontiers.append(parent)
        reversed_frontier_data.append(parent_data)
        current = parent

    frontiers = tuple(reversed(reversed_frontiers))
    frontier_data = tuple(reversed(reversed_frontier_data))
    commits = tuple(reversed(reversed_commits))
    genesis = frontiers[0]
    if (
        genesis.commit_seq != 0
        or genesis.parent_frontier_sha256 is not None
        or genesis.commit_id != log.manifest.genesis_commit_id
        or content_ref(log.layout.frontier_key(0, genesis.frontier_sha256), frontier_data[0])
        != log.manifest.genesis_frontier_ref
    ):
        raise VerificationError("genesis root differs from the run manifest", commit_seq=0)
    if len(commits) + 1 != len(frontiers):
        raise VerificationError("commit/frontier prefix lengths differ")

    proposals: dict[str, object] = {}
    consumption: dict[str, int] = {}
    last_lineage_sequence: dict[tuple[str, str, int], int] = {}
    consumed_interval_bases: set[tuple[str, str, int, str, int]] = set()
    reachable = {
        log.layout.run_manifest_key,
        log.layout.head_key,
        *(log.layout.frontier_key(item.commit_seq, item.frontier_sha256) for item in frontiers),
    }
    frontier_by_commit = {genesis.commit_id: genesis}
    prefix_digests: list[str] = []
    genesis_head = HeadManifest(
        protocol_version=2,
        run_id=log.spec.run_id,
        run_generation=log.spec.run_generation,
        fencing_epoch=genesis.fencing_epoch,
        commit_seq=0,
        commit_id=genesis.commit_id,
        frontier_ref=content_ref(
            log.layout.frontier_key(0, genesis.frontier_sha256), frontier_data[0]
        ),
    )
    prefix_digests.append(_prefix_digest(log, genesis_head, frontiers[:1], ()))
    for fragment in genesis.fragments.values():
        reachable.update((fragment.params_ref.key, fragment.outer_state_ref.key))
        try:
            decode_params(verified_get(log.backend, fragment.params_ref, commit_seq=0))
            decode_outer_state(
                verified_get(log.backend, fragment.outer_state_ref, commit_seq=0)
            )
        except VerificationError:
            raise
        except Exception as exc:
            raise VerificationError(f"invalid genesis payload: {exc}", commit_seq=0) from exc

    for index, commit in enumerate(commits, start=1):
        if not isinstance(commit, CommitManifest):
            raise VerificationError(
                "reference-codec run cannot contain control commits", commit_seq=index
            )
        previous = frontiers[index - 1]
        frontier = frontiers[index]
        if commit.commit_seq != index or frontier.commit_seq != index:
            raise VerificationError("commit sequence is not contiguous", commit_seq=index)
        if commit.commit_id != frontier.commit_id:
            raise VerificationError("commit/frontier IDs differ", commit_seq=index)
        if commit.parent_commit_id != previous.commit_id:
            raise VerificationError("commit parent chain is not contiguous", commit_seq=index)
        if (
            commit.run_id != log.spec.run_id
            or commit.run_generation != log.spec.run_generation
            or frontier.run_id != log.spec.run_id
            or frontier.run_generation != log.spec.run_generation
        ):
            raise VerificationError("committed object run identity mismatch", commit_seq=index)
        prior_ref = content_ref(
            log.layout.frontier_key(previous.commit_seq, previous.frontier_sha256),
            frontier_data[index - 1],
        )
        prior_head = HeadManifest(
            protocol_version=2,
            run_id=log.spec.run_id,
            run_generation=log.spec.run_generation,
            fencing_epoch=previous.fencing_epoch,
            commit_seq=previous.commit_seq,
            commit_id=previous.commit_id,
            frontier_ref=prior_ref,
        )
        if commit.parent_head_version != _logical_head_version(prior_head):
            raise VerificationError("commit logical parent-head token mismatch", commit_seq=index)
        if frontier.parent_frontier_sha256 != previous.frontier_sha256:
            raise VerificationError("frontier parent chain is not contiguous", commit_seq=index)
        if commit.fragment_id not in previous.fragments:
            raise VerificationError("commit targets an unknown fragment", commit_seq=index)
        old_fragment = previous.fragments[commit.fragment_id]
        if (
            commit.previous_fragment_version != old_fragment.version
            or commit.new_fragment_version != old_fragment.version + 1
        ):
            raise VerificationError("fragment version transition is invalid", commit_seq=index)
        selected_ids = [selection.proposal_id for selection in commit.selected_proposals]
        if selected_ids != sorted(selected_ids):
            raise VerificationError("commit selections are not canonical", commit_seq=index)
        if set(selected_ids) & set(consumption):
            raise VerificationError("proposal is included more than once", commit_seq=index)
        selected = []
        for selection in commit.selected_proposals:
            proposal = log.read_proposal(selection.proposal_id, commit_seq=index)
            base = frontier_by_commit.get(proposal.base_commit_id)
            if base is None or base.commit_seq != proposal.base_commit_seq:
                raise VerificationError("proposal causal base is invalid", commit_seq=index)
            base_fragment = base.fragments.get(commit.fragment_id)
            if (
                proposal.fragment_id != commit.fragment_id
                or base_fragment is None
                or base_fragment.version != proposal.base_fragment_version
            ):
                raise VerificationError("proposal fragment base is invalid", commit_seq=index)
            if previous.commit_seq - proposal.base_commit_seq > log.spec.max_global_staleness:
                raise VerificationError("proposal exceeds global staleness", commit_seq=index)
            if (
                old_fragment.version - proposal.base_fragment_version
                > log.spec.max_fragment_staleness
            ):
                raise VerificationError("proposal exceeds fragment staleness", commit_seq=index)
            lineage = (proposal.learner_id, proposal.session_id, proposal.fragment_id)
            prior_sequence = last_lineage_sequence.get(lineage)
            if prior_sequence is not None and proposal.sequence <= prior_sequence:
                raise VerificationError(
                    "committed proposal lineage is not monotonic", commit_seq=index
                )
            interval_base = (
                *lineage,
                proposal.base_commit_id,
                proposal.base_fragment_version,
            )
            if interval_base in consumed_interval_bases:
                raise VerificationError(
                    "same-base learner interval is consumed twice", commit_seq=index
                )
            expected_selection = {
                "proposal_id": proposal.proposal_id,
                "learner_id": proposal.learner_id,
                "learner_session_id": proposal.session_id,
                "sequence": proposal.sequence,
                "base_commit_seq": proposal.base_commit_seq,
                "base_fragment_version": proposal.base_fragment_version,
                "target_tokens": proposal.target_tokens,
                "staleness": old_fragment.version - proposal.base_fragment_version,
                "weight_fp64_hex": selection.weight_fp64_hex,
            }
            if selection.to_dict() != expected_selection:
                raise VerificationError("proposal selection metadata mismatch", commit_seq=index)
            selected.append(proposal)
            last_lineage_sequence[lineage] = proposal.sequence
            consumed_interval_bases.add(interval_base)

        try:
            old_params = decode_params(
                verified_get(log.backend, old_fragment.params_ref, commit_seq=index)
            )
            old_outer = decode_outer_state(
                verified_get(log.backend, old_fragment.outer_state_ref, commit_seq=index)
            )
            output = transition(
                current_params=old_params,
                current_outer_state=old_outer,
                current_fragment_version=old_fragment.version,
                proposals=selected,
                optimizer_config=log.spec.optimizer_config,
                weighting_config=log.spec.weighting_config,
            )
        except VerificationError:
            raise
        except Exception as exc:
            raise VerificationError(f"reference transition failed: {exc}", commit_seq=index) from exc
        weights = dict(output.weights)
        if any(
            item.weight_fp64_hex != weights[item.proposal_id].hex()
            for item in commit.selected_proposals
        ):
            raise VerificationError("committed weights differ from the oracle", commit_seq=index)
        if commit.aggregate_digest != canonical_digest(vector_identity(output.aggregate)):
            raise VerificationError("aggregate digest differs from the oracle", commit_seq=index)
        if commit.outer_optimizer_impl_digest != log.spec.optimizer_config.digest:
            raise VerificationError("optimizer implementation digest mismatch", commit_seq=index)
        try:
            new_params = decode_params(
                verified_get(log.backend, commit.new_params_ref, commit_seq=index)
            )
            new_outer = decode_outer_state(
                verified_get(log.backend, commit.new_outer_state_ref, commit_seq=index)
            )
        except VerificationError:
            raise
        except Exception as exc:
            raise VerificationError(f"invalid transition payload: {exc}", commit_seq=index) from exc
        if new_params != output.new_params or new_outer != output.new_outer_state:
            raise VerificationError("committed outputs differ from the oracle", commit_seq=index)
        expected_fragments = dict(previous.fragments)
        expected_fragments[commit.fragment_id] = type(old_fragment)(
            version=commit.new_fragment_version,
            params_ref=commit.new_params_ref,
            outer_state_ref=commit.new_outer_state_ref,
            producing_commit_id=commit.commit_id,
        )
        if dict(frontier.fragments) != expected_fragments:
            raise VerificationError("frontier exposes a partial or extra fragment change", commit_seq=index)
        expected_consumed = tuple(sorted(set(previous.consumed_proposal_ids) | set(selected_ids)))
        if frontier.consumed_proposal_ids != expected_consumed:
            raise VerificationError("frontier consumption set mismatch", commit_seq=index)
        expected_cursor = (previous.scheduler_state["next_fragment_cursor"] + 1) % len(
            previous.fragments
        )
        if frontier.scheduler_state["next_fragment_cursor"] != expected_cursor:
            raise VerificationError("frontier scheduler state mismatch", commit_seq=index)
        if frontier.fencing_epoch != commit.fencing_epoch:
            raise VerificationError("frontier fencing epoch mismatch", commit_seq=index)

        commit_key = log.layout.commit_key(commit.commit_seq, commit.commit_id)
        reachable.add(commit_key)
        reachable.update((commit.new_params_ref.key, commit.new_outer_state_ref.key))
        for proposal in selected:
            proposals[proposal.proposal_id] = proposal
            consumption[proposal.proposal_id] = index
            reachable.add(log.layout.proposal_key(proposal.proposal_id))
        frontier_by_commit[frontier.commit_id] = frontier
        prefix_head = HeadManifest(
            protocol_version=2,
            run_id=log.spec.run_id,
            run_generation=log.spec.run_generation,
            fencing_epoch=frontier.fencing_epoch,
            commit_seq=frontier.commit_seq,
            commit_id=frontier.commit_id,
            frontier_ref=content_ref(
                log.layout.frontier_key(frontier.commit_seq, frontier.frontier_sha256),
                frontier_data[index],
            ),
        )
        prefix_digests.append(
            _prefix_digest(log, prefix_head, frontiers[: index + 1], commits[:index])
        )

    return ReplayResult(
        loaded_head=loaded_head,
        frontiers=frontiers,
        commits=commits,
        proposals=proposals,
        consumption=consumption,
        prefix_digests=tuple(prefix_digests),
        committed_state_digest=prefix_digests[-1],
        reachable_keys=frozenset(reachable),
        control_requests={},
    )


def _read_production_proposal(
    log: TransactionalLog,
    proposal_id: str,
    *,
    commit_seq: int,
) -> ProposalManifest:
    try:
        manifest = load_manifest_bytes(log.backend.get(log.layout.proposal_key(proposal_id)))
    except Exception as exc:
        raise VerificationError(
            f"cannot read production proposal {proposal_id}: {exc}", commit_seq=commit_seq
        ) from exc
    if not isinstance(manifest, ProposalManifest) or manifest.proposal_id != proposal_id:
        raise VerificationError("production proposal identity mismatch", commit_seq=commit_seq)
    return manifest


def _optimizer_count(frontier: FrontierManifest) -> int:
    coordination = frontier.coordination
    return (
        coordination.optimizer_transition_count
        if coordination is not None
        else frontier.commit_seq
    )


def _verify_control_transition(
    *,
    previous: FrontierManifest,
    frontier: FrontierManifest,
    commit: ControlCommitManifest,
    control_requests: dict[str, tuple[str, int]],
) -> None:
    if previous.coordination is not None and previous.coordination.stop is not None:
        raise VerificationError(
            "control transition is forbidden after authoritative stop",
            commit_seq=commit.commit_seq,
        )
    prior_request = control_requests.get(commit.request_id)
    if prior_request is not None:
        raise VerificationError(
            "control request identity appears more than once in committed ancestry",
            commit_seq=commit.commit_seq,
        )
    request_body: dict[str, object] = {
        "operation": commit.control_kind,
        "request_id": commit.request_id,
        "owner_id": commit.owner_id,
        "owner_session_id": commit.owner_session_id,
        "fencing_epoch": commit.fencing_epoch,
        "parent_commit_id": commit.parent_commit_id,
    }
    if commit.stop_reason is not None:
        request_body["stop_reason"] = commit.stop_reason
    if commit.request_digest != canonical_digest(request_body):
        raise VerificationError(
            "control request digest differs from canonical content",
            commit_seq=commit.commit_seq,
        )
    if commit.prior_fencing_epoch != previous.fencing_epoch:
        raise VerificationError(
            "control commit prior fencing epoch differs from its parent",
            commit_seq=commit.commit_seq,
        )
    if dict(frontier.fragments) != dict(previous.fragments):
        raise VerificationError(
            "control transition changed parameter or outer state",
            commit_seq=commit.commit_seq,
        )
    if frontier.scheduler_state != previous.scheduler_state:
        raise VerificationError(
            "control transition changed scheduler state", commit_seq=commit.commit_seq
        )
    if frontier.consumed_proposal_ids != previous.consumed_proposal_ids:
        raise VerificationError(
            "control transition changed proposal consumption",
            commit_seq=commit.commit_seq,
        )
    projection = frontier.coordination
    if projection is None:
        raise VerificationError(
            "control transition frontier has no coordination projection",
            commit_seq=commit.commit_seq,
        )
    if (
        projection.optimizer_transition_count != commit.optimizer_transition_count
        or projection.optimizer_transition_count != _optimizer_count(previous)
        or projection.owner_id != commit.owner_id
        or projection.owner_session_id != commit.owner_session_id
        or frontier.fencing_epoch != commit.fencing_epoch
    ):
        raise VerificationError(
            "control transition projection differs from committed control fact",
            commit_seq=commit.commit_seq,
        )
    if commit.control_kind == "epoch_bump":
        if commit.fencing_epoch <= previous.fencing_epoch or projection.stop is not None:
            raise VerificationError(
                "epoch bump is not a monotonic running-owner transition",
                commit_seq=commit.commit_seq,
            )
    elif commit.control_kind == "stop":
        prior = previous.coordination
        if (
            prior is None
            or prior.owner_id != commit.owner_id
            or prior.owner_session_id != commit.owner_session_id
            or commit.fencing_epoch != previous.fencing_epoch
        ):
            raise VerificationError(
                "stop was not issued by the current fenced owner",
                commit_seq=commit.commit_seq,
            )
        expected_stop = StopProjection(
            request_id=commit.request_id,
            request_digest=commit.request_digest,
            reason=commit.stop_reason or "",
            committed_at_seq=commit.commit_seq,
        )
        if projection.stop != expected_stop:
            raise VerificationError(
                "stop projection differs from control commit",
                commit_seq=commit.commit_seq,
            )
    control_requests[commit.request_id] = (
        commit.request_digest,
        commit.commit_seq,
    )


def _replay_production_log(
    log: TransactionalLog,
    *,
    cache: ProductionReplayCache | None = None,
    validation_device: Any = None,
) -> ReplayResult:
    from .production_codec import (
        PRODUCTION_CODEC,
        decode_production_outer_state,
        decode_production_params,
        production_optimizer_digest,
        validate_production_tensor_payload,
    )

    if log.spec.payload_codec != PRODUCTION_CODEC:
        raise VerificationError("production replay received the wrong payload codec")
    cached_proposals = set(cache.proposal_payloads) if cache is not None else set()
    cached_params = dict(cache.params_numels) if cache is not None else {}
    cached_outer = dict(cache.outer_numels) if cache is not None else {}
    loaded_head = log.load_head()
    head = loaded_head.manifest
    current_data = verified_get(log.backend, head.frontier_ref, commit_seq=head.commit_seq)
    current = _parse_frontier(current_data, commit_seq=head.commit_seq)
    expected_head_key = log.layout.frontier_key(current.commit_seq, current.frontier_sha256)
    if head.frontier_ref.key != expected_head_key:
        raise VerificationError("head frontier key is not canonical", commit_seq=head.commit_seq)
    if (
        head.commit_seq != current.commit_seq
        or head.commit_id != current.commit_id
        or head.fencing_epoch != current.fencing_epoch
    ):
        raise VerificationError("head and frontier identity differ", commit_seq=head.commit_seq)

    reversed_frontiers = [current]
    reversed_frontier_data = [current_data]
    reversed_commits: list[CommittedManifest] = []
    while current.commit_seq > 0:
        seq = current.commit_seq
        commit = _parse_commit(
            _direct_get(log, log.layout.commit_key(seq, current.commit_id), commit_seq=seq),
            commit_seq=seq,
        )
        reversed_commits.append(commit)
        parent_digest = current.parent_frontier_sha256
        if parent_digest is None:
            raise VerificationError("non-genesis frontier has no parent", commit_seq=seq)
        parent_data = _direct_get(
            log,
            log.layout.frontier_key(seq - 1, parent_digest),
            commit_seq=seq - 1,
        )
        parent = _parse_frontier(parent_data, commit_seq=seq - 1)
        if parent.frontier_sha256 != parent_digest:
            raise VerificationError("parent frontier digest mismatch", commit_seq=seq)
        reversed_frontiers.append(parent)
        reversed_frontier_data.append(parent_data)
        current = parent

    frontiers = tuple(reversed(reversed_frontiers))
    frontier_data = tuple(reversed(reversed_frontier_data))
    commits = tuple(reversed(reversed_commits))
    genesis = frontiers[0]
    if (
        genesis.commit_seq != 0
        or genesis.parent_frontier_sha256 is not None
        or genesis.commit_id != log.manifest.genesis_commit_id
        or content_ref(log.layout.frontier_key(0, genesis.frontier_sha256), frontier_data[0])
        != log.manifest.genesis_frontier_ref
    ):
        raise VerificationError("genesis root differs from the run manifest", commit_seq=0)
    if len(commits) + 1 != len(frontiers):
        raise VerificationError("commit/frontier prefix lengths differ")

    proposals: dict[str, object] = {}
    consumption: dict[str, int] = {}
    control_requests: dict[str, tuple[str, int]] = {}
    last_lineage_sequence: dict[tuple[str, str, int], int] = {}
    consumed_interval_bases: set[tuple[str, str, int, str, int]] = set()
    reachable = {
        log.layout.run_manifest_key,
        log.layout.head_key,
        *(log.layout.frontier_key(item.commit_seq, item.frontier_sha256) for item in frontiers),
    }
    frontier_by_commit = {genesis.commit_id: genesis}
    prefix_digests: list[str] = []
    genesis_head = HeadManifest(
        protocol_version=2,
        run_id=log.spec.run_id,
        run_generation=log.spec.run_generation,
        fencing_epoch=genesis.fencing_epoch,
        commit_seq=0,
        commit_id=genesis.commit_id,
        frontier_ref=content_ref(
            log.layout.frontier_key(0, genesis.frontier_sha256), frontier_data[0]
        ),
    )
    prefix_digests.append(_prefix_digest(log, genesis_head, frontiers[:1], ()))
    for fragment in genesis.fragments.values():
        reachable.update((fragment.params_ref.key, fragment.outer_state_ref.key))
        params_key = _ref_identity(fragment.params_ref)
        outer_key = _ref_identity(fragment.outer_state_ref)
        params_numel = cached_params.get(params_key)
        if params_numel is None:
            params = decode_production_params(
                verified_get(log.backend, fragment.params_ref, commit_seq=0)
            )
            params_numel = int(params.numel())
            cached_params[params_key] = params_numel
        outer_numels = cached_outer.get(outer_key)
        if outer_numels is None:
            outer = decode_production_outer_state(
                verified_get(log.backend, fragment.outer_state_ref, commit_seq=0)
            )
            outer_numels = frozenset(
                int(item.numel()) for key, item in outer.items() if key != "step"
            )
            cached_outer[outer_key] = outer_numels
        if outer_numels != {params_numel}:
            raise VerificationError("genesis params/outer-state size mismatch", commit_seq=0)

    expected_impl = production_optimizer_digest(log.spec.optimizer_config.identity())
    for index, commit in enumerate(commits, start=1):
        previous = frontiers[index - 1]
        frontier = frontiers[index]
        if commit.commit_seq != index or frontier.commit_seq != index:
            raise VerificationError("commit sequence is not contiguous", commit_seq=index)
        if commit.commit_id != frontier.commit_id:
            raise VerificationError("commit/frontier IDs differ", commit_seq=index)
        if commit.parent_commit_id != previous.commit_id:
            raise VerificationError("commit parent chain is not contiguous", commit_seq=index)
        if (
            commit.run_id != log.spec.run_id
            or commit.run_generation != log.spec.run_generation
            or frontier.run_id != log.spec.run_id
            or frontier.run_generation != log.spec.run_generation
        ):
            raise VerificationError("committed object run identity mismatch", commit_seq=index)
        prior_ref = content_ref(
            log.layout.frontier_key(previous.commit_seq, previous.frontier_sha256),
            frontier_data[index - 1],
        )
        prior_head = HeadManifest(
            protocol_version=2,
            run_id=log.spec.run_id,
            run_generation=log.spec.run_generation,
            fencing_epoch=previous.fencing_epoch,
            commit_seq=previous.commit_seq,
            commit_id=previous.commit_id,
            frontier_ref=prior_ref,
        )
        if commit.parent_head_version != _logical_head_version(prior_head):
            raise VerificationError("commit logical parent-head token mismatch", commit_seq=index)
        if frontier.parent_frontier_sha256 != previous.frontier_sha256:
            raise VerificationError("frontier parent chain is not contiguous", commit_seq=index)
        if isinstance(commit, ControlCommitManifest):
            if log.spec.coordination_protocol not in {"head-fenced-v1", "distributed-head-fenced-v1"}:
                raise VerificationError(
                    "run contract does not allow control commits", commit_seq=index
                )
            _verify_control_transition(
                previous=previous,
                frontier=frontier,
                commit=commit,
                control_requests=control_requests,
            )
            reachable.add(log.layout.commit_key(commit.commit_seq, commit.commit_id))
            frontier_by_commit[frontier.commit_id] = frontier
            prefix_head = HeadManifest(
                protocol_version=2,
                run_id=log.spec.run_id,
                run_generation=log.spec.run_generation,
                fencing_epoch=frontier.fencing_epoch,
                commit_seq=frontier.commit_seq,
                commit_id=frontier.commit_id,
                frontier_ref=content_ref(
                    log.layout.frontier_key(
                        frontier.commit_seq, frontier.frontier_sha256
                    ),
                    frontier_data[index],
                ),
            )
            prefix_digests.append(
                _prefix_digest(
                    log, prefix_head, frontiers[: index + 1], commits[:index]
                )
            )
            continue
        if not isinstance(commit, CommitManifest):
            raise VerificationError("unknown committed transition type", commit_seq=index)
        if log.spec.coordination_protocol in {"head-fenced-v1", "distributed-head-fenced-v1"}:
            prior_coordination = previous.coordination
            if prior_coordination is None or prior_coordination.stop is not None:
                raise VerificationError(
                    "fenced optimizer transition has no running authoritative owner",
                    commit_seq=index,
                )
            request_body = {
                "operation": "optimizer",
                "request_id": commit.request_id,
                "owner_id": commit.owner_id,
                "owner_session_id": commit.owner_session_id,
                "fencing_epoch": commit.fencing_epoch,
                "parent_commit_id": commit.parent_commit_id,
                "selected_proposal_ids": [
                    item.proposal_id for item in commit.selected_proposals
                ],
                "aggregate_digest": commit.aggregate_digest,
            }
            if (
                commit.owner_id != prior_coordination.owner_id
                or commit.owner_session_id != prior_coordination.owner_session_id
                or commit.fencing_epoch != previous.fencing_epoch
                or commit.request_id is None
                or commit.request_digest != canonical_digest(request_body)
                or commit.optimizer_transition_count
                != prior_coordination.optimizer_transition_count + 1
            ):
                raise VerificationError(
                    "optimizer transition differs from committed fencing owner",
                    commit_seq=index,
                )
            if commit.request_id in control_requests:
                raise VerificationError(
                    "mutation request identity appears more than once",
                    commit_seq=index,
                )
            control_requests[commit.request_id] = (
                commit.request_digest,
                commit.commit_seq,
            )
        elif commit.owner_id is not None:
            raise VerificationError(
                "legacy run contains fenced optimizer fields", commit_seq=index
            )
        old_fragment = previous.fragments.get(commit.fragment_id)
        if old_fragment is None:
            raise VerificationError("commit targets an unknown fragment", commit_seq=index)
        if (
            commit.previous_fragment_version != old_fragment.version
            or commit.new_fragment_version != old_fragment.version + 1
        ):
            raise VerificationError("fragment version transition is invalid", commit_seq=index)
        selected_ids = [selection.proposal_id for selection in commit.selected_proposals]
        if selected_ids != sorted(selected_ids) or len(selected_ids) != len(set(selected_ids)):
            raise VerificationError("commit selections are not canonical", commit_seq=index)
        if set(selected_ids) & set(consumption):
            raise VerificationError("proposal is included more than once", commit_seq=index)
        selected: list[ProposalManifest] = []
        for selection in commit.selected_proposals:
            proposal = _read_production_proposal(log, selection.proposal_id, commit_seq=index)
            if (
                proposal.run_id != log.spec.run_id
                or proposal.run_generation != log.spec.run_generation
                or proposal.model_revision != log.spec.model_revision
                or proposal.parameter_index_digest != log.spec.parameter_index_digest
                or proposal.fragment_layout_digest != log.spec.fragment_layout_digest
                or proposal.outer_optimizer_schema_digest != log.spec.outer_optimizer_schema_digest
            ):
                raise VerificationError("proposal run contract mismatch", commit_seq=index)
            base = frontier_by_commit.get(proposal.base_commit_id)
            if (
                base is None
                or base.commit_seq != proposal.base_commit_seq
                or base.frontier_sha256 != proposal.base_frontier_digest
            ):
                raise VerificationError("proposal causal base is invalid", commit_seq=index)
            base_fragment = base.fragments.get(commit.fragment_id)
            if (
                proposal.fragment_id != commit.fragment_id
                or base_fragment is None
                or base_fragment.version != proposal.base_fragment_version
            ):
                raise VerificationError("proposal fragment base is invalid", commit_seq=index)
            base_optimizer_count = _optimizer_count(base)
            if (
                _optimizer_count(previous) - base_optimizer_count
                > log.spec.max_global_staleness
            ):
                raise VerificationError("proposal exceeds global staleness", commit_seq=index)
            if old_fragment.version - proposal.base_fragment_version > log.spec.max_fragment_staleness:
                raise VerificationError("proposal exceeds fragment staleness", commit_seq=index)
            lineage = (proposal.learner_id, proposal.learner_session_id, proposal.fragment_id)
            prior_sequence = last_lineage_sequence.get(lineage)
            if prior_sequence is not None and proposal.sequence <= prior_sequence:
                raise VerificationError("committed proposal lineage is not monotonic", commit_seq=index)
            interval_base = (
                *lineage,
                proposal.base_commit_id,
                proposal.base_fragment_version,
            )
            if interval_base in consumed_interval_bases:
                raise VerificationError("same-base learner interval is consumed twice", commit_seq=index)
            expected_selection = {
                "proposal_id": proposal.proposal_id,
                "learner_id": proposal.learner_id,
                "learner_session_id": proposal.learner_session_id,
                "sequence": proposal.sequence,
                "base_commit_seq": proposal.base_commit_seq,
                "base_fragment_version": proposal.base_fragment_version,
                "target_tokens": proposal.target_tokens_since_base,
                "staleness": old_fragment.version - proposal.base_fragment_version,
                "weight_fp64_hex": selection.weight_fp64_hex,
            }
            if selection.to_dict() != expected_selection:
                raise VerificationError("proposal selection metadata mismatch", commit_seq=index)
            payload_ref = ObjectRef(
                key=proposal.payload_key,
                sha256=proposal.payload_sha256,
                size=proposal.payload_size,
            )
            payload_identity = _ref_identity(payload_ref)
            if payload_identity not in cached_proposals:
                payload = verified_get(log.backend, payload_ref, commit_seq=index)
                validate_production_tensor_payload(
                    payload,
                    tensor_key=proposal.tensor_key,
                    shape=proposal.shape,
                    dtype=proposal.dtype,
                    require_finite=True,
                    validation_device=validation_device,
                )
                cached_proposals.add(payload_identity)
            selected.append(proposal)
            last_lineage_sequence[lineage] = proposal.sequence
            consumed_interval_bases.add(interval_base)
            reachable.update((log.layout.proposal_key(proposal.proposal_id), proposal.payload_key))

        weights = normalized_weights(
            {item.proposal_id: item.target_tokens_since_base for item in selected},
            staleness={
                item.proposal_id: old_fragment.version - item.base_fragment_version
                for item in selected
            },
            config=log.spec.weighting_config,
        )
        if any(
            item.weight_fp64_hex != weights[item.proposal_id].hex()
            for item in commit.selected_proposals
        ):
            raise VerificationError("committed weights differ from the oracle", commit_seq=index)
        if commit.outer_optimizer_impl_digest != expected_impl:
            raise VerificationError("production optimizer implementation digest mismatch", commit_seq=index)
        params_key = _ref_identity(commit.new_params_ref)
        outer_key = _ref_identity(commit.new_outer_state_ref)
        params_numel = cached_params.get(params_key)
        if params_numel is None:
            new_params = decode_production_params(
                verified_get(log.backend, commit.new_params_ref, commit_seq=index)
            )
            params_numel = int(new_params.numel())
            cached_params[params_key] = params_numel
        outer_numels = cached_outer.get(outer_key)
        if outer_numels is None:
            new_outer = decode_production_outer_state(
                verified_get(log.backend, commit.new_outer_state_ref, commit_seq=index)
            )
            outer_numels = frozenset(
                int(item.numel()) for key, item in new_outer.items() if key != "step"
            )
            cached_outer[outer_key] = outer_numels
        if outer_numels != {params_numel}:
            raise VerificationError("transition params/outer-state size mismatch", commit_seq=index)
        expected_fragments = dict(previous.fragments)
        expected_fragments[commit.fragment_id] = type(old_fragment)(
            version=commit.new_fragment_version,
            params_ref=commit.new_params_ref,
            outer_state_ref=commit.new_outer_state_ref,
            producing_commit_id=commit.commit_id,
        )
        if dict(frontier.fragments) != expected_fragments:
            raise VerificationError("frontier exposes a partial or extra fragment change", commit_seq=index)
        expected_consumed = tuple(sorted(set(previous.consumed_proposal_ids) | set(selected_ids)))
        if frontier.consumed_proposal_ids != expected_consumed:
            raise VerificationError("frontier consumption set mismatch", commit_seq=index)
        expected_cursor = (previous.scheduler_state["next_fragment_cursor"] + 1) % len(
            previous.fragments
        )
        if frontier.scheduler_state["next_fragment_cursor"] != expected_cursor:
            raise VerificationError("frontier scheduler state mismatch", commit_seq=index)
        if frontier.fencing_epoch != commit.fencing_epoch:
            raise VerificationError("frontier fencing epoch mismatch", commit_seq=index)
        if log.spec.coordination_protocol in {"head-fenced-v1", "distributed-head-fenced-v1"}:
            coordination = frontier.coordination
            if (
                coordination is None
                or coordination.owner_id != commit.owner_id
                or coordination.owner_session_id != commit.owner_session_id
                or coordination.optimizer_transition_count
                != commit.optimizer_transition_count
                or coordination.stop is not None
            ):
                raise VerificationError(
                    "optimizer frontier coordination projection mismatch",
                    commit_seq=index,
                )

        reachable.add(log.layout.commit_key(commit.commit_seq, commit.commit_id))
        reachable.update((commit.new_params_ref.key, commit.new_outer_state_ref.key))
        for proposal in selected:
            proposals[proposal.proposal_id] = proposal
            consumption[proposal.proposal_id] = index
        frontier_by_commit[frontier.commit_id] = frontier
        prefix_head = HeadManifest(
            protocol_version=2,
            run_id=log.spec.run_id,
            run_generation=log.spec.run_generation,
            fencing_epoch=frontier.fencing_epoch,
            commit_seq=frontier.commit_seq,
            commit_id=frontier.commit_id,
            frontier_ref=content_ref(
                log.layout.frontier_key(frontier.commit_seq, frontier.frontier_sha256),
                frontier_data[index],
            ),
        )
        prefix_digests.append(
            _prefix_digest(log, prefix_head, frontiers[: index + 1], commits[:index])
        )

    result = ReplayResult(
        loaded_head=loaded_head,
        frontiers=frontiers,
        commits=commits,
        proposals=proposals,
        consumption=consumption,
        prefix_digests=tuple(prefix_digests),
        committed_state_digest=prefix_digests[-1],
        reachable_keys=frozenset(reachable),
        control_requests=control_requests,
    )
    if cache is not None:
        cache.proposal_payloads = cached_proposals
        cache.params_numels = cached_params
        cache.outer_numels = cached_outer
    return result


def replay_log(
    log: TransactionalLog,
    *,
    production_cache: ProductionReplayCache | None = None,
    production_validation_device: Any = None,
) -> ReplayResult:
    if log.spec.payload_codec == "canonical-float-hex-v1":
        return _replay_reference_log(log)
    if log.spec.payload_codec == "safetensors-flat-v1":
        return _replay_production_log(
            log,
            cache=production_cache,
            validation_device=production_validation_device,
        )
    raise VerificationError(f"unsupported replay payload codec: {log.spec.payload_codec}")


def inspect_orphans(log: TransactionalLog) -> OrphanReport:
    replay = replay_log(log)
    observed = set(log.backend.list_prefix(log.layout.immutable_prefix))
    proposals = {key for key in observed if key.startswith(log.layout.proposal_prefix)}
    uncommitted_proposals = proposals - set(replay.reachable_keys)
    prepared_orphans = observed - set(replay.reachable_keys) - uncommitted_proposals
    return OrphanReport(
        committed_reachable=tuple(sorted(observed & set(replay.reachable_keys))),
        prepared_orphans=tuple(sorted(prepared_orphans)),
        uncommitted_proposals=tuple(sorted(uncommitted_proposals)),
    )
