from __future__ import annotations

import copy

import pytest

from fs_diloco.protocol.work_order_v1 import FragmentWorkOrderV1
from fs_diloco.protocol.work_order_v2 import RedundantFragmentWorkOrderV2


def _base() -> FragmentWorkOrderV1:
    return FragmentWorkOrderV1.with_computed_id(
        {
            "schema": FragmentWorkOrderV1.SCHEMA,
            "run_id": "run-r2",
            "run_generation": 0,
            "parent_commit_id": "parent",
            "parent_frontier_digest": "1" * 64,
            "fragment_id": 0,
            "committer_fencing_epoch": 1,
            "membership_revision": 0,
            "ownership_digest": "2" * 64,
            "proposals": [
                {
                    "proposal_id": "proposal-a",
                    "payload_sha256": "3" * 64,
                    "target_tokens": 8,
                    "base_fragment_version": 0,
                    "weight_hex": (1.0).hex(),
                }
            ],
            "aggregation_policy_digest": "4" * 64,
            "outer_optimizer_impl_digest": "5" * 64,
            "execution_backend_digest": "6" * 64,
            "parameter_index_digest": "7" * 64,
            "fragment_layout_digest": "8" * 64,
        }
    )


def _payload():
    return {
        "schema": RedundantFragmentWorkOrderV2.SCHEMA,
        "base_work_order": _base().to_dict(),
        "owner_member_ids": ["member-primary", "member-backup"],
        "redundancy_policy": {"mode": "hedged", "hedge_delay_ms": 6000},
    }


def test_redundant_work_order_round_trips_roles_mode_and_identity():
    order = RedundantFragmentWorkOrderV2.with_computed_id(_payload())
    assert RedundantFragmentWorkOrderV2.from_dict(copy.deepcopy(order.to_dict())) == order
    assert order.primary_member_id == "member-primary"
    assert order.backup_member_id == "member-backup"
    assert order.fragment_id == 0 and order.proposals == _base().proposals


def test_redundant_work_order_unknown_null_or_conflicting_role_fails_closed():
    order = RedundantFragmentWorkOrderV2.with_computed_id(_payload()).to_dict()
    mutations = []
    unknown = copy.deepcopy(order); unknown["winner"] = "primary"; mutations.append(unknown)
    null_delay = copy.deepcopy(order); null_delay["redundancy_policy"] = {"mode": "warm_standby", "hedge_delay_ms": None}; mutations.append(null_delay)
    duplicate = copy.deepcopy(order); duplicate["owner_member_ids"] = ["same", "same"]; mutations.append(duplicate)
    for payload in mutations:
        with pytest.raises(ValueError):
            RedundantFragmentWorkOrderV2.from_dict(payload)
