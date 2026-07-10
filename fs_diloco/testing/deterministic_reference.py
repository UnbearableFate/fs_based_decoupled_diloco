"""Pure-float deterministic reducer and outer-optimizer oracle."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping

from fs_diloco.protocol.canonical_json import canonical_digest


Vector = tuple[float, ...]


@dataclass(frozen=True)
class ReferenceWeightingConfig:
    """Deterministic token-by-staleness weighting frozen for P02."""

    staleness_function: str = "rational"
    staleness_lambda: float = 0.2

    def __post_init__(self) -> None:
        if not isinstance(self.staleness_function, str):
            raise ValueError("staleness_function must be a string")
        try:
            staleness_lambda = float(self.staleness_lambda)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("staleness_lambda must be numeric") from exc
        object.__setattr__(self, "staleness_lambda", staleness_lambda)
        if self.staleness_function != "rational":
            raise ValueError("P02 supports only rational staleness weighting")
        if not math.isfinite(self.staleness_lambda) or self.staleness_lambda < 0.0:
            raise ValueError("staleness_lambda must be finite and non-negative")

    def identity(self) -> dict[str, object]:
        return {
            "staleness_function": self.staleness_function,
            "staleness_lambda": self.staleness_lambda.hex(),
            "token_weight": True,
        }


@dataclass(frozen=True)
class ReferenceOptimizerConfig:
    name: str = "nesterov"
    lr: float = 0.7
    momentum: float = 0.9
    weight_decay: float = 0.0
    betas: tuple[float, float] = (0.9, 0.999)
    eps: float = 1.0e-8

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise ValueError("optimizer name must be a string")
        try:
            lr = float(self.lr)
            momentum = float(self.momentum)
            weight_decay = float(self.weight_decay)
            betas = tuple(float(value) for value in self.betas)
            eps = float(self.eps)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("optimizer numeric configuration is invalid") from exc
        object.__setattr__(self, "lr", lr)
        object.__setattr__(self, "momentum", momentum)
        object.__setattr__(self, "weight_decay", weight_decay)
        object.__setattr__(self, "betas", betas)
        object.__setattr__(self, "eps", eps)
        if self.name.lower() not in {"sgd", "momentum", "nesterov", "adamw"}:
            raise ValueError(f"unsupported optimizer: {self.name}")
        if not math.isfinite(self.lr) or self.lr <= 0.0:
            raise ValueError("optimizer lr must be finite and positive")
        if not math.isfinite(self.momentum) or self.momentum < 0.0:
            raise ValueError("optimizer momentum must be finite and non-negative")
        if not math.isfinite(self.weight_decay) or self.weight_decay < 0.0:
            raise ValueError("optimizer weight_decay must be finite and non-negative")
        if len(self.betas) != 2 or any(
            not math.isfinite(value) or value < 0.0 or value >= 1.0
            for value in self.betas
        ):
            raise ValueError("optimizer betas must be finite values in [0, 1)")
        if not math.isfinite(self.eps) or self.eps <= 0.0:
            raise ValueError("optimizer eps must be finite and positive")

    def identity(self) -> dict[str, object]:
        return {
            "name": self.name.lower(),
            "lr": self.lr.hex(),
            "momentum": self.momentum.hex(),
            "weight_decay": self.weight_decay.hex(),
            "betas": [value.hex() for value in self.betas],
            "eps": self.eps.hex(),
            "implementation": "stdlib-float64-v1",
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.identity())


@dataclass(frozen=True)
class ReferenceOptimizerState:
    step: int
    momentum: Vector = ()
    exp_avg: Vector = ()
    exp_avg_sq: Vector = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "momentum", tuple(self.momentum))
        object.__setattr__(self, "exp_avg", tuple(self.exp_avg))
        object.__setattr__(self, "exp_avg_sq", tuple(self.exp_avg_sq))

    def identity(self) -> dict[str, object]:
        return {
            "step": self.step,
            "momentum": [value.hex() for value in self.momentum],
            "exp_avg": [value.hex() for value in self.exp_avg],
            "exp_avg_sq": [value.hex() for value in self.exp_avg_sq],
        }


def _finite(vector: Iterable[float], name: str) -> Vector:
    result = tuple(float(value) for value in vector)
    if not all(math.isfinite(value) for value in result):
        raise ValueError(f"{name} contains a non-finite value")
    return result


def initial_state(size: int, config: ReferenceOptimizerConfig) -> ReferenceOptimizerState:
    if size < 1:
        raise ValueError("optimizer vector size must be positive")
    zeros = (0.0,) * size
    if config.name.lower() in {"sgd", "momentum", "nesterov"}:
        return ReferenceOptimizerState(step=0, momentum=zeros)
    if config.name.lower() == "adamw":
        return ReferenceOptimizerState(step=0, exp_avg=zeros, exp_avg_sq=zeros)
    raise ValueError(f"unsupported optimizer: {config.name}")


def normalized_weights(
    token_counts: Mapping[str, int],
    *,
    staleness: Mapping[str, int] | None = None,
    config: ReferenceWeightingConfig | None = None,
) -> dict[str, float]:
    if not token_counts or any(type(value) is not int or value <= 0 for value in token_counts.values()):
        raise ValueError("token counts must be positive integers")
    weighting = config or ReferenceWeightingConfig()
    staleness_by_id = (
        {key: 0 for key in token_counts} if staleness is None else staleness
    )
    if set(staleness_by_id) != set(token_counts) or any(
        type(value) is not int or value < 0 for value in staleness_by_id.values()
    ):
        raise ValueError("staleness must contain one non-negative integer per proposal")
    raw = {
        key: token_counts[key]
        / (1.0 + weighting.staleness_lambda * staleness_by_id[key])
        for key in sorted(token_counts)
    }
    total = math.fsum(raw[key] for key in sorted(raw))
    if not math.isfinite(total) or total <= 0.0:
        raise ValueError("effective proposal weight sum must be finite and positive")
    return {key: raw[key] / total for key in sorted(raw)}


def weighted_reduce(vectors: Mapping[str, Vector], weights: Mapping[str, float]) -> Vector:
    if set(vectors) != set(weights) or not vectors:
        raise ValueError("vectors and weights must have the same non-empty IDs")
    ordered = sorted(vectors)
    size = len(vectors[ordered[0]])
    if size < 1 or any(len(vectors[key]) != size for key in ordered):
        raise ValueError("all vectors must have equal positive length")
    if any(not math.isfinite(weights[key]) or weights[key] <= 0 for key in ordered):
        raise ValueError("weights must be finite and positive")
    weight_sum = math.fsum(weights[key] for key in ordered)
    if weight_sum <= 0:
        raise ValueError("weight sum must be positive")
    return tuple(
        math.fsum(weights[key] * _finite(vectors[key], key)[index] for key in ordered)
        / weight_sum
        for index in range(size)
    )


def outer_step(
    theta: Vector,
    gradient: Vector,
    state: ReferenceOptimizerState,
    config: ReferenceOptimizerConfig,
) -> tuple[Vector, ReferenceOptimizerState]:
    theta = _finite(theta, "theta")
    gradient = _finite(gradient, "gradient")
    if len(theta) != len(gradient) or not theta:
        raise ValueError("theta and gradient must have equal positive length")
    step = state.step + 1
    name = config.name.lower()
    if name in {"sgd", "momentum", "nesterov"}:
        momentum = state.momentum or (0.0,) * len(theta)
        if len(momentum) != len(theta):
            raise ValueError("momentum size mismatch")
        adjusted = tuple(
            grad + config.weight_decay * parameter
            for parameter, grad in zip(theta, gradient, strict=True)
        )
        if name == "sgd" or config.momentum == 0.0:
            next_momentum = (0.0,) * len(theta)
            update = adjusted
        else:
            next_momentum = tuple(
                config.momentum * old + grad
                for old, grad in zip(momentum, adjusted, strict=True)
            )
            if name == "nesterov":
                update = tuple(
                    grad + config.momentum * moment
                    for grad, moment in zip(adjusted, next_momentum, strict=True)
                )
            else:
                update = next_momentum
        next_theta = tuple(
            parameter - config.lr * delta for parameter, delta in zip(theta, update, strict=True)
        )
        return next_theta, ReferenceOptimizerState(step=step, momentum=next_momentum)
    if name == "adamw":
        beta1, beta2 = config.betas
        exp_avg = state.exp_avg or (0.0,) * len(theta)
        exp_avg_sq = state.exp_avg_sq or (0.0,) * len(theta)
        if len(exp_avg) != len(theta) or len(exp_avg_sq) != len(theta):
            raise ValueError("AdamW state size mismatch")
        decayed = tuple(
            parameter * (1.0 - config.lr * config.weight_decay) for parameter in theta
        )
        next_avg = tuple(
            beta1 * old + (1.0 - beta1) * grad
            for old, grad in zip(exp_avg, gradient, strict=True)
        )
        next_avg_sq = tuple(
            beta2 * old + (1.0 - beta2) * grad * grad
            for old, grad in zip(exp_avg_sq, gradient, strict=True)
        )
        correction1 = 1.0 - beta1**step
        correction2 = 1.0 - beta2**step
        next_theta = tuple(
            parameter
            - config.lr
            * (mean / correction1)
            / (math.sqrt(variance / correction2) + config.eps)
            for parameter, mean, variance in zip(decayed, next_avg, next_avg_sq, strict=True)
        )
        return next_theta, ReferenceOptimizerState(
            step=step,
            exp_avg=next_avg,
            exp_avg_sq=next_avg_sq,
        )
    raise ValueError(f"unsupported optimizer: {config.name}")


def vector_identity(vector: Vector) -> list[str]:
    return [value.hex() for value in _finite(vector, "vector")]


def optimizer_state_digest(
    theta: Vector,
    state: ReferenceOptimizerState,
    config: ReferenceOptimizerConfig,
) -> str:
    return canonical_digest(
        {
            "theta": vector_identity(theta),
            "state": state.identity(),
            "config": config.identity(),
        }
    )
