from __future__ import annotations

import torch

from fs_diloco.fragment_codec import extract_fragment, scatter_fragment
from fs_diloco.fragment_index import build_fragment_index
from fs_diloco.optimizer.fragment_access import FragmentAccessPlanCache
from fs_diloco.param_index import build_param_index, flatten_trainable_params


class _Model(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.left = torch.nn.Parameter(
            torch.arange(12, dtype=torch.float32).reshape(3, 4).t()
        )
        self.middle = torch.nn.Parameter(torch.arange(7, dtype=torch.float64))
        self.right = torch.nn.Parameter(torch.arange(10, dtype=torch.float32).reshape(2, 5))


def test_direct_gather_and_scatter_match_legacy_for_every_balanced_fragment():
    model = _Model()
    param_index = build_param_index(model, model_name_or_path="direct-test")
    fragment_index = build_fragment_index(
        param_index, strategy="balanced_tensor", num_fragments=3
    )
    cache = FragmentAccessPlanCache()
    original = flatten_trainable_params(model, param_index, dtype=torch.float32)
    for fragment_id in range(3):
        plan = cache.get(param_index, fragment_index, fragment_id)
        direct = plan.gather_model(model)
        legacy = extract_fragment(original, fragment_index, fragment_id)
        assert torch.equal(direct, legacy)

        replacement = direct.add(100 + fragment_id)
        expected = scatter_fragment(original, fragment_index, fragment_id, replacement)
        clone = _Model()
        clone.load_state_dict(model.state_dict())
        plan.scatter_model(clone, replacement)
        actual = flatten_trainable_params(clone, param_index, dtype=torch.float32)
        assert torch.equal(actual, expected)


def test_process_local_layout_cache_is_canonical_and_deletable():
    model = _Model()
    param_index = build_param_index(model, model_name_or_path="cache-test")
    fragment_index = build_fragment_index(
        param_index, strategy="balanced_tensor", num_fragments=2
    )
    cache = FragmentAccessPlanCache()
    first = cache.get(param_index, fragment_index, 0)
    assert cache.get(param_index, fragment_index, 0) is first
    assert first.fragment_numel < first.total_model_numel
    assert first.fragment_bytes_float32 < first.whole_model_bytes_float32
    cache.clear()
    second = cache.get(param_index, fragment_index, 0)
    assert second is not first
    assert second.plan_digest == first.plan_digest
