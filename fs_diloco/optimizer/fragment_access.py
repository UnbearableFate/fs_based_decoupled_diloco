"""Canonical direct fragment gather/scatter over the existing index contracts."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any

import torch

from fs_diloco.fragment_index import (
    fragment_by_id,
    fragment_layout_digest,
    validate_fragment_index,
)
from fs_diloco.param_index import param_index_digest
from fs_diloco.protocol.canonical_json import canonical_digest


@dataclass(frozen=True)
class DirectSlice:
    param_name: str
    param_offset: int
    numel: int
    fragment_offset: int
    shape: tuple[int, ...]
    source_dtype: str

    def to_dict(self) -> dict[str, object]:
        return {
            "param_name": self.param_name,
            "param_offset": self.param_offset,
            "numel": self.numel,
            "fragment_offset": self.fragment_offset,
            "shape": list(self.shape),
            "source_dtype": self.source_dtype,
        }


@dataclass(frozen=True)
class FragmentAccessPlan:
    fragment_id: int
    parameter_index_digest: str
    fragment_layout_digest: str
    total_model_numel: int
    fragment_numel: int
    slices: tuple[DirectSlice, ...]
    plan_digest: str

    @classmethod
    def create(
        cls,
        param_index: dict[str, Any],
        fragment_index: dict[str, Any],
        fragment_id: int,
    ) -> "FragmentAccessPlan":
        validate_fragment_index(fragment_index, param_index)
        fragment = fragment_by_id(fragment_index, fragment_id)
        params = {str(item["name"]): item for item in param_index["params"]}
        cursor = 0
        slices: list[DirectSlice] = []
        for item in fragment["slices"]:
            name = str(item["param_name"])
            parameter = params.get(name)
            if parameter is None:
                raise ValueError(f"fragment references unknown parameter: {name}")
            param_offset = int(item.get("param_offset", 0))
            span = int(item["flat_end"]) - int(item["flat_start"])
            if span < 1 or param_offset < 0 or (
                param_offset + span > int(parameter["numel"])
            ):
                raise ValueError(f"fragment slice is outside parameter {name}")
            slices.append(
                DirectSlice(
                    param_name=name,
                    param_offset=param_offset,
                    numel=span,
                    fragment_offset=cursor,
                    shape=tuple(int(value) for value in parameter["shape"]),
                    source_dtype=str(parameter["dtype"]),
                )
            )
            cursor += span
        if cursor != int(fragment["numel"]):
            raise ValueError("direct fragment plan size differs from fragment index")
        parameter_digest = param_index_digest(param_index)
        layout_digest = fragment_layout_digest(fragment_index)
        identity = {
            "schema": "duraloco-fragment-access-plan-v1",
            "fragment_id": int(fragment_id),
            "parameter_index_digest": parameter_digest,
            "fragment_layout_digest": layout_digest,
            "total_model_numel": int(param_index["total_numel"]),
            "fragment_numel": cursor,
            "slices": [item.to_dict() for item in slices],
        }
        return cls(
            fragment_id=int(fragment_id),
            parameter_index_digest=parameter_digest,
            fragment_layout_digest=layout_digest,
            total_model_numel=int(param_index["total_numel"]),
            fragment_numel=cursor,
            slices=tuple(slices),
            plan_digest=canonical_digest(identity),
        )

    @property
    def fragment_bytes_float32(self) -> int:
        return self.fragment_numel * 4

    @property
    def whole_model_bytes_float32(self) -> int:
        return self.total_model_numel * 4

    def gather_model(
        self,
        model: torch.nn.Module,
        *,
        dtype: torch.dtype = torch.float32,
        device: torch.device | str = "cpu",
    ) -> torch.Tensor:
        named = dict(model.named_parameters())
        result = torch.empty(self.fragment_numel, dtype=dtype, device=device)
        for item in self.slices:
            parameter = named.get(item.param_name)
            if parameter is None:
                raise ValueError(f"model is missing parameter {item.param_name}")
            source = parameter.detach().reshape(-1)
            if int(source.numel()) < item.param_offset + item.numel:
                raise ValueError(f"model parameter {item.param_name} changed shape")
            target = result[item.fragment_offset : item.fragment_offset + item.numel]
            target.copy_(
                source[item.param_offset : item.param_offset + item.numel].to(
                    device=device, dtype=dtype, non_blocking=False
                )
            )
        return result.contiguous()

    @torch.no_grad()
    def scatter_model(
        self,
        model: torch.nn.Module,
        fragment: torch.Tensor,
    ) -> None:
        flat = fragment.detach().reshape(-1)
        if int(flat.numel()) != self.fragment_numel:
            raise ValueError(
                f"fragment has {flat.numel()} values, expected {self.fragment_numel}"
            )
        named = dict(model.named_parameters())
        for item in self.slices:
            parameter = named.get(item.param_name)
            if parameter is None:
                raise ValueError(f"model is missing parameter {item.param_name}")
            source = flat[item.fragment_offset : item.fragment_offset + item.numel]
            if parameter.is_contiguous():
                target = parameter.view(-1)[
                    item.param_offset : item.param_offset + item.numel
                ]
                target.copy_(source.to(device=target.device, dtype=target.dtype))
            else:
                # ``reshape`` of a non-contiguous parameter is a copy. Update
                # that logical flat order and explicitly copy the shaped value
                # back so the parameter storage, not a temporary, is mutated.
                updated = parameter.detach().reshape(-1).clone()
                updated[item.param_offset : item.param_offset + item.numel].copy_(
                    source.to(device=updated.device, dtype=updated.dtype)
                )
                parameter.copy_(updated.reshape(parameter.shape))


class FragmentAccessPlanCache:
    """Deletable process-local layout cache keyed only by frozen digests."""

    def __init__(self) -> None:
        self._plans: dict[tuple[str, str, int], FragmentAccessPlan] = {}
        self._lock = Lock()

    def get(
        self,
        param_index: dict[str, Any],
        fragment_index: dict[str, Any],
        fragment_id: int,
    ) -> FragmentAccessPlan:
        key = (
            param_index_digest(param_index),
            fragment_layout_digest(fragment_index),
            int(fragment_id),
        )
        with self._lock:
            plan = self._plans.get(key)
            if plan is None:
                plan = FragmentAccessPlan.create(
                    param_index, fragment_index, fragment_id
                )
                self._plans[key] = plan
            return plan

    def clear(self) -> None:
        with self._lock:
            self._plans.clear()


def model_parameter_norm(model: torch.nn.Module) -> float:
    """Compute the full norm without constructing a whole-model flat copy."""

    total = torch.zeros((), dtype=torch.float64)
    for parameter in model.parameters():
        values = parameter.detach().to(device="cpu", dtype=torch.float64)
        total.add_(torch.sum(values * values))
    return float(torch.sqrt(total).item())
