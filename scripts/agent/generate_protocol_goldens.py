#!/usr/bin/env python3
"""Print reviewable Protocol v2 canonical manifest vectors; never overwrite fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fs_diloco.protocol.identities import commit_id_for, frontier_digest_for
from fs_diloco.protocol.manifests import dump_manifest
from fs_diloco.protocol.schemas import (
    CommitManifest,
    DropDecision,
    FrontierManifest,
    HeadManifest,
    ProposalManifest,
)


D = "d" * 64


def _ref(key: str) -> dict[str, object]:
    return {"key": key, "sha256": D, "size": 8}


def _objects() -> list[object]:
    proposal = ProposalManifest.with_computed_id(
        {
            "manifest_type": "proposal",
            "protocol_version": 2,
            "run_id": "golden-run",
            "run_generation": 0,
            "model_revision": "synthetic-model-v1",
            "learner_id": "learner-000",
            "learner_session_id": "session-000",
            "sequence": 1,
            "fragment_id": 0,
            "base_commit_id": "genesis",
            "base_commit_seq": 0,
            "base_fragment_version": 0,
            "base_frontier_digest": "a" * 64,
            "local_steps_since_base": 10,
            "target_tokens_since_base": 100,
            "payload_kind": "pseudo_gradient",
            "payload_key": "immutable/proposals/payload.safetensors",
            "tensor_key": "fragment_0000",
            "shape": [2],
            "dtype": "float32",
            "payload_size": 16,
            "payload_sha256": "e" * 64,
            "parameter_index_digest": "b" * 64,
            "fragment_layout_digest": "c" * 64,
            "outer_optimizer_schema_digest": D,
        }
    )
    commit_body = {
        "manifest_type": "commit",
        "protocol_version": 2,
        "run_id": "golden-run",
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
                "base_commit_seq": 0,
                "base_fragment_version": 0,
                "target_tokens": 100,
                "staleness": 0,
                "weight_fp64_hex": float(1.0).hex(),
            }
        ],
        "aggregate_digest": D,
        "outer_optimizer_impl_digest": "f" * 64,
        "new_params_ref": _ref("params"),
        "new_outer_state_ref": _ref("outer"),
    }
    commit = CommitManifest.from_dict(
        {**commit_body, "commit_id": commit_id_for(commit_body)}
    )
    frontier_body = {
        "manifest_type": "frontier",
        "protocol_version": 2,
        "run_id": "golden-run",
        "run_generation": 0,
        "commit_seq": 1,
        "commit_id": commit.commit_id,
        "parent_frontier_sha256": "a" * 64,
        "fencing_epoch": 0,
        "fragments": {
            "0": {
                "version": 1,
                "params_ref": _ref("params"),
                "outer_state_ref": _ref("outer"),
                "producing_commit_id": commit.commit_id,
            }
        },
        "scheduler_state": {"next_fragment_cursor": 0},
        "consumed_proposal_ids": [proposal.proposal_id],
    }
    frontier = FrontierManifest.from_dict(
        {**frontier_body, "frontier_sha256": frontier_digest_for(frontier_body)}
    )
    head = HeadManifest.from_dict(
        {
            "manifest_type": "head",
            "protocol_version": 2,
            "run_id": "golden-run",
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
    return [proposal, commit, frontier, head, drop]


def main() -> int:
    vectors = {}
    for manifest in _objects():
        encoded = dump_manifest(manifest)
        vectors[manifest.MANIFEST_TYPE] = {
            "canonical": encoded.decode(),
            "sha256": hashlib.sha256(encoded).hexdigest(),
        }
    print(json.dumps(vectors, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
