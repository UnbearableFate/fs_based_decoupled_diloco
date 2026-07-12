"""Immutable mark snapshots and guarded, idempotent lifecycle GC."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from fs_diloco.log.codec import canonical_object
from fs_diloco.protocol.canonical_json import canonical_bytes, canonical_digest
from fs_diloco.protocol.schemas import HeadManifest, ObjectRef
from fs_diloco.storage import NotFound

from .reachability import ReachabilityReport, build_reachability


@dataclass(frozen=True)
class GcMarkV1:
    run_id: str
    run_generation: int
    head: HeadManifest
    head_version: str
    fencing_epoch: int
    membership_revision: int | None
    candidate_refs: tuple[ObjectRef, ...]
    reachable_digest: str
    protected_unknown_digest: str
    mark_id: str

    @classmethod
    def create(cls, log, report: ReachabilityReport) -> "GcMarkV1":
        loaded = log.load_head()
        if (
            loaded.manifest.commit_id != report.head_commit_id
            or loaded.manifest.commit_seq != report.head_commit_seq
            or loaded.manifest.fencing_epoch != report.fencing_epoch
        ):
            raise ValueError("reachability report does not cover the current head")
        refs = tuple(
            sorted(
                (log.backend.head(key).to_ref() for key in report.candidates),
                key=lambda item: item.key,
            )
        )
        body = {
            "schema": "duraloco-gc-mark-v1",
            "run_id": log.spec.run_id,
            "run_generation": log.spec.run_generation,
            "head": loaded.manifest.to_dict(),
            "head_version": loaded.metadata.version,
            "fencing_epoch": report.fencing_epoch,
            "membership_revision": report.membership_revision,
            "candidate_refs": [item.to_dict() for item in refs],
            "reachable_digest": canonical_digest(list(report.reachable)),
            "protected_unknown_digest": canonical_digest(
                list(report.protected_unknown)
            ),
        }
        return cls.from_dict({**body, "mark_id": "mark-" + canonical_digest(body)})

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "GcMarkV1":
        required = {
            "schema",
            "run_id",
            "run_generation",
            "head",
            "head_version",
            "fencing_epoch",
            "membership_revision",
            "candidate_refs",
            "reachable_digest",
            "protected_unknown_digest",
            "mark_id",
        }
        if not isinstance(payload, Mapping) or set(payload) != required:
            raise ValueError("GC mark fields differ from contract")
        if payload["schema"] != "duraloco-gc-mark-v1":
            raise ValueError("unsupported GC mark schema")
        if not isinstance(payload["run_id"], str) or not payload["run_id"]:
            raise ValueError("GC mark run_id must be non-empty")
        if type(payload["run_generation"]) is not int or payload["run_generation"] < 0:
            raise ValueError("GC mark run_generation must be non-negative")
        head = HeadManifest.from_dict(payload["head"])
        if (
            head.run_id != payload["run_id"]
            or head.run_generation != payload["run_generation"]
            or head.fencing_epoch != payload["fencing_epoch"]
        ):
            raise ValueError("GC mark head identity differs")
        if not isinstance(payload["head_version"], str) or not payload["head_version"]:
            raise ValueError("GC mark head version must be non-empty")
        membership = payload["membership_revision"]
        if membership is not None and (type(membership) is not int or membership < 0):
            raise ValueError("GC mark membership revision is invalid")
        raw_refs = payload["candidate_refs"]
        if not isinstance(raw_refs, list):
            raise ValueError("GC mark candidate_refs must be a list")
        refs = tuple(ObjectRef.from_dict(item) for item in raw_refs)
        if tuple(sorted(refs, key=lambda item: item.key)) != refs:
            raise ValueError("GC mark candidates are not canonical")
        for field in ("reachable_digest", "protected_unknown_digest"):
            if not isinstance(payload[field], str) or len(payload[field]) != 64:
                raise ValueError(f"GC mark {field} is invalid")
        body = dict(payload)
        mark_id = body.pop("mark_id")
        if mark_id != "mark-" + canonical_digest(body):
            raise ValueError("GC mark identity differs")
        return cls(
            run_id=payload["run_id"],
            run_generation=payload["run_generation"],
            head=head,
            head_version=payload["head_version"],
            fencing_epoch=payload["fencing_epoch"],
            membership_revision=membership,
            candidate_refs=refs,
            reachable_digest=payload["reachable_digest"],
            protected_unknown_digest=payload["protected_unknown_digest"],
            mark_id=mark_id,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "duraloco-gc-mark-v1",
            "run_id": self.run_id,
            "run_generation": self.run_generation,
            "head": self.head.to_dict(),
            "head_version": self.head_version,
            "fencing_epoch": self.fencing_epoch,
            "membership_revision": self.membership_revision,
            "candidate_refs": [item.to_dict() for item in self.candidate_refs],
            "reachable_digest": self.reachable_digest,
            "protected_unknown_digest": self.protected_unknown_digest,
            "mark_id": self.mark_id,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())


@dataclass(frozen=True)
class GcApplyResult:
    request_id: str
    mark_id: str
    status: str
    deleted: tuple[str, ...]
    already_missing: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "duraloco-gc-result-v1",
            "request_id": self.request_id,
            "mark_id": self.mark_id,
            "status": self.status,
            "deleted": list(self.deleted),
            "already_missing": list(self.already_missing),
        }


def create_gc_mark(
    log,
    *,
    grace_eligible_keys: Iterable[str] = (),
) -> tuple[GcMarkV1, ReachabilityReport]:
    replay = _lifecycle_replay(log)
    report = build_reachability(
        log, replay=replay, grace_eligible_keys=grace_eligible_keys
    )
    mark = GcMarkV1.create(log, report)
    log.backend.put_immutable(log.layout.mark_key(mark.mark_id), mark.canonical_bytes())
    return mark, report


def _lifecycle_replay(log):
    """Replay safely both before and after prefix compaction."""

    replay_from_snapshot = getattr(log, "replay_from_snapshot", None)
    if replay_from_snapshot is not None:
        return replay_from_snapshot().replay
    return log.replay(force_full=True)


def approval_token_for(mark: GcMarkV1, *, namespace: str) -> str:
    return "gc-approve-" + canonical_digest(
        {"mark_id": mark.mark_id, "namespace": namespace, "operation": "gc_apply"}
    )


def _load_existing_result(log, request_id: str) -> GcApplyResult | None:
    try:
        payload = canonical_object(log.backend.get(log.layout.delete_result_key(request_id)))
    except NotFound:
        return None
    required = {
        "schema",
        "request_id",
        "mark_id",
        "status",
        "deleted",
        "already_missing",
    }
    if set(payload) != required or payload["schema"] != "duraloco-gc-result-v1":
        raise ValueError("stored GC result differs from contract")
    return GcApplyResult(
        request_id=payload["request_id"],
        mark_id=payload["mark_id"],
        status=payload["status"],
        deleted=tuple(payload["deleted"]),
        already_missing=tuple(payload["already_missing"]),
    )


def apply_gc(
    log,
    mark: GcMarkV1,
    *,
    approval_token: str,
    namespace: str,
    grace_eligible_keys: Iterable[str],
    request_id: str,
) -> GcApplyResult:
    """Apply one immutable mark in a synthetic namespace only.

    Real-run destructive apply remains an explicit human approval gate and is
    deliberately unavailable through this API.
    """

    if namespace != "synthetic" or not log.spec.run_id.startswith("synthetic-"):
        raise PermissionError("destructive GC is restricted to synthetic namespaces")
    if approval_token != approval_token_for(mark, namespace=namespace):
        raise PermissionError("GC approval token differs from mark and namespace")
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("GC request_id must be non-empty")
    existing = _load_existing_result(log, request_id)
    if existing is not None:
        if existing.mark_id != mark.mark_id:
            raise ValueError("GC request identity conflicts with another mark")
        return existing
    loaded = log.load_head()
    replay = _lifecycle_replay(log)
    membership = (
        replay.head_frontier.membership.revision
        if replay.head_frontier.membership is not None
        else None
    )
    if (
        loaded.manifest != mark.head
        or loaded.metadata.version != mark.head_version
        or replay.head_frontier.fencing_epoch != mark.fencing_epoch
        or membership != mark.membership_revision
    ):
        raise RuntimeError("GC mark is stale after head or epoch change")
    report = build_reachability(
        log,
        replay=replay,
        grace_eligible_keys=grace_eligible_keys,
    )
    current_candidates = set(report.candidates)
    present: list[ObjectRef] = []
    reconciled_missing: set[str] = set()
    for ref in mark.candidate_refs:
        try:
            metadata = log.backend.head(ref.key)
        except NotFound:
            reconciled_missing.add(ref.key)
            continue
        if metadata.to_ref() != ref:
            raise RuntimeError(f"GC target identity changed for {ref.key}")
        present.append(ref)
    if not {item.key for item in present} <= current_candidates:
        raise RuntimeError("GC candidate became reachable or lost grace eligibility")
    request_body = {
        "schema": "duraloco-gc-delete-request-v1",
        "request_id": request_id,
        "mark_id": mark.mark_id,
        "namespace": namespace,
        "targets": [item.to_dict() for item in mark.candidate_refs],
    }
    log.backend.put_immutable(
        log.layout.delete_request_key(request_id), canonical_bytes(request_body)
    )
    nonmarkers = tuple(
        item for item in present if "/prepared/markers/" not in item.key
    )
    markers = tuple(
        item for item in present if "/prepared/markers/" in item.key
    )
    deleted: set[str] = set()
    missing: set[str] = set(reconciled_missing)
    for group in (nonmarkers, markers):
        if not group:
            continue
        outcomes = log.backend.delete_batch(group)
        for key, outcome in outcomes.items():
            if outcome == "deleted":
                deleted.add(key)
            elif outcome == "missing":
                missing.add(key)
            else:
                raise RuntimeError(f"GC delete precondition failed for {key}: {outcome}")
    result = GcApplyResult(
        request_id=request_id,
        mark_id=mark.mark_id,
        status="applied",
        deleted=tuple(sorted(deleted)),
        already_missing=tuple(sorted(missing)),
    )
    log.backend.put_immutable(
        log.layout.delete_result_key(request_id), canonical_bytes(result.to_dict())
    )
    return result
