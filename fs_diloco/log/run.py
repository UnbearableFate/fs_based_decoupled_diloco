"""Frozen run configuration and immutable run-manifest representation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from fs_diloco.protocol.canonical_json import canonical_bytes, canonical_digest
from fs_diloco.protocol.identities import validate_sha256
from fs_diloco.protocol.schemas import ObjectRef
from fs_diloco.testing.deterministic_reference import (
    ReferenceOptimizerConfig,
    ReferenceWeightingConfig,
)

from .codec import canonical_object
from .errors import VerificationError


@dataclass(frozen=True)
class RunSpec:
    run_id: str
    run_generation: int
    model_revision: str
    parameter_index_digest: str
    fragment_layout_digest: str
    outer_optimizer_schema_digest: str
    optimizer_config: ReferenceOptimizerConfig = field(
        default_factory=ReferenceOptimizerConfig
    )
    weighting_config: ReferenceWeightingConfig = field(
        default_factory=ReferenceWeightingConfig
    )
    max_global_staleness: int = 64
    max_fragment_staleness: int = 4

    def __post_init__(self) -> None:
        for value, name in ((self.run_id, "run_id"), (self.model_revision, "model_revision")):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if type(self.run_generation) is not int or self.run_generation < 0:
            raise ValueError("run_generation must be a non-negative integer")
        for value, name in (
            (self.parameter_index_digest, "parameter_index_digest"),
            (self.fragment_layout_digest, "fragment_layout_digest"),
            (self.outer_optimizer_schema_digest, "outer_optimizer_schema_digest"),
        ):
            validate_sha256(value, field=name)
        for value, name in (
            (self.max_global_staleness, "max_global_staleness"),
            (self.max_fragment_staleness, "max_fragment_staleness"),
        ):
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": 2,
            "run_id": self.run_id,
            "run_generation": self.run_generation,
            "model_revision": self.model_revision,
            "parameter_index_digest": self.parameter_index_digest,
            "fragment_layout_digest": self.fragment_layout_digest,
            "outer_optimizer_schema_digest": self.outer_optimizer_schema_digest,
            "optimizer_config": self.optimizer_config.identity(),
            "weighting_config": self.weighting_config.identity(),
            "protocol_config": {
                "max_global_staleness": self.max_global_staleness,
                "max_fragment_staleness": self.max_fragment_staleness,
            },
            "payload_codec": "canonical-float-hex-v1",
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RunSpec":
        required = {
            "protocol_version",
            "run_id",
            "run_generation",
            "model_revision",
            "parameter_index_digest",
            "fragment_layout_digest",
            "outer_optimizer_schema_digest",
            "optimizer_config",
            "weighting_config",
            "protocol_config",
            "payload_codec",
        }
        if set(payload) != required or payload.get("protocol_version") != 2:
            raise ValueError("invalid run specification fields or protocol version")
        if payload.get("payload_codec") != "canonical-float-hex-v1":
            raise ValueError("unsupported run payload codec")
        optimizer = payload["optimizer_config"]
        weighting = payload["weighting_config"]
        protocol = payload["protocol_config"]
        if not isinstance(optimizer, dict) or set(optimizer) != {
            "name",
            "lr",
            "momentum",
            "weight_decay",
            "betas",
            "eps",
            "implementation",
        }:
            raise ValueError("invalid optimizer configuration")
        if optimizer["implementation"] != "stdlib-float64-v1":
            raise ValueError("unsupported optimizer implementation")
        if not isinstance(optimizer["betas"], list) or len(optimizer["betas"]) != 2:
            raise ValueError("invalid optimizer beta encoding")
        optimizer_config = ReferenceOptimizerConfig(
            name=optimizer["name"],
            lr=float.fromhex(optimizer["lr"]),
            momentum=float.fromhex(optimizer["momentum"]),
            weight_decay=float.fromhex(optimizer["weight_decay"]),
            betas=tuple(float.fromhex(value) for value in optimizer["betas"]),
            eps=float.fromhex(optimizer["eps"]),
        )
        if optimizer_config.identity() != optimizer:
            raise ValueError("optimizer configuration is not canonical")
        if not isinstance(weighting, dict) or set(weighting) != {
            "staleness_function",
            "staleness_lambda",
            "token_weight",
        }:
            raise ValueError("invalid weighting configuration")
        if weighting["token_weight"] is not True:
            raise ValueError("token weighting must be enabled")
        weighting_config = ReferenceWeightingConfig(
            staleness_function=weighting["staleness_function"],
            staleness_lambda=float.fromhex(weighting["staleness_lambda"]),
        )
        if weighting_config.identity() != weighting:
            raise ValueError("weighting configuration is not canonical")
        if not isinstance(protocol, dict) or set(protocol) != {
            "max_global_staleness",
            "max_fragment_staleness",
        }:
            raise ValueError("invalid protocol configuration")
        return cls(
            run_id=payload["run_id"],
            run_generation=payload["run_generation"],
            model_revision=payload["model_revision"],
            parameter_index_digest=payload["parameter_index_digest"],
            fragment_layout_digest=payload["fragment_layout_digest"],
            outer_optimizer_schema_digest=payload["outer_optimizer_schema_digest"],
            optimizer_config=optimizer_config,
            weighting_config=weighting_config,
            max_global_staleness=protocol["max_global_staleness"],
            max_fragment_staleness=protocol["max_fragment_staleness"],
        )


@dataclass(frozen=True)
class RunManifest:
    spec: RunSpec
    genesis_commit_id: str
    genesis_frontier_ref: ObjectRef

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_type": "run",
            "protocol_version": 2,
            "spec": self.spec.to_dict(),
            "spec_digest": self.spec.digest,
            "genesis_commit_id": self.genesis_commit_id,
            "genesis_frontier_ref": self.genesis_frontier_ref.to_dict(),
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())

    @classmethod
    def from_bytes(cls, data: bytes) -> "RunManifest":
        try:
            payload = canonical_object(data)
            if set(payload) != {
                "manifest_type",
                "protocol_version",
                "spec",
                "spec_digest",
                "genesis_commit_id",
                "genesis_frontier_ref",
            }:
                raise ValueError("invalid run-manifest fields")
            if payload["manifest_type"] != "run" or payload["protocol_version"] != 2:
                raise ValueError("invalid run-manifest type or protocol")
            spec = RunSpec.from_dict(payload["spec"])
            if payload["spec_digest"] != spec.digest:
                raise ValueError("run specification digest mismatch")
            commit_id = payload["genesis_commit_id"]
            if not isinstance(commit_id, str) or not commit_id.startswith("genesis-"):
                raise ValueError("invalid genesis commit identity")
            return cls(
                spec=spec,
                genesis_commit_id=commit_id,
                genesis_frontier_ref=ObjectRef.from_dict(payload["genesis_frontier_ref"]),
            )
        except VerificationError:
            raise
        except Exception as exc:
            raise VerificationError(f"invalid run manifest: {exc}") from exc
