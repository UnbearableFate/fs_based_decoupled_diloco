from __future__ import annotations

import pytest

from fs_diloco.distributed_syncer.hedge_policy import (
    RedundancyPolicyV1,
    execution_eligible,
)


def test_redundancy_modes_have_one_canonical_spelling():
    active = RedundancyPolicyV1.from_dict({"mode": "active_active"})
    warm = RedundancyPolicyV1.from_dict({"mode": "warm_standby"})
    hedged = RedundancyPolicyV1.from_dict(
        {"mode": "hedged", "hedge_delay_ms": 6000}
    )
    assert active.to_dict() == {"mode": "active_active"}
    assert warm.to_dict() == {"mode": "warm_standby"}
    assert hedged.to_dict() == {"mode": "hedged", "hedge_delay_ms": 6000}
    for bad in (
        {"mode": "hedged"},
        {"mode": "hedged", "hedge_delay_ms": 0},
        {"mode": "active_active", "hedge_delay_ms": 1},
        {"mode": "warm_standby", "hedge_delay_ms": None},
        {"mode": "fastest"},
    ):
        with pytest.raises(ValueError):
            RedundancyPolicyV1.from_dict(bad)


def test_execution_eligibility_is_mode_and_role_deterministic():
    active = RedundancyPolicyV1.from_dict({"mode": "active_active"})
    warm = RedundancyPolicyV1.from_dict({"mode": "warm_standby"})
    hedge = RedundancyPolicyV1.from_dict({"mode": "hedged", "hedge_delay_ms": 6000})
    assert execution_eligible(active, owner_role="primary", elapsed_ms=0)
    assert execution_eligible(active, owner_role="backup", elapsed_ms=0)
    assert execution_eligible(warm, owner_role="primary", elapsed_ms=0)
    assert not execution_eligible(warm, owner_role="backup", elapsed_ms=99999)
    assert execution_eligible(
        warm, owner_role="backup", elapsed_ms=0, backup_activated=True
    )
    assert not execution_eligible(hedge, owner_role="backup", elapsed_ms=5999)
    assert execution_eligible(hedge, owner_role="backup", elapsed_ms=6000)
