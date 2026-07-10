from __future__ import annotations

import hashlib

from fs_diloco.log import RunSpec, TransactionalLog, replay_log
from fs_diloco.log.model import ReferenceProposal


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def spec(run_id: str = "p04-test") -> RunSpec:
    return RunSpec(
        run_id=run_id,
        run_generation=0,
        model_revision="gpt2-test-revision",
        parameter_index_digest=digest("parameter-index"),
        fragment_layout_digest=digest("fragment-layout"),
        outer_optimizer_schema_digest=digest("outer-optimizer-schema"),
    )


def initialize(backend, run_id: str = "p04-test", fragment_count: int = 2) -> TransactionalLog:
    return TransactionalLog.initialize(
        backend,
        spec(run_id),
        {fragment_id: (0.0, 0.0) for fragment_id in range(fragment_count)},
    )


def proposal(
    log: TransactionalLog,
    *,
    learner: str,
    sequence: int,
    fragment_id: int = 0,
    values: tuple[float, ...] = (1.0, -1.0),
) -> ReferenceProposal:
    current = replay_log(log).head_frontier
    item = ReferenceProposal.create(
        learner_id=learner,
        session_id=f"session-{learner}",
        sequence=sequence,
        fragment_id=fragment_id,
        base_commit_id=current.commit_id,
        base_commit_seq=current.commit_seq,
        base_fragment_version=current.fragments[fragment_id].version,
        target_tokens=100 + sequence,
        values=values,
    )
    log.publish_proposal(item)
    return item
