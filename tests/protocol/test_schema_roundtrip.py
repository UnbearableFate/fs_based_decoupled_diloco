from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from fs_diloco.protocol.identities import commit_id_for, frontier_digest_for
from fs_diloco.protocol.manifests import dump_manifest, load_manifest_bytes
from fs_diloco.protocol.schemas import (
    CommitManifest,
    DropDecision,
    FrontierManifest,
    HeadManifest,
    ObjectRef,
    ProposalManifest,
)

from .helpers import DIGEST, make_proposal


ROOT = Path(__file__).resolve().parents[2]


def _ref(key: str) -> dict:
    return {"key": key, "sha256": DIGEST, "size": 8}


def _commit_dict(proposal: ProposalManifest) -> dict:
    body = {
        "manifest_type": "commit",
        "protocol_version": 2,
        "run_id": "run-test",
        "run_generation": 0,
        "commit_seq": 1,
        "parent_commit_id": "genesis",
        "parent_head_version": "v0",
        "fencing_epoch": 0,
        "fragment_id": 0,
        "previous_fragment_version": 0,
        "new_fragment_version": 1,
        "selected_proposals": [
            {
                "proposal_id": proposal.proposal_id,
                "learner_id": proposal.learner_id,
                "learner_session_id": proposal.learner_session_id,
                "sequence": proposal.sequence,
                "base_commit_seq": proposal.base_commit_seq,
                "base_fragment_version": proposal.base_fragment_version,
                "target_tokens": proposal.target_tokens_since_base,
                "staleness": 0,
                "weight_fp64_hex": float(1.0).hex(),
            }
        ],
        "aggregate_digest": DIGEST,
        "outer_optimizer_impl_digest": "e" * 64,
        "new_params_ref": _ref("params"),
        "new_outer_state_ref": _ref("outer"),
    }
    return {**body, "commit_id": commit_id_for(body)}


def _frontier_dict(commit_id: str, proposal_id: str) -> dict:
    body = {
        "manifest_type": "frontier",
        "protocol_version": 2,
        "run_id": "run-test",
        "run_generation": 0,
        "commit_seq": 1,
        "commit_id": commit_id,
        "parent_frontier_sha256": "a" * 64,
        "fencing_epoch": 0,
        "fragments": {
            "0": {
                "version": 1,
                "params_ref": _ref("params"),
                "outer_state_ref": _ref("outer"),
                "producing_commit_id": commit_id,
            }
        },
        "scheduler_state": {"next_fragment_cursor": 0},
        "consumed_proposal_ids": [proposal_id],
    }
    return {**body, "frontier_sha256": frontier_digest_for(body)}


def _all_objects(tmp_path):
    proposal = make_proposal(tmp_path)
    commit = CommitManifest.from_dict(_commit_dict(proposal))
    frontier = FrontierManifest.from_dict(_frontier_dict(commit.commit_id, proposal.proposal_id))
    head = HeadManifest.from_dict(
        {
            "manifest_type": "head",
            "protocol_version": 2,
            "run_id": "run-test",
            "run_generation": 0,
            "fencing_epoch": 0,
            "commit_seq": 1,
            "commit_id": commit.commit_id,
            "frontier_ref": _ref("frontier"),
        }
    )
    drop = DropDecision.from_dict(
        {
            "manifest_type": "drop_decision",
            "protocol_version": 2,
            "proposal_id": proposal.proposal_id,
            "decision": "superseded",
            "reason": "newer_nonoverlap",
            "decided_at_commit_seq": 1,
        }
    )
    return proposal, commit, frontier, head, drop


def test_all_protocol_objects_round_trip_canonical_bytes(tmp_path):
    for manifest in _all_objects(tmp_path):
        encoded = dump_manifest(manifest)
        parsed = load_manifest_bytes(encoded)
        assert dump_manifest(parsed) == encoded
        assert parsed == manifest


def test_inspect_cli_reports_a_canonical_v2_manifest(tmp_path):
    proposal = make_proposal(tmp_path)
    manifest_path = tmp_path / "proposal.json"
    manifest_path.write_bytes(dump_manifest(proposal))
    result = subprocess.run(
        [sys.executable, "-m", "fs_diloco.protocol", str(manifest_path)],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    assert json.loads(result.stdout) == proposal.to_dict()


def test_every_present_required_field_is_enforced_for_every_protocol_object(tmp_path):
    for manifest in _all_objects(tmp_path):
        payload = manifest.to_dict()
        for field in tuple(payload):
            candidate = copy.deepcopy(payload)
            del candidate[field]
            with pytest.raises(Exception):
                type(manifest).from_dict(candidate)


def test_object_ref_required_fields_and_optional_version():
    payload = {"key": "immutable/object", "sha256": DIGEST, "size": 8, "version": "v1"}
    assert ObjectRef.from_dict(payload).to_dict() == payload
    for field in ("key", "sha256", "size"):
        candidate = dict(payload)
        del candidate[field]
        with pytest.raises(Exception):
            ObjectRef.from_dict(candidate)


@pytest.mark.parametrize("field", ["run_id", "payload_key", "shape", "payload_sha256"])
def test_proposal_required_fields_are_enforced(tmp_path, field):
    payload = make_proposal(tmp_path).to_dict()
    del payload[field]
    with pytest.raises(Exception):
        ProposalManifest.from_dict(payload)


def test_unknown_fields_types_versions_and_ranges_are_rejected(tmp_path):
    valid = make_proposal(tmp_path).to_dict()
    cases = []
    item = copy.deepcopy(valid)
    item["surprise"] = True
    cases.append(item)
    item = copy.deepcopy(valid)
    item["protocol_version"] = 3
    cases.append(item)
    item = copy.deepcopy(valid)
    item["sequence"] = -1
    cases.append(item)
    item = copy.deepcopy(valid)
    item["payload_sha256"] = item["payload_sha256"].upper()
    cases.append(item)
    item = copy.deepcopy(valid)
    item["fragment_id"] = True
    cases.append(item)
    for payload in cases:
        with pytest.raises(Exception):
            ProposalManifest.from_dict(payload)
