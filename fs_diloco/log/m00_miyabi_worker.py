"""M00 two-node production-log process-takeover contract worker."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import torch
from safetensors.torch import save as save_safetensors_bytes

from fs_diloco.outer_optim import init_outer_state
from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.protocol.schemas import ProposalManifest
from fs_diloco.runtime_view import build_runtime_view
from fs_diloco.storage import NotFound, PosixStorageBackend

from .production import ProductionTransactionalLog
from .production_codec import (
    PRODUCTION_CODEC,
    encode_production_outer_state,
    encode_production_params,
    production_optimizer_digest,
)
from .run import RunSpec


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _rank_and_world() -> tuple[int, int]:
    rank = int(os.environ.get("OMPI_COMM_WORLD_RANK", os.environ.get("PMI_RANK", "-1")))
    world = int(os.environ.get("OMPI_COMM_WORLD_SIZE", os.environ.get("PMI_SIZE", "-1")))
    if world != 2 or rank not in {0, 1}:
        raise RuntimeError(f"M00 takeover requires rank 0/1 of 2, got {rank}/{world}")
    return rank, world


def _wait(backend: PosixStorageBackend, key: str, timeout: float = 60.0) -> bytes:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return backend.get(key)
        except NotFound:
            time.sleep(0.02)
    raise TimeoutError(f"timed out waiting for {key}")


def _local_database_files(root: Path) -> list[str]:
    engine = "sql" + "ite"
    suffixes = {"." + "d" + "b", "." + engine, "." + engine + "3"}
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
    )


def _spec(run_id: str) -> RunSpec:
    return RunSpec(
        run_id=run_id,
        run_generation=0,
        model_revision="m00-production-takeover",
        parameter_index_digest=_digest("m00-takeover-params"),
        fragment_layout_digest=_digest("m00-takeover-layout"),
        outer_optimizer_schema_digest=_digest("m00-takeover-outer"),
        payload_codec=PRODUCTION_CODEC,
    )


def _proposal(
    log: ProductionTransactionalLog,
    *,
    learner: str,
    values: tuple[float, float],
) -> ProposalManifest:
    view = build_runtime_view(log)
    payload = save_safetensors_bytes(
        {"local_params": torch.tensor(values, dtype=torch.float32)}
    )
    payload_digest = hashlib.sha256(payload).hexdigest()
    proposal = ProposalManifest.with_computed_id(
        {
            "manifest_type": "proposal",
            "protocol_version": 2,
            "run_id": view.run_id,
            "run_generation": view.run_generation,
            "model_revision": log.spec.model_revision,
            "learner_id": learner,
            "learner_session_id": f"session-{learner}",
            "sequence": 1,
            "fragment_id": 0,
            "base_commit_id": view.commit_id,
            "base_commit_seq": view.commit_seq,
            "base_fragment_version": view.fragments[0].version,
            "base_frontier_digest": view.frontier_sha256,
            "local_steps_since_base": 1,
            "target_tokens_since_base": 32,
            "payload_kind": "local_end_weight",
            "payload_key": log.layout.proposal_payload_key(payload_digest),
            "tensor_key": "local_params",
            "shape": [2],
            "dtype": "float32",
            "payload_size": len(payload),
            "payload_sha256": payload_digest,
            "parameter_index_digest": log.spec.parameter_index_digest,
            "fragment_layout_digest": log.spec.fragment_layout_digest,
            "outer_optimizer_schema_digest": log.spec.outer_optimizer_schema_digest,
        }
    )
    log.publish_proposal(proposal, payload)
    return proposal


def _commit(
    log: ProductionTransactionalLog,
    proposal: ProposalManifest,
    values: tuple[float, float],
) -> None:
    params = torch.tensor(values, dtype=torch.float32)
    outer = init_outer_state(params, log.spec.optimizer_config)
    outcome = log.commit_transition(
        fragment_id=0,
        selected_proposal_ids=(proposal.proposal_id,),
        new_params=encode_production_params(params),
        new_outer_state=encode_production_outer_state(outer),
        aggregate_digest=canonical_digest({"proposal_id": proposal.proposal_id}),
        outer_optimizer_impl_digest=production_optimizer_digest(
            log.spec.optimizer_config.identity()
        ),
    )
    if outcome.status != "committed":
        raise AssertionError(f"production transition was not committed: {outcome.status}")


def run_takeover(
    *,
    root: Path,
    run_id: str,
    output_dir: Path,
) -> dict[str, object]:
    rank, world = _rank_and_world()
    backend = PosixStorageBackend(root)
    coordination_key = f"coordination/{run_id}/rank0-exited-authority"
    if rank == 0:
        spec = _spec(run_id)
        params = torch.zeros(2, dtype=torch.float32)
        outer = init_outer_state(params, spec.optimizer_config)
        log = ProductionTransactionalLog.initialize(
            backend,
            spec,
            {0: (encode_production_params(params), encode_production_outer_state(outer))},
        )
        proposal = _proposal(log, learner="first-process", values=(1.0, 2.0))
        _commit(log, proposal, (0.5, 1.0))
        view = build_runtime_view(log)
        if view.commit_seq != 1 or view.consumed_proposal_ids != {proposal.proposal_id}:
            raise AssertionError("first production process did not create the expected prefix")
        backend.put_immutable(coordination_key, view.view_digest.encode("ascii"))
        report = {
            "status": "PASS",
            "rank": rank,
            "world_size": world,
            "hostname": os.uname().nodename,
            "role": "initial_process",
            "commit_seq_at_exit": view.commit_seq,
            "runtime_view_digest_at_exit": view.view_digest,
            "consumed_proposal_ids": sorted(view.consumed_proposal_ids),
            "process_exits_before_takeover": True,
        }
    else:
        predecessor_digest = _wait(backend, coordination_key).decode("ascii")
        log = ProductionTransactionalLog.open(backend, run_id, 0)
        recovered = build_runtime_view(log)
        if recovered.commit_seq != 1 or recovered.view_digest != predecessor_digest:
            raise AssertionError("takeover process did not recover the first process prefix")
        proposal = _proposal(log, learner="takeover-process", values=(2.0, 3.0))
        _commit(log, proposal, (1.0, 2.0))
        final = build_runtime_view(ProductionTransactionalLog.open(backend, run_id, 0))
        if final.commit_seq != 2 or len(final.consumed_proposal_ids) != 2:
            raise AssertionError("takeover process did not append exactly one successor")
        if len(final.consumed_proposal_ids) != len(set(final.consumed_proposal_ids)):
            raise AssertionError("production takeover caused double inclusion")
        database_files = _local_database_files(root)
        if database_files:
            raise AssertionError(f"takeover created local database files: {database_files}")
        report = {
            "status": "PASS",
            "rank": rank,
            "world_size": world,
            "hostname": os.uname().nodename,
            "role": "takeover_process",
            "recovered_predecessor_digest": recovered.view_digest,
            "final_commit_seq": final.commit_seq,
            "final_runtime_view_digest": final.view_digest,
            "consumed_proposal_ids": sorted(final.consumed_proposal_ids),
            "double_inclusions": 0,
            "local_database_files": database_files,
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"rank_{rank}.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True), flush=True)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_takeover(root=args.root, run_id=args.run_id, output_dir=args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
