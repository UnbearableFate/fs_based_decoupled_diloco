import json

from fs_diloco.paths import RunPaths
from fs_diloco.retention import (
    cleanup_fragment_artifacts,
    cleanup_global_artifacts,
    cleanup_learner_update_artifacts,
    cleanup_syncer_model_artifacts,
)


def test_cleanup_global_artifacts_keeps_newest_versions(tmp_path):
    paths = RunPaths(tmp_path)
    paths.weights.mkdir(parents=True)
    paths.optim.mkdir(parents=True)
    for version in range(5):
        paths.global_weight_path(version).write_text("weight")
        paths.outer_optim_path(version).write_text("optim")

    deleted = cleanup_global_artifacts(paths, keep_last=3)

    assert deleted == 4
    assert sorted(path.name for path in paths.weights.glob("*.safetensors")) == [
        "global_v000002.safetensors",
        "global_v000003.safetensors",
        "global_v000004.safetensors",
    ]
    assert sorted(path.name for path in paths.optim.glob("*.safetensors")) == [
        "outer_v000002.safetensors",
        "outer_v000003.safetensors",
        "outer_v000004.safetensors",
    ]


def test_cleanup_learner_update_artifacts_keeps_newest_pairs(tmp_path):
    update_dir = tmp_path / "updates" / "pending" / "learner_000"
    update_dir.mkdir(parents=True)
    for step in range(100, 600, 100):
        tensor_path = update_dir / f"update_{step}.params.safetensors"
        meta_path = update_dir / f"update_{step}.meta.json"
        tensor_path.write_text("tensor")
        meta_path.write_text(
            json.dumps(
                {
                    "local_step_end": step,
                    "committed_at": float(step),
                    "file_path": str(tensor_path),
                }
            )
        )

    deleted = cleanup_learner_update_artifacts(update_dir, keep_last=3)

    assert deleted == 4
    assert sorted(path.name for path in update_dir.glob("*.meta.json")) == [
        "update_300.meta.json",
        "update_400.meta.json",
        "update_500.meta.json",
    ]
    assert sorted(path.name for path in update_dir.glob("*.params.safetensors")) == [
        "update_300.params.safetensors",
        "update_400.params.safetensors",
        "update_500.params.safetensors",
    ]


def test_cleanup_learner_update_artifacts_deletes_fragment_and_orphan_files(tmp_path):
    update_dir = tmp_path / "updates" / "pending" / "learner_000"
    update_dir.mkdir(parents=True)
    tensor_path = update_dir / "update_abc_fragment_002.params.safetensors"
    tensor_path.write_text("tensor")
    (update_dir / "update_abc_fragment_002.meta.json").write_text(
        json.dumps(
            {
                "local_step_end": 100,
                "committed_at": 1.0,
                "file_path": str(tensor_path),
            }
        )
    )
    (update_dir / "update_orphan.params.safetensors").write_text("orphan")
    (update_dir / "update_invalid.meta.json").write_text("not-json")
    (update_dir / ".update_partial.params.safetensors.abc.tmp").write_text("partial")

    deleted = cleanup_learner_update_artifacts(
        update_dir,
        keep_last=0,
        orphan_grace_seconds=0,
    )

    assert deleted == 5
    assert list(update_dir.iterdir()) == []


def test_cleanup_preserves_fresh_inflight_tensor_without_marker(tmp_path):
    update_dir = tmp_path / "updates" / "pending" / "learner_000"
    update_dir.mkdir(parents=True)
    inflight = update_dir / "update_inflight.params.safetensors"
    inflight.write_text("payload being published")

    deleted = cleanup_learner_update_artifacts(update_dir, keep_last=0)

    assert deleted == 0
    assert inflight.read_text() == "payload being published"


def test_cleanup_fragment_artifacts_keeps_newest_version_per_fragment(tmp_path):
    paths = RunPaths(tmp_path)
    for root in (paths.fragment_weights, paths.fragment_optim):
        for fragment_id in range(2):
            fragment_dir = root / f"fragment_{fragment_id:03d}"
            fragment_dir.mkdir(parents=True)
            for version in range(5):
                (fragment_dir / f"v{version:06d}.safetensors").write_text("artifact")

    deleted = cleanup_fragment_artifacts(paths, keep_last=1)

    assert deleted == 16
    for root in (paths.fragment_weights, paths.fragment_optim):
        for fragment_id in range(2):
            fragment_dir = root / f"fragment_{fragment_id:03d}"
            assert [path.name for path in fragment_dir.glob("*.safetensors")] == [
                "v000004.safetensors"
            ]


def test_cleanup_syncer_models_covers_full_and_fragment_layouts(tmp_path):
    paths = RunPaths(tmp_path)
    paths.weights.mkdir(parents=True)
    paths.optim.mkdir(parents=True)
    for version in range(3):
        paths.global_weight_path(version).write_text("weight")
        paths.outer_optim_path(version).write_text("optim")
        paths.fragment_weight_path(0, version).parent.mkdir(parents=True, exist_ok=True)
        paths.fragment_outer_optim_path(0, version).parent.mkdir(parents=True, exist_ok=True)
        paths.fragment_weight_path(0, version).write_text("fragment-weight")
        paths.fragment_outer_optim_path(0, version).write_text("fragment-optim")

    deleted = cleanup_syncer_model_artifacts(paths, keep_last=1)

    assert deleted == 8
    assert [path.name for path in paths.weights.glob("*.safetensors")] == [
        "global_v000002.safetensors"
    ]
    assert [path.name for path in paths.optim.glob("*.safetensors")] == [
        "outer_v000002.safetensors"
    ]
    fragment_weights = (paths.fragment_weights / "fragment_000").glob("*.safetensors")
    fragment_optim = (paths.fragment_optim / "fragment_000").glob("*.safetensors")
    assert [path.name for path in fragment_weights] == ["v000002.safetensors"]
    assert [path.name for path in fragment_optim] == ["v000002.safetensors"]
