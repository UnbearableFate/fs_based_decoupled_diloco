from __future__ import annotations

import hashlib

import pytest
import torch

from fs_diloco.coordination import OwnerToken
from fs_diloco.distributed_syncer.membership import (
    DistributedMemberV1,
    MembershipRevisionV1,
)
from fs_diloco.log import CommitConflict, ProductionTransactionalLog, RunSpec
from fs_diloco.log.production_codec import (
    PRODUCTION_CODEC,
    encode_production_outer_state,
    encode_production_params,
)
from fs_diloco.outer_optim import init_outer_state
from fs_diloco.runtime_view import build_runtime_view
from fs_diloco.storage import InMemoryStorageBackend


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _membership() -> MembershipRevisionV1:
    members = tuple(
        DistributedMemberV1(
            member_id=f"member-{index}",
            learner_id=f"learner-{index}",
            learner_session_id=f"learner-session-{index}",
            executor_id=f"executor-{index}",
            executor_session_id=f"executor-session-{index}",
            node_id=f"node-{index}",
            capability_digest=f"{index + 1:064x}",
            committer_eligible=True,
        )
        for index in range(2)
    )
    return MembershipRevisionV1.create(0, members)


def _log(run_id: str, *, protocol: str):
    membership = _membership()
    spec = RunSpec(
        run_id=run_id,
        run_generation=1,
        model_revision="error-resume-test",
        parameter_index_digest=_digest("params"),
        fragment_layout_digest=_digest("layout"),
        outer_optimizer_schema_digest=_digest("outer"),
        payload_codec=PRODUCTION_CODEC,
        coordination_protocol=protocol,
        distributed_membership=membership,
        ownership_replication_factor=2,
        execution_backend_digest=_digest("backend"),
        prepare_capability_digest=_digest("capability"),
    )
    params = torch.tensor([0.0, 0.0])
    return ProductionTransactionalLog.initialize(
        InMemoryStorageBackend(),
        spec,
        {
            0: (
                encode_production_params(params),
                encode_production_outer_state(
                    init_outer_state(params, spec.optimizer_config)
                ),
            )
        },
    )


def test_error_stop_resumes_under_new_fence_without_changing_optimizer_state():
    log = _log(
        "p08-error-resume",
        protocol="distributed-head-fenced-error-resume-v2",
    )
    first = OwnerToken("member-0", "owner-session-0", 1)
    log.activate_owner(token=first, request_id="activate-first")
    before_stop = build_runtime_view(log)
    log.commit_stop(reason="error", request_id="truthful-error")
    stopped = build_runtime_view(log)
    assert stopped.authoritative_stop is not None
    assert stopped.authoritative_stop.reason == "error"

    reopened = ProductionTransactionalLog.open(
        log.backend, log.spec.run_id, log.spec.run_generation
    )
    second = OwnerToken("member-1", "owner-session-1", 2)
    reopened.resume_error(token=second, request_id="resume-after-error")
    resumed = build_runtime_view(reopened, force_full=True)

    assert resumed.authoritative_stop is None
    assert resumed.optimizer_transition_count == before_stop.optimizer_transition_count
    assert resumed.fragments == before_stop.fragments
    assert resumed.membership == before_stop.membership
    assert resumed.fencing_epoch == 2
    assert resumed.owner_id == second.owner_id
    assert resumed.commit_seq == stopped.commit_seq + 1


@pytest.mark.parametrize("reason", ["completed", "stop_after_outer_steps"])
def test_normal_terminal_stops_remain_irreversible(reason):
    log = _log(
        f"p08-no-resume-{reason}",
        protocol="distributed-head-fenced-error-resume-v2",
    )
    log.activate_owner(
        token=OwnerToken("member-0", "owner-session-0", 1),
        request_id="activate",
    )
    log.commit_stop(reason=reason, request_id=f"stop-{reason}")
    with pytest.raises(CommitConflict, match="only an authoritative error"):
        log.resume_error(
            token=OwnerToken("member-1", "owner-session-1", 2),
            request_id="forbidden-resume",
        )


def test_v1_generation_cannot_emit_resume():
    log = _log("p08-v1-no-resume", protocol="distributed-head-fenced-v1")
    log.activate_owner(
        token=OwnerToken("member-0", "owner-session-0", 1),
        request_id="activate",
    )
    log.commit_stop(reason="error", request_id="error")
    with pytest.raises(CommitConflict, match="does not enable error resume"):
        log.resume_error(
            token=OwnerToken("member-1", "owner-session-1", 2),
            request_id="v1-resume",
        )
