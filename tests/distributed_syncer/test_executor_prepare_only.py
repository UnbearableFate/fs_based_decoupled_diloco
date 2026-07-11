from __future__ import annotations

import ast
from pathlib import Path

import torch

from fs_diloco.distributed_syncer.executor import (
    ExecutorBudget,
    execute_work_order,
    execution_backend_identity,
)
from fs_diloco.distributed_syncer.layout import DistributedLayout
from fs_diloco.distributed_syncer.prepared_store import load_prepared_attempt
from fs_diloco.log.layout import LogLayout
from fs_diloco.outer_optim import init_outer_state
from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.protocol.work_order_v1 import FragmentWorkOrderV1
from fs_diloco.storage import InMemoryStorageBackend
from fs_diloco.syncer_core.capabilities import PrepareObjectFacade
from fs_diloco.testing.deterministic_reference import ReferenceOptimizerConfig


def _order(layout: DistributedLayout, *, threads: int = 1) -> FragmentWorkOrderV1:
    return FragmentWorkOrderV1.with_computed_id(
        {
            "schema": FragmentWorkOrderV1.SCHEMA,
            "run_id": layout.log.run_id,
            "run_generation": layout.log.run_generation,
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
            "execution_backend_digest": canonical_digest(
                execution_backend_identity(threads=threads)
            ),
            "parameter_index_digest": "6" * 64,
            "fragment_layout_digest": "7" * 64,
        }
    )


def test_executor_publishes_parameter_state_result_attempt_then_marker():
    backend = InMemoryStorageBackend()
    layout = DistributedLayout(LogLayout("distributed-test", 1))
    facade = PrepareObjectFacade(
        backend,
        read_prefixes=(layout.log.immutable_prefix,),
        write_prefixes=(layout.prepared_prefix,),
    )
    order = _order(layout)
    params = torch.tensor([1.0, 2.0], dtype=torch.float32)
    optimizer = ReferenceOptimizerConfig(name="nesterov", lr=0.1, momentum=0.9)
    state = init_outer_state(params, optimizer)
    result, envelope = execute_work_order(
        facade=facade,
        layout=layout,
        order=order,
        current_params=params,
        current_outer_state=state,
        proposal_tensors={"proposal-a": torch.tensor([0.5, 1.5])},
        optimizer_config=optimizer,
        executor_id="executor-0",
        executor_session_id="session-0",
        attempt_id="attempt-0",
        resource_evidence_digest="8" * 64,
        budget=ExecutorBudget(threads=1, max_rss_bytes=1024**4),
    )
    marker_key = layout.marker_key(order.work_order_id, envelope.attempt_envelope_id)
    loaded_result, loaded_envelope = load_prepared_attempt(backend, marker_key)
    assert loaded_result == result
    assert loaded_envelope == envelope
    operations = [record.key for record in backend.history if record.operation == "put_immutable"]
    assert operations[-1] == marker_key
    assert not hasattr(facade, "conditional_replace")
    assert not hasattr(facade, "list_prefix")


def test_executor_dependency_graph_has_no_authority_api():
    source = Path(__file__).resolve().parents[2] / "fs_diloco/distributed_syncer/executor.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any(name.startswith("fs_diloco.storage") for name in imports)
    assert not any(name.startswith("fs_diloco.coordination") for name in imports)
    assert "fs_diloco.log.production" not in imports
