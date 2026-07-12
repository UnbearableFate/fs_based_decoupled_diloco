"""Capture and restore complete learner-private state from exact capsules."""

from __future__ import annotations

from dataclasses import dataclass
import io
import random
from typing import Any, Mapping

import torch

from fs_diloco.log.codec import canonical_object
from fs_diloco.protocol.canonical_json import canonical_bytes

from .capsule import LearnerCapsuleV1


def _torch_bytes(value: object) -> bytes:
    buffer = io.BytesIO()
    torch.save(value, buffer)
    return buffer.getvalue()


def _torch_load(data: bytes, *, map_location: Any = "cpu") -> object:
    return torch.load(io.BytesIO(data), map_location=map_location, weights_only=False)


def capture_exact_components(
    *,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    scheduler: Any,
    scaler: Any,
    data_source: Any,
    interval_state: Mapping[str, Any],
    frontier_state: Mapping[str, Any],
) -> dict[str, tuple[bytes, str]]:
    if not hasattr(data_source, "state_dict") or not hasattr(data_source, "load_state_dict"):
        raise ValueError("exact capsule requires a restorable data source")
    rng_state = {
        "cpu": torch.get_rng_state(),
        "cuda": (
            tuple(torch.cuda.get_rng_state_all()) if torch.cuda.is_available() else ()
        ),
        "python": random.getstate(),
    }
    scheduler_state = {
        "present": scheduler is not None,
        "state": scheduler.state_dict() if scheduler is not None else {},
    }
    scaler_state = {
        "present": scaler is not None,
        "state": scaler.state_dict() if scaler is not None else {},
    }
    return {
        "model": (_torch_bytes(model.state_dict()), "pt"),
        "inner_optimizer": (_torch_bytes(optimizer.state_dict()), "pt"),
        "scheduler": (_torch_bytes(scheduler_state), "pt"),
        "scaler": (_torch_bytes(scaler_state), "pt"),
        "rng": (_torch_bytes(rng_state), "pt"),
        "data_source": (canonical_bytes(data_source.state_dict()), "json"),
        "interval": (canonical_bytes(dict(interval_state)), "json"),
        "frontier": (canonical_bytes(dict(frontier_state)), "json"),
    }


@dataclass(frozen=True)
class ExactRecoveryReport:
    capsule_id: str
    old_session_id: str
    new_session_id: str
    next_sequence: int
    consistency_point: str
    discarded_pending_proposal_ids: tuple[str, ...]
    exact: bool = True
    warm: bool = False


def restore_exact_components(
    backend,
    capsule: LearnerCapsuleV1,
    *,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    scheduler: Any,
    scaler: Any,
    data_source: Any,
    new_session_id: str,
    expected_frontier_commit_id: str,
    map_location: Any = "cpu",
) -> ExactRecoveryReport:
    if not isinstance(new_session_id, str) or not new_session_id:
        raise ValueError("exact recovery requires a new non-empty session ID")
    if new_session_id == capsule.learner_session_id:
        raise ValueError("exact recovery must open a new learner session")
    if expected_frontier_commit_id != capsule.frontier_commit_id:
        raise ValueError("capsule frontier advanced; exact recovery fails closed")
    refs = capsule.component_map
    if set(refs) != {
        "model",
        "inner_optimizer",
        "scheduler",
        "scaler",
        "rng",
        "data_source",
        "interval",
        "frontier",
    }:
        raise ValueError("capsule lacks exact recovery state")

    def read(kind: str) -> bytes:
        ref = refs[kind]
        data = backend.get(ref.key)
        import hashlib

        if len(data) != ref.size or hashlib.sha256(data).hexdigest() != ref.sha256:
            raise ValueError(f"capsule {kind} component differs")
        return data

    frontier = canonical_object(read("frontier"))
    if frontier.get("commit_id") != capsule.frontier_commit_id or (
        frontier.get("commit_seq") != capsule.frontier_commit_seq
    ):
        raise ValueError("capsule frontier component differs from manifest")
    interval = canonical_object(read("interval"))
    if capsule.consistency_point == "interval_boundary" and (
        capsule.pending_proposal_ids or interval.get("open", False)
    ):
        raise ValueError("boundary capsule carries an open or pending interval")

    model.load_state_dict(_torch_load(read("model"), map_location=map_location), strict=True)
    optimizer.load_state_dict(
        _torch_load(read("inner_optimizer"), map_location=map_location)
    )
    scheduler_payload = _torch_load(read("scheduler"), map_location=map_location)
    if scheduler_payload["present"] != (scheduler is not None):
        raise ValueError("capsule scheduler presence differs")
    if scheduler is not None:
        scheduler.load_state_dict(scheduler_payload["state"])
    scaler_payload = _torch_load(read("scaler"), map_location=map_location)
    if scaler_payload["present"] != (scaler is not None):
        raise ValueError("capsule scaler presence differs")
    if scaler is not None:
        scaler.load_state_dict(scaler_payload["state"])
    if not hasattr(data_source, "load_state_dict"):
        raise ValueError("restore target data source is not restorable")
    data_source.load_state_dict(canonical_object(read("data_source")))
    rng_state = _torch_load(read("rng"), map_location="cpu")
    torch.set_rng_state(rng_state["cpu"])
    random.setstate(rng_state["python"])
    cuda_states = rng_state["cuda"]
    if cuda_states:
        if not torch.cuda.is_available() or len(cuda_states) != torch.cuda.device_count():
            raise ValueError("capsule CUDA RNG topology differs")
        torch.cuda.set_rng_state_all(list(cuda_states))
    return ExactRecoveryReport(
        capsule_id=capsule.capsule_id,
        old_session_id=capsule.learner_session_id,
        new_session_id=new_session_id,
        next_sequence=capsule.sequence + 1,
        consistency_point=capsule.consistency_point,
        discarded_pending_proposal_ids=capsule.pending_proposal_ids,
    )
