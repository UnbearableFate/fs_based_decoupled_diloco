from __future__ import annotations

import hashlib
from pathlib import Path
import shutil

import pytest
import torch

from fs_diloco.fragment_index import build_fragment_index, save_fragment_index
from fs_diloco.log import ProductionTransactionalLog, RunSpec
from fs_diloco.log.bootstrap import bootstrap_new_generation
from fs_diloco.param_index import save_param_index
from fs_diloco.paths import RunPaths, prepare_run_dirs
from fs_diloco.runtime_view import build_runtime_view
from fs_diloco.storage import PosixStorageBackend
from fs_diloco.tensor_codec import save_global_weights


def _param_index() -> dict[str, object]:
    return {
        "format_version": 1,
        "model_name_or_path": "synthetic-tiny",
        "trainable_only": True,
        "total_numel": 2,
        "params": [
            {
                "name": "weight",
                "shape": [2],
                "dtype": "torch.float32",
                "numel": 2,
                "offset": 0,
            }
        ],
    }


def _workspace(tmp_path: Path, monkeypatch):
    source_config = Path(__file__).parents[2] / "configs" / "fs_diloco_tiny_local.yaml"
    config = tmp_path / "config.yaml"
    shutil.copyfile(source_config, config)
    monkeypatch.chdir(tmp_path)
    shared_root = tmp_path / "run"
    paths = RunPaths(shared_root)
    prepare_run_dirs(paths, num_learners=2)
    param_index = _param_index()
    save_param_index(param_index, paths.param_index_json)
    save_fragment_index(
        build_fragment_index(param_index, strategy="full", num_fragments=1),
        paths.fragment_index_json,
    )
    checkpoint = tmp_path / "source.safetensors"
    save_global_weights(checkpoint, torch.tensor([1.0, 2.0]), param_index)
    return config, shared_root, paths, checkpoint


def test_checkpoint_only_warm_start_creates_fresh_generation_without_history(
    tmp_path,
    monkeypatch,
):
    config, shared_root, paths, checkpoint = _workspace(tmp_path, monkeypatch)
    receipt = bootstrap_new_generation(
        config_path=config,
        run_id="warm-start-test",
        generation=1,
        shared_root=shared_root,
        params_paths={0: checkpoint},
        outer_paths={},
    )
    log = ProductionTransactionalLog.open(
        PosixStorageBackend(paths.authority),
        "warm-start-test",
        1,
    )
    view = build_runtime_view(log)

    assert view.commit_seq == 0
    assert view.consumed_proposal_ids == frozenset()
    assert log.spec.generation_kind == "warm_start"
    assert log.spec.source_checkpoint_digests == (
        hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
    )
    assert receipt["imported_proposal_history"] is False
    assert receipt["exact_continuation"] is False
    assert receipt["run_generation"] == 1

    forged = log.spec.to_dict()
    forged["generation_origin"]["exact_continuation"] = True
    with pytest.raises(ValueError, match="cannot claim exact historical continuation"):
        RunSpec.from_dict(forged)


def test_warm_start_rejects_generation_zero_and_incomplete_checkpoint_mapping(
    tmp_path,
    monkeypatch,
):
    config, shared_root, _paths, checkpoint = _workspace(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="fresh generation greater than zero"):
        bootstrap_new_generation(
            config_path=config,
            run_id="warm-start-zero",
            generation=0,
            shared_root=shared_root,
            params_paths={0: checkpoint},
            outer_paths={},
        )
    with pytest.raises(ValueError, match="frozen fragment layout"):
        bootstrap_new_generation(
            config_path=config,
            run_id="warm-start-missing",
            generation=1,
            shared_root=shared_root,
            params_paths={},
            outer_paths={},
        )
