from __future__ import annotations

import pytest
import torch

from fs_diloco.outer_optim import OuterOptimizerConfig, init_outer_state, outer_optimizer_step
from fs_diloco.testing.deterministic_reference import (
    ReferenceOptimizerConfig,
    initial_state,
    normalized_weights,
    outer_step,
)
from fs_diloco.testing.oracles import assert_vector_close, fragment_count_one_step


def test_weighting_requires_one_explicit_staleness_per_proposal():
    with pytest.raises(ValueError, match="staleness"):
        normalized_weights({"p": 10}, staleness={})


@pytest.mark.parametrize(
    "config",
    [
        ReferenceOptimizerConfig(name="sgd", lr=0.1),
    ],
)
def test_valid_reference_optimizer_config_constructs(config):
    assert config.lr > 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "unknown"},
        {"lr": float("nan")},
        {"weight_decay": -1.0},
        {"betas": (0.9, 1.0)},
        {"eps": 0.0},
    ],
)
def test_invalid_reference_optimizer_contract_is_rejected(kwargs):
    with pytest.raises(ValueError):
        ReferenceOptimizerConfig(**kwargs)


@pytest.mark.parametrize("name", ["sgd", "momentum", "nesterov", "adamw"])
def test_reference_optimizer_matches_legacy_torch_fragment_count_one(name):
    reference_config = ReferenceOptimizerConfig(
        name=name,
        lr=0.03,
        momentum=0.8,
        weight_decay=0.01,
        betas=(0.7, 0.95),
        eps=1.0e-8,
    )
    legacy_config = OuterOptimizerConfig(
        name=name,
        lr=reference_config.lr,
        momentum=reference_config.momentum,
        weight_decay=reference_config.weight_decay,
        betas=reference_config.betas,
        eps=reference_config.eps,
    )
    theta_tuple = (1.0, -2.0, 0.5)
    state = initial_state(len(theta_tuple), reference_config)
    theta = torch.tensor(theta_tuple, dtype=torch.float32)
    legacy_state = init_outer_state(theta, legacy_config)
    for gradient_tuple in ((0.1, -0.2, 0.3), (-0.4, 0.5, 0.2), (0.0, -0.1, 0.7)):
        reference_theta, state = outer_step(
            theta_tuple, gradient_tuple, state, reference_config
        )
        legacy_theta, legacy_state = outer_optimizer_step(
            theta,
            torch.tensor(gradient_tuple, dtype=torch.float32),
            legacy_state,
            legacy_config,
        )
        assert_vector_close(reference_theta, tuple(legacy_theta.tolist()))
        fragment_theta, fragment_state = fragment_count_one_step(
            theta_tuple,
            gradient_tuple,
            initial_state(len(theta_tuple), reference_config)
            if state.step == 1
            else previous_state,
            reference_config,
        )
        assert_vector_close(fragment_theta, reference_theta)
        assert fragment_state == state
        theta_tuple = reference_theta
        theta = legacy_theta
        previous_state = state
