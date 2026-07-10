from __future__ import annotations

import pytest

from fs_diloco.protocol.errors import ErrorCategory, ProtocolError
from fs_diloco.protocol.invariants import IdentityRegistry
from fs_diloco.protocol.schemas import ProposalManifest

from .helpers import make_proposal


def test_proposal_identity_is_content_derived_and_observation_time_is_excluded(tmp_path):
    first = make_proposal(tmp_path)
    second_data = first.to_dict()
    second_data["created_at"] = "2099-01-01T00:00:00Z"
    second = ProposalManifest.from_dict(second_data)
    assert first.proposal_id == second.proposal_id
    assert first.canonical_bytes() != second.canonical_bytes()


def test_same_logical_body_has_same_id_and_content_change_has_different_id(tmp_path):
    first = make_proposal(tmp_path)
    same = make_proposal(tmp_path)
    changed = make_proposal(tmp_path, target_tokens_since_base=101)
    assert first.proposal_id == same.proposal_id
    assert first.proposal_id != changed.proposal_id


def test_supplied_identity_for_different_content_fails_fatally(tmp_path):
    first = make_proposal(tmp_path)
    conflicting = first.to_dict()
    conflicting["target_tokens_since_base"] += 1
    with pytest.raises(ProtocolError) as caught:
        ProposalManifest.from_dict(conflicting)
    assert caught.value.code == "PROPOSAL_ID_MISMATCH"
    assert caught.value.category == ErrorCategory.FATAL


def test_identity_registry_is_idempotent(tmp_path):
    proposal = make_proposal(tmp_path)
    registry = IdentityRegistry()
    assert registry.observe(proposal) is True
    assert registry.observe(proposal) is False
