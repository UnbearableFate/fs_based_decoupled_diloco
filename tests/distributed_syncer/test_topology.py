from __future__ import annotations

import pytest

from fs_diloco.distributed_syncer.topology_manifest import TopologyManifestV1


def test_no_dedicated_syncer_topology_is_explicit():
    topology = TopologyManifestV1(
        learner_nodes=("node-0", "node-1"),
        learner_ids=("learner-0", "learner-1"),
        executor_ids=("executor-0", "executor-1"),
        committer_candidates=("member-0", "member-1"),
    )
    assert topology.to_dict()["dedicated_syncer_nodes"] == 0


def test_hidden_syncer_node_is_rejected():
    with pytest.raises(ValueError, match="dedicated syncer"):
        TopologyManifestV1(
            learner_nodes=("node-0",),
            learner_ids=("learner-0",),
            executor_ids=("executor-0",),
            committer_candidates=("member-0",),
            dedicated_syncer_nodes=1,
        )
