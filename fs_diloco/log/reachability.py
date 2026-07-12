"""Explainable distributed object-graph reachability for lifecycle GC."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from fs_diloco.distributed_syncer.layout import DistributedLayout
from fs_diloco.log.codec import canonical_object
from fs_diloco.protocol.schemas import CommitManifest, ObjectRef, ProposalManifest

from .acknowledgements import LifecycleAcknowledgementV1
from .pins import LifecyclePinV1
from fs_diloco.learner_protocol.capsule import load_capsule
from .replay import find_valid_snapshots


@dataclass(frozen=True)
class ReachabilityEdge:
    source: str
    target: str
    reason: str


@dataclass(frozen=True)
class ReachabilityReport:
    head_commit_id: str
    head_commit_seq: int
    fencing_epoch: int
    membership_revision: int | None
    inventory: tuple[str, ...]
    roots: tuple[tuple[str, str], ...]
    edges: tuple[ReachabilityEdge, ...]
    reachable: tuple[str, ...]
    candidates: tuple[str, ...]
    protected_unknown: tuple[str, ...]
    retention_reasons: tuple[tuple[str, tuple[str, ...]], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "head_commit_id": self.head_commit_id,
            "head_commit_seq": self.head_commit_seq,
            "fencing_epoch": self.fencing_epoch,
            "membership_revision": self.membership_revision,
            "inventory": list(self.inventory),
            "roots": [list(item) for item in self.roots],
            "edges": [
                {"source": item.source, "target": item.target, "reason": item.reason}
                for item in self.edges
            ],
            "reachable": list(self.reachable),
            "candidates": list(self.candidates),
            "protected_unknown": list(self.protected_unknown),
            "retention_reasons": [
                [key, list(reasons)] for key, reasons in self.retention_reasons
            ],
        }

    def explain(self, target: str) -> tuple[ReachabilityEdge, ...]:
        root_keys = {key for key, _reason in self.roots}
        if target in root_keys:
            return ()
        incoming: dict[str, list[ReachabilityEdge]] = {}
        for edge in self.edges:
            incoming.setdefault(edge.target, []).append(edge)
        queue = deque([(target, ())])
        seen = {target}
        while queue:
            current, reversed_path = queue.popleft()
            for edge in sorted(
                incoming.get(current, ()), key=lambda item: (item.source, item.reason)
            ):
                path = (edge, *reversed_path)
                if edge.source in root_keys:
                    return path
                if edge.source not in seen:
                    seen.add(edge.source)
                    queue.append((edge.source, path))
        return ()


def _extract_refs(value: Any) -> tuple[ObjectRef, ...]:
    refs: dict[tuple[str, str, int], ObjectRef] = {}

    def visit(item: Any) -> None:
        if isinstance(item, Mapping):
            if {"key", "sha256", "size"} <= set(item):
                try:
                    ref = ObjectRef.from_dict(item)
                except Exception:
                    pass
                else:
                    refs[(ref.key, ref.sha256, ref.size)] = ref
                    return
            for child in item.values():
                visit(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)

    visit(value)
    return tuple(refs[key] for key in sorted(refs))


def _known_collectable(key: str, *, log_layout, distributed: DistributedLayout) -> bool:
    prefixes = (
        f"{log_layout.immutable_prefix}commits/",
        f"{log_layout.immutable_prefix}frontiers/",
        f"{log_layout.immutable_prefix}fragments/",
        log_layout.proposal_prefix,
        f"{log_layout.immutable_prefix}distributed/memberships/",
        distributed.work_order_prefix,
        distributed.prepared_prefix,
        log_layout.learner_publication_prefix,
        log_layout.snapshot_prefix,
        log_layout.acknowledgement_prefix,
        log_layout.pin_prefix,
        log_layout.capsule_prefix,
        log_layout.mark_prefix,
        log_layout.delete_request_prefix,
        log_layout.delete_result_prefix,
    )
    return key.startswith(prefixes)


def build_reachability(
    log,
    *,
    replay=None,
    grace_eligible_keys: Iterable[str] = (),
) -> ReachabilityReport:
    """Build roots and edges from verified ancestry plus immutable evidence.

    Listing contributes only the candidate inventory. Unknown object classes are
    protected, and a listed known object becomes a delete candidate only when a
    caller supplies immutable evidence that its grace interval has elapsed.
    """

    replay = replay or log.replay(force_full=True)
    backend = log.backend
    layout = log.layout
    distributed = DistributedLayout(layout)
    inventory = tuple(sorted(backend.list_prefix(layout.immutable_prefix)))
    inventory_set = set(inventory)
    eligible = set(grace_eligible_keys)
    roots: dict[str, set[str]] = {}
    edges: set[tuple[str, str, str]] = set()

    def root(key: str, reason: str) -> None:
        roots.setdefault(key, set()).add(reason)

    def edge(source: str, target: str, reason: str) -> None:
        edges.add((source, target, reason))

    root(layout.run_manifest_key, "run_manifest")
    root(layout.head_key, "current_global_head")

    # Keep two independently valid restore bases.  Only after a second base is
    # available may physical objects covered by the older retained snapshot be
    # reclaimed.  The snapshot embeds the verified logical prefix; the objects
    # above it remain an ordinary, strictly validated committed suffix.
    try:
        snapshot_pins, _snapshot_failures = find_valid_snapshots(log.transactional, limit=2)
    except AttributeError:
        snapshot_pins, _snapshot_failures = find_valid_snapshots(log, limit=2)
    compacted_base_seq: int | None = None
    if len(snapshot_pins) >= 2:
        compacted_base_seq = snapshot_pins[-1].snapshot.covered_head.commit_seq
        for item in snapshot_pins:
            root(item.snapshot_key, "retained_snapshot_restore_point")
    else:
        for key in replay.reachable_keys:
            root(key, "committed_prefix_before_two_restore_points")

    # Audit records are observational rather than optimizer authority.  Keep
    # two observed generations in the active namespace; older records become
    # compactable only after the two-snapshot grace gate above is established.
    for prefix, reason in (
        (layout.mark_prefix, "recent_gc_mark"),
        (layout.delete_request_prefix, "recent_gc_delete_request"),
        (layout.delete_result_prefix, "recent_gc_delete_result"),
    ):
        for key in sorted(item for item in inventory if item.startswith(prefix))[-2:]:
            root(key, reason)

    def in_live_suffix(commit_seq: int) -> bool:
        return compacted_base_seq is None or commit_seq > compacted_base_seq

    if compacted_base_seq is not None:
        for frontier in replay.frontiers:
            if in_live_suffix(frontier.commit_seq):
                frontier_key = layout.frontier_key(
                    frontier.commit_seq, frontier.frontier_sha256
                )
                root(frontier_key, "snapshot_suffix_frontier")
                for fragment in frontier.fragments.values():
                    edge(frontier_key, fragment.params_ref.key, "frontier_params")
                    edge(frontier_key, fragment.outer_state_ref.key, "frontier_outer_state")
                if frontier.membership is not None:
                    edge(
                        frontier_key,
                        frontier.membership.membership_ref.key,
                        "frontier_membership",
                    )
        for commit in replay.commits:
            if not in_live_suffix(commit.commit_seq):
                continue
            commit_key = layout.commit_key(commit.commit_seq, commit.commit_id)
            root(commit_key, "snapshot_suffix_commit")
            if isinstance(commit, CommitManifest):
                for selected in commit.selected_proposals:
                    proposal = replay.proposals.get(selected.proposal_id)
                    proposal_key = layout.proposal_key(selected.proposal_id)
                    edge(commit_key, proposal_key, "selected_proposal")
                    if isinstance(proposal, ProposalManifest):
                        edge(proposal_key, proposal.payload_key, "proposal_payload")
            elif getattr(commit, "membership", None) is not None:
                edge(
                    commit_key,
                    commit.membership.membership_ref.key,
                    "committed_membership",
                )
            if getattr(commit, "snapshot", None) is not None and any(
                item.snapshot_key == commit.snapshot.snapshot_ref.key
                for item in snapshot_pins
            ):
                edge(commit_key, commit.snapshot.snapshot_ref.key, "snapshot_pin")

    for commit in replay.commits:
        if not in_live_suffix(commit.commit_seq):
            continue
        commit_key = layout.commit_key(commit.commit_seq, commit.commit_id)
        if not isinstance(commit, CommitManifest):
            if getattr(commit, "snapshot", None) is not None:
                edge(commit_key, commit.snapshot.snapshot_ref.key, "snapshot_pin")
            continue
        if commit.distributed_work_order_id is None:
            continue
        work_key = distributed.work_order_key(commit.distributed_work_order_id)
        result_key = distributed.result_key(commit.prepared_result_id or "")
        root(work_key, "committed_work_order")
        root(result_key, "committed_prepared_result")
        edge(commit_key, work_key, "final_transition_work_order")
        edge(commit_key, result_key, "final_transition_prepared_result")
        input_key = distributed.input_bundle_key(commit.distributed_work_order_id)
        if input_key in inventory_set:
            edge(work_key, input_key, "executor_input_bundle")
            try:
                for ref in _extract_refs(canonical_object(backend.get(input_key))):
                    edge(input_key, ref.key, "input_object_ref")
            except Exception:
                root(input_key, "invalid_input_bundle_quarantine")
        if result_key in inventory_set:
            try:
                for ref in _extract_refs(canonical_object(backend.get(result_key))):
                    edge(result_key, ref.key, "prepared_output_ref")
            except Exception:
                root(result_key, "invalid_prepared_result_quarantine")

    marker_groups: dict[str, dict[str, list[tuple[str, str]]]] = {}
    for marker_key in sorted(
        key for key in inventory if key.startswith(distributed.marker_prefix)
    ):
        try:
            marker = canonical_object(backend.get(marker_key))
            required = {
                "schema",
                "work_order_id",
                "prepared_result_ref",
                "attempt_envelope_ref",
            }
            if set(marker) != required or marker["schema"] != "duraloco-prepared-attempt-marker-v1":
                raise ValueError("marker schema differs")
            result_ref = ObjectRef.from_dict(marker["prepared_result_ref"])
            attempt_ref = ObjectRef.from_dict(marker["attempt_envelope_ref"])
            work_order_id = marker["work_order_id"]
            if not isinstance(work_order_id, str) or not work_order_id:
                raise ValueError("marker work order identity differs")
            marker_groups.setdefault(work_order_id, {}).setdefault(
                result_ref.key, []
            ).append((marker_key, attempt_ref.key))
            edge(marker_key, result_ref.key, "marker_prepared_result")
            edge(marker_key, attempt_ref.key, "marker_attempt_envelope")
        except Exception:
            root(marker_key, "invalid_marker_quarantine")

    committed_results = {
        commit.distributed_work_order_id: distributed.result_key(commit.prepared_result_id)
        for commit in replay.commits
        if isinstance(commit, CommitManifest)
        and commit.distributed_work_order_id is not None
        and commit.prepared_result_id is not None
    }
    for work_order_id, result_groups in marker_groups.items():
        divergent = len(result_groups) > 1
        for result_key, attempts in result_groups.items():
            for marker_key, attempt_key in attempts:
                if divergent:
                    root(marker_key, "divergent_result_blocker")
                    root(attempt_key, "divergent_result_blocker")
                    root(result_key, "divergent_result_blocker")
                elif committed_results.get(work_order_id) == result_key:
                    if marker_key not in eligible:
                        root(marker_key, "same_digest_loser_grace")
                    if attempt_key not in eligible:
                        root(attempt_key, "same_digest_loser_grace")
                elif marker_key not in eligible:
                    root(marker_key, "abandoned_attempt_grace")
                    root(attempt_key, "abandoned_attempt_grace")
                    root(result_key, "abandoned_result_grace")

    for key in sorted(key for key in inventory if key.startswith(layout.pin_prefix)):
        try:
            pin = LifecyclePinV1.from_dict(canonical_object(backend.get(key)))
            root(key, f"pin:{pin.kind}")
            for ref in pin.object_refs:
                edge(key, ref.key, f"pin_ref:{pin.kind}")
        except Exception:
            root(key, "invalid_pin_quarantine")

    released_refs: set[str] = set()
    acknowledgements: list[tuple[str, LifecycleAcknowledgementV1]] = []
    for key in sorted(
        key for key in inventory if key.startswith(layout.acknowledgement_prefix)
    ):
        try:
            acknowledgement = LifecycleAcknowledgementV1.from_dict(
                canonical_object(backend.get(key))
            )
            acknowledgements.append((key, acknowledgement))
            if acknowledgement.kind == "no_longer_needs":
                released_refs.update(ref.key for ref in acknowledgement.object_refs)
        except Exception:
            root(key, "invalid_ack_quarantine")

    retained_ack_keys: set[str] = set()
    acknowledgement_groups: dict[
        tuple[str, str, str, int | None],
        list[tuple[str, LifecycleAcknowledgementV1]],
    ] = {}
    for item in acknowledgements:
        key, acknowledgement = item
        group = (
            acknowledgement.role,
            acknowledgement.subject_id,
            acknowledgement.kind,
            acknowledgement.fragment_id,
        )
        acknowledgement_groups.setdefault(group, []).append(item)
    for items in acknowledgement_groups.values():
        retained_ack_keys.update(
            key
            for key, _ack in sorted(
                items,
                key=lambda item: (
                    item[1].commit_seq,
                    item[1].session_id,
                    item[1].acknowledgement_id,
                ),
            )[-2:]
        )
    for key, acknowledgement in acknowledgements:
        if key not in retained_ack_keys:
            continue
        root(key, f"ack:{acknowledgement.kind}")
        if acknowledgement.kind != "no_longer_needs":
            for ref in acknowledgement.object_refs:
                edge(key, ref.key, f"ack_ref:{acknowledgement.kind}")

    capsule_marker_prefix = f"{layout.capsule_prefix}markers/"
    capsules = []
    for key in sorted(
        key for key in inventory if key.startswith(capsule_marker_prefix)
    ):
        try:
            marker = canonical_object(backend.get(key))
            capsule = load_capsule(backend, key)
            manifest_ref = ObjectRef.from_dict(marker["manifest_ref"])
            capsules.append((key, capsule, manifest_ref))
        except Exception:
            root(key, "invalid_capsule_quarantine")

    retained_capsule_keys: set[str] = set()
    capsule_groups: dict[str, list[tuple[str, Any, ObjectRef]]] = {}
    for item in capsules:
        capsule_groups.setdefault(item[1].learner_id, []).append(item)
    for items in capsule_groups.values():
        retained_capsule_keys.update(
            key
            for key, _capsule, _manifest_ref in sorted(
                items,
                key=lambda item: (
                    item[1].frontier_commit_seq,
                    item[1].sequence,
                    item[1].capsule_id,
                ),
            )[-2:]
        )
    for key, capsule, manifest_ref in capsules:
        released = key in released_refs and key in eligible
        if key in retained_capsule_keys and not released:
            root(key, "learner_capsule_restore_point")
            edge(key, manifest_ref.key, "capsule_manifest")
            for kind, ref in capsule.components:
                edge(manifest_ref.key, ref.key, f"capsule_component:{kind}")

    adjacency: dict[str, set[str]] = {}
    for source, target, _reason in edges:
        adjacency.setdefault(source, set()).add(target)
    reachable = set(roots)
    queue = deque(sorted(reachable))
    while queue:
        source = queue.popleft()
        for target in sorted(adjacency.get(source, ())):
            if target not in reachable:
                reachable.add(target)
                queue.append(target)

    candidates: list[str] = []
    protected_unknown: list[str] = []
    for key in inventory:
        if key in reachable:
            continue
        if not _known_collectable(key, log_layout=layout, distributed=distributed):
            protected_unknown.append(key)
        elif key in eligible or (
            compacted_base_seq is not None
            and key.startswith(
                (
                    f"{layout.immutable_prefix}commits/",
                    f"{layout.immutable_prefix}frontiers/",
                    f"{layout.immutable_prefix}fragments/",
                    layout.proposal_prefix,
                    f"{layout.immutable_prefix}distributed/memberships/",
                    layout.snapshot_prefix,
                    layout.acknowledgement_prefix,
                    layout.capsule_prefix,
                    layout.mark_prefix,
                    layout.delete_request_prefix,
                    layout.delete_result_prefix,
                )
            )
        ):
            candidates.append(key)
        else:
            root(key, "grace_not_elapsed")
            reachable.add(key)

    reasons = tuple(
        (key, tuple(sorted(values))) for key, values in sorted(roots.items())
    )
    return ReachabilityReport(
        head_commit_id=replay.head_frontier.commit_id,
        head_commit_seq=replay.head_frontier.commit_seq,
        fencing_epoch=replay.head_frontier.fencing_epoch,
        membership_revision=(
            replay.head_frontier.membership.revision
            if replay.head_frontier.membership is not None
            else None
        ),
        inventory=inventory,
        roots=tuple((key, reason) for key, values in reasons for reason in values),
        edges=tuple(
            ReachabilityEdge(source, target, reason)
            for source, target, reason in sorted(edges)
        ),
        reachable=tuple(sorted(reachable)),
        candidates=tuple(sorted(candidates)),
        protected_unknown=tuple(protected_unknown),
        retention_reasons=reasons,
    )
