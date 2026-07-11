from __future__ import annotations

import copy

import pytest

from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.protocol.identities import commit_id_for, frontier_digest_for
from fs_diloco.protocol.manifests import dump_manifest, load_manifest_bytes
from fs_diloco.protocol.schemas import ControlCommitManifest, FrontierManifest


def _control_dict(*, kind: str = "epoch_bump") -> dict[str, object]:
    request_body = {
        "operation": kind,
        "request_id": f"request-{kind}",
        "owner_id": "syncer-a",
        "owner_session_id": "session-a",
        "fencing_epoch": 1,
    }
    body: dict[str, object] = {
        "manifest_type": "control_commit",
        "protocol_version": 2,
        "run_id": "run-test",
        "run_generation": 0,
        "commit_seq": 1,
        "parent_commit_id": "genesis",
        "parent_head_version": "sha256:" + "a" * 64,
        "control_kind": kind,
        "prior_fencing_epoch": 0 if kind == "epoch_bump" else 1,
        "fencing_epoch": 1,
        "owner_id": "syncer-a",
        "owner_session_id": "session-a",
        "request_id": f"request-{kind}",
        "request_digest": canonical_digest(request_body),
        "optimizer_transition_count": 0,
    }
    if kind == "stop":
        body["stop_reason"] = "operator_requested"
    return {**body, "commit_id": commit_id_for(body)}


def _frontier_dict(commit: ControlCommitManifest) -> dict[str, object]:
    coordination: dict[str, object] = {
        "optimizer_transition_count": commit.optimizer_transition_count,
        "owner_id": commit.owner_id,
        "owner_session_id": commit.owner_session_id,
    }
    if commit.control_kind == "stop":
        coordination["stop"] = {
            "request_id": commit.request_id,
            "request_digest": commit.request_digest,
            "reason": commit.stop_reason,
            "committed_at_seq": commit.commit_seq,
        }
    body: dict[str, object] = {
        "manifest_type": "frontier",
        "protocol_version": 2,
        "run_id": "run-test",
        "run_generation": 0,
        "commit_seq": commit.commit_seq,
        "commit_id": commit.commit_id,
        "parent_frontier_sha256": "b" * 64,
        "fencing_epoch": commit.fencing_epoch,
        "fragments": {
            "0": {
                "version": 0,
                "params_ref": {"key": "params", "sha256": "c" * 64, "size": 8},
                "outer_state_ref": {
                    "key": "outer",
                    "sha256": "d" * 64,
                    "size": 8,
                },
                "producing_commit_id": "genesis",
            }
        },
        "scheduler_state": {"next_fragment_cursor": 0},
        "consumed_proposal_ids": [],
        "coordination": coordination,
    }
    return {**body, "frontier_sha256": frontier_digest_for(body)}


@pytest.mark.parametrize("kind", ["epoch_bump", "stop"])
def test_control_commit_and_frontier_round_trip_canonically(kind):
    commit = ControlCommitManifest.from_dict(_control_dict(kind=kind))
    frontier = FrontierManifest.from_dict(_frontier_dict(commit))
    for manifest in (commit, frontier):
        assert load_manifest_bytes(dump_manifest(manifest)) == manifest


def test_control_commit_rejects_unknown_and_null_identity_fields():
    payload = _control_dict()
    payload["unknown"] = "value"
    with pytest.raises(Exception):
        ControlCommitManifest.from_dict(payload)

    payload = _control_dict()
    payload["stop_reason"] = None
    with pytest.raises(Exception):
        ControlCommitManifest.from_dict(payload)


def test_frontier_requires_canonical_omission_for_absent_stop():
    commit = ControlCommitManifest.from_dict(_control_dict())
    payload = _frontier_dict(commit)
    payload = copy.deepcopy(payload)
    payload["coordination"]["stop"] = None
    payload["frontier_sha256"] = frontier_digest_for(
        {key: value for key, value in payload.items() if key != "frontier_sha256"}
    )
    with pytest.raises(Exception):
        FrontierManifest.from_dict(payload)


def test_legacy_frontier_without_coordination_preserves_identity():
    payload = _frontier_dict(ControlCommitManifest.from_dict(_control_dict()))
    payload.pop("coordination")
    payload["frontier_sha256"] = frontier_digest_for(
        {key: value for key, value in payload.items() if key != "frontier_sha256"}
    )
    parsed = FrontierManifest.from_dict(payload)
    assert "coordination" not in parsed.to_dict()
    assert parsed.to_dict() == payload
