"""Fresh distributed-generation bootstrap with revision-zero membership."""

from __future__ import annotations

from collections.abc import Sequence

from fs_diloco.config import Config
from fs_diloco.log.run import RunSpec
from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.syncer import _optimizer_config, _outer_schema_digest
from fs_diloco.testing.deterministic_reference import ReferenceWeightingConfig
from fs_diloco.log.production_codec import PRODUCTION_CODEC

from .executor import ExecutorBudget, execution_backend_identity
from .membership import DistributedMemberV1, MembershipRevisionV1


def revision_zero_membership(
    *, run_id: str, learner_ids: Sequence[str], node_ids: Sequence[str], budget: ExecutorBudget
) -> MembershipRevisionV1:
    if len(learner_ids) != len(node_ids) or not learner_ids:
        raise ValueError("bootstrap requires one learner per node")
    capability = canonical_digest(
        {
            "schema": "duraloco-prepare-capability-v1",
            "operations": ["get", "put_immutable"],
            "read_scope": "run-generation-immutable",
            "write_scope": "distributed-prepared",
            "budget": budget.to_dict(),
        }
    )
    members = tuple(
        DistributedMemberV1(
            member_id=f"member-{index:03d}",
            learner_id=learner_id,
            learner_session_id=f"{run_id}-{learner_id}-session",
            executor_id=f"executor-{index:03d}",
            executor_session_id=f"{run_id}-executor-{index:03d}-session",
            node_id=node_id,
            capability_digest=capability,
            committer_eligible=True,
        )
        for index, (learner_id, node_id) in enumerate(zip(learner_ids, node_ids, strict=True))
    )
    return MembershipRevisionV1.create(0, members)


def distributed_run_spec_factory(
    *,
    membership: MembershipRevisionV1,
    budget: ExecutorBudget,
    replication_factor: int = 1,
    error_resume: bool = False,
):
    backend_digest = canonical_digest(execution_backend_identity(threads=budget.threads))

    def build(config: Config, *, parameter_digest: str, layout_digest: str) -> RunSpec:
        return RunSpec(
            run_id=config.run.run_id or "",
            run_generation=config.init.run_generation,
            model_revision=config.model.name_or_path,
            parameter_index_digest=parameter_digest,
            fragment_layout_digest=layout_digest,
            outer_optimizer_schema_digest=_outer_schema_digest(config),
            optimizer_config=_optimizer_config(config),
            weighting_config=ReferenceWeightingConfig(staleness_lambda=0.2),
            max_global_staleness=config.sync.max_staleness_versions,
            max_fragment_staleness=config.sync.max_staleness_versions,
            payload_codec=PRODUCTION_CODEC,
            coordination_protocol=(
                "distributed-head-fenced-error-resume-v2"
                if error_resume
                else "distributed-head-fenced-v1"
            ),
            distributed_membership=membership,
            ownership_replication_factor=replication_factor,
            execution_backend_digest=backend_digest,
            prepare_capability_digest=membership.capability_set_digest,
        )

    return build
