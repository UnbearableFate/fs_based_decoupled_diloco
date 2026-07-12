from __future__ import annotations

from types import SimpleNamespace

import torch

from fs_diloco.atomic_io import read_json
from fs_diloco.config import Config
from fs_diloco.fragment_index import build_fragment_index
from fs_diloco.outer_optim import init_outer_state
from fs_diloco.param_index import build_param_index
from fs_diloco.paths import RunPaths, prepare_run_dirs
from fs_diloco.syncer import publish_materialized_view


class _Model(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.left = torch.nn.Parameter(torch.tensor([1.0, 2.0]))
        self.right = torch.nn.Parameter(torch.tensor([3.0, 4.0]))


def _view(*, commit_seq: int, optimizer_count: int, versions: tuple[int, int]):
    fragments = {
        index: SimpleNamespace(
            version=version,
            producing_commit_id=f"producer-{index}-{version}",
        )
        for index, version in enumerate(versions)
    }
    return SimpleNamespace(
        run_generation=1,
        commit_seq=commit_seq,
        optimizer_transition_count=optimizer_count,
        fragments=fragments,
        committed_interval_identities=frozenset(),
        commit_id=f"commit-{commit_seq}",
        frontier_sha256=f"{commit_seq:064x}",
        committed_state_digest=f"{commit_seq + 10:064x}",
        view_digest=f"{commit_seq + 20:064x}",
        total_seen_tokens=optimizer_count * 10,
        fencing_epoch=1,
        owner_id="owner",
        owner_session_id="owner-session",
    )


def test_materialization_reuses_unchanged_fragments_and_honors_cadence(tmp_path):
    config = Config()
    config.run.run_id = "p08-materialization"
    config.fragments.enabled = True
    config.fragments.materialize_full_every_events = 2
    paths = RunPaths(tmp_path)
    prepare_run_dirs(paths, 1)
    model = _Model()
    param_index = build_param_index(model, model_name_or_path="materialization-test")
    fragment_index = build_fragment_index(
        param_index, strategy="balanced_tensor", num_fragments=2
    )
    initial = {0: torch.tensor([1.0, 2.0]), 1: torch.tensor([3.0, 4.0])}
    initial_states = {
        key: init_outer_state(value, config.outer_optimizer)
        for key, value in initial.items()
    }

    first_path = publish_materialized_view(
        config=config,
        paths=paths,
        view=_view(commit_seq=1, optimizer_count=0, versions=(0, 0)),
        param_index=param_index,
        fragment_index=fragment_index,
        fragment_thetas=initial,
        outer_states=initial_states,
    )
    unchanged_path = paths.fragment_weight_path(1, 0)
    unchanged_stat = unchanged_path.stat()

    changed = {0: torch.tensor([5.0, 6.0]), 1: initial[1]}
    changed_states = {
        key: init_outer_state(value, config.outer_optimizer)
        for key, value in changed.items()
    }
    second_path = publish_materialized_view(
        config=config,
        paths=paths,
        view=_view(commit_seq=2, optimizer_count=1, versions=(1, 0)),
        param_index=param_index,
        fragment_index=fragment_index,
        fragment_thetas=changed,
        outer_states=changed_states,
    )
    second_latest = read_json(paths.latest_json)
    assert second_path == first_path
    assert second_latest["materialized_at_commit_seq"] == 1
    assert paths.fragment_weight_path(0, 1).is_file()
    assert unchanged_path.stat() == unchanged_stat

    third_path = publish_materialized_view(
        config=config,
        paths=paths,
        view=_view(commit_seq=3, optimizer_count=2, versions=(1, 0)),
        param_index=param_index,
        fragment_index=fragment_index,
        fragment_thetas=changed,
        outer_states=changed_states,
    )
    third_latest = read_json(paths.latest_json)
    assert third_path == paths.global_weight_path(3)
    assert third_path != first_path
    assert third_latest["materialized_at_commit_seq"] == 3
    assert third_latest["materialization_cadence"] == 2
