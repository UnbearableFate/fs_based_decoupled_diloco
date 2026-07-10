from __future__ import annotations

from fs_diloco.fragment_index import build_fragment_index, fragment_layout_digest
from fs_diloco.param_index import param_index_digest


def _param_index() -> dict:
    return {
        "format_version": 1,
        "model_name_or_path": "synthetic",
        "trainable_only": True,
        "total_numel": 6,
        "params": [
            {"name": "a", "shape": [2], "dtype": "torch.float32", "numel": 2, "offset": 0},
            {"name": "b", "shape": [4], "dtype": "torch.float32", "numel": 4, "offset": 2},
        ],
    }


def test_parameter_index_digest_is_order_stable_and_content_sensitive():
    original = _param_index()
    reordered_keys = {key: original[key] for key in reversed(original)}
    assert param_index_digest(original) == param_index_digest(reordered_keys)
    changed = _param_index()
    changed["params"][0] = {**changed["params"][0], "name": "changed"}
    assert param_index_digest(original) != param_index_digest(changed)


def test_fragment_layout_digest_ignores_host_source_path_but_binds_layout():
    index = _param_index()
    first = build_fragment_index(
        index,
        strategy="balanced_tensor",
        num_fragments=2,
        source_param_index_path="/host/a/index.json",
    )
    second = {**first, "source_param_index_path": "/different/host/index.json"}
    assert fragment_layout_digest(first) == fragment_layout_digest(second)
    full = build_fragment_index(index, strategy="full", num_fragments=1)
    assert fragment_layout_digest(first) != fragment_layout_digest(full)
