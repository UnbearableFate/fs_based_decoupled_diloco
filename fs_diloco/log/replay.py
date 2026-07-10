"""Verify and replay the authoritative committed prefix from the current head."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

from fs_diloco.optimizer.reference_adapter import transition
from fs_diloco.protocol.canonical_json import canonical_bytes, canonical_digest
from fs_diloco.protocol.schemas import CommitManifest, FrontierManifest, HeadManifest, ObjectRef
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
    commits: tuple[CommitManifest, ...]
    proposals: dict[str, object]
    consumption: dict[str, int]
    prefix_digests: tuple[str, ...]
    committed_state_digest: str
    reachable_keys: frozenset[str]

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


def _parse_frontier(data: bytes, *, commit_seq: int) -> FrontierManifest:
    try:
        return FrontierManifest.from_dict(canonical_object(data, commit_seq=commit_seq))
    except VerificationError:
        raise
    except Exception as exc:
        raise VerificationError(f"invalid frontier: {exc}", commit_seq=commit_seq) from exc


def _parse_commit(data: bytes, *, commit_seq: int) -> CommitManifest:
    try:
        return CommitManifest.from_dict(canonical_object(data, commit_seq=commit_seq))
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
    commits: tuple[CommitManifest, ...],
) -> str:
    return canonical_digest(
        {
            "spec_digest": log.spec.digest,
            "head": head.to_dict(),
            "frontiers": [frontier.to_dict() for frontier in frontiers],
            "commits": [commit.to_dict() for commit in commits],
        }
    )


def replay_log(log: TransactionalLog) -> ReplayResult:
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
    reversed_commits: list[CommitManifest] = []
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
    )


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
