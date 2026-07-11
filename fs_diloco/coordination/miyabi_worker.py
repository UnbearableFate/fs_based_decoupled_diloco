"""Two-node P05 lease, fencing, and takeover contract worker."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import torch
from safetensors.torch import save as save_safetensors_bytes

from fs_diloco.log.errors import CommitConflict
from fs_diloco.log.production import ProductionTransactionalLog
from fs_diloco.log.production_codec import (
    PRODUCTION_CODEC,
    encode_production_outer_state,
    encode_production_params,
    production_optimizer_digest,
)
from fs_diloco.log.run import RunSpec
from fs_diloco.outer_optim import init_outer_state
from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.protocol.schemas import ProposalManifest
from fs_diloco.runtime_view import build_runtime_view
from fs_diloco.storage import NotFound, PosixStorageBackend

from .lease import LeaseManager, LeaseMutation


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _rank_and_world() -> tuple[int, int]:
    rank = int(os.environ.get("OMPI_COMM_WORLD_RANK", os.environ.get("PMI_RANK", "-1")))
    world = int(os.environ.get("OMPI_COMM_WORLD_SIZE", os.environ.get("PMI_SIZE", "-1")))
    if rank not in {0, 1} or world != 2:
        raise RuntimeError(f"P05 worker requires rank 0/1 of 2, got {rank}/{world}")
    return rank, world


def _wait(backend: PosixStorageBackend, key: str, timeout: float = 120.0) -> bytes:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return backend.get(key)
        except NotFound:
            time.sleep(0.02)
    raise TimeoutError(f"timed out waiting for {key}")


def _spec(run_id: str) -> RunSpec:
    return RunSpec(
        run_id=run_id,
        run_generation=0,
        model_revision="p05-miyabi-failover",
        parameter_index_digest=_digest("p05-parameters"),
        fragment_layout_digest=_digest("p05-layout"),
        outer_optimizer_schema_digest=_digest("p05-outer"),
        payload_codec=PRODUCTION_CODEC,
        coordination_protocol="head-fenced-v1",
    )


def _initialize(backend: PosixStorageBackend, run_id: str) -> ProductionTransactionalLog:
    spec = _spec(run_id)
    params = torch.tensor([0.0, 0.0], dtype=torch.float32)
    return ProductionTransactionalLog.initialize(
        backend,
        spec,
        {
            0: (
                encode_production_params(params),
                encode_production_outer_state(init_outer_state(params, spec.optimizer_config)),
            )
        },
    )


def _proposal(
    log: ProductionTransactionalLog,
    *,
    learner: str,
    sequence: int,
    values: tuple[float, float],
) -> ProposalManifest:
    view = build_runtime_view(log, force_full=True)
    payload = save_safetensors_bytes(
        {"local_params": torch.tensor(values, dtype=torch.float32)}
    )
    payload_digest = hashlib.sha256(payload).hexdigest()
    manifest = ProposalManifest.with_computed_id(
        {
            "manifest_type": "proposal",
            "protocol_version": 2,
            "run_id": view.run_id,
            "run_generation": view.run_generation,
            "model_revision": log.spec.model_revision,
            "learner_id": learner,
            "learner_session_id": f"session-{learner}",
            "sequence": sequence,
            "fragment_id": 0,
            "base_commit_id": view.commit_id,
            "base_commit_seq": view.commit_seq,
            "base_fragment_version": view.fragments[0].version,
            "base_frontier_digest": view.frontier_sha256,
            "local_steps_since_base": 1,
            "target_tokens_since_base": 100 + sequence,
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
    log.publish_proposal(manifest, payload)
    return manifest


def _prepare(
    log: ProductionTransactionalLog,
    proposal: ProposalManifest,
    *,
    request_id: str,
    values: tuple[float, float],
):
    params = torch.tensor(values, dtype=torch.float32)
    return log.prepare_transition(
        fragment_id=0,
        selected_proposal_ids=[proposal.proposal_id],
        new_params=encode_production_params(params),
        new_outer_state=encode_production_outer_state(
            init_outer_state(params, log.spec.optimizer_config)
        ),
        aggregate_digest=canonical_digest({"proposal": proposal.proposal_id}),
        outer_optimizer_impl_digest=production_optimizer_digest(
            log.spec.optimizer_config.identity()
        ),
        request_id=request_id,
    )


def run_two_node(*, root: Path, run_id: str, output_dir: Path) -> dict[str, object]:
    rank, world = _rank_and_world()
    backend = PosixStorageBackend(root)
    barrier = f"coordination/{run_id}/p05-worker"
    ttl_ns = 2_000_000_000
    max_clock_skew_ns = 100_000_000
    if rank == 0:
        _initialize(backend, run_id)
        backend.put_immutable(f"{barrier}/initialized", b"ready")
    _wait(backend, f"{barrier}/initialized")

    log = ProductionTransactionalLog.open(backend, run_id, 0)
    lease_manager = LeaseManager(
        backend, log.layout, max_clock_skew_ns=max_clock_skew_ns
    )
    stale_commit_rejected = False
    stale_stop_rejected = False
    takeover_wait_seconds = 0.0
    strict_replay_seconds = 0.0

    if rank == 0:
        requested = time.time_ns()
        lease = lease_manager.acquire(
            LeaseMutation(
                operation="acquire",
                request_id="lease-owner-a",
                owner_id="syncer-a",
                owner_session_id="session-a",
                observed_fencing_epoch=0,
                requested_at_utc_ns=requested,
                ttl_ns=ttl_ns,
            )
        )
        log.activate_owner(token=lease.record.owner_token, request_id="fence-owner-a")
        proposal = _proposal(
            log, learner="learner-before-takeover", sequence=1, values=(1.0, 1.0)
        )
        stale_prepared = _prepare(
            log,
            proposal,
            request_id="optimizer-stale-owner-a",
            values=(0.5, 0.5),
        )
        backend.put_immutable(f"{barrier}/owner-a-prepared", b"ready")
        _wait(backend, f"{barrier}/owner-b-fenced")
        try:
            log.commit_prepared(stale_prepared)
        except CommitConflict:
            stale_commit_rejected = True
        else:
            raise AssertionError("stale owner committed a prepared optimizer transition")
        try:
            log.commit_stop(reason="stale-owner-stop", request_id="stale-stop-a")
        except CommitConflict:
            stale_stop_rejected = True
        else:
            raise AssertionError("stale owner committed stop after takeover")
        backend.put_immutable(f"{barrier}/owner-a-rejected", b"ready")
    else:
        _wait(backend, f"{barrier}/owner-a-prepared")
        observed = lease_manager.load()
        wait_started = time.monotonic()
        eligible_at = observed.record.expires_at_utc_ns + max_clock_skew_ns
        while time.time_ns() < eligible_at:
            time.sleep(0.01)
        takeover_wait_seconds = time.monotonic() - wait_started
        replay_started = time.monotonic()
        before = build_runtime_view(log, force_full=True)
        strict_replay_seconds = time.monotonic() - replay_started
        if before.fencing_epoch != 1 or before.optimizer_transition_count != 0:
            raise AssertionError("standby strict replay observed an unexpected authority state")
        lease = lease_manager.acquire(
            LeaseMutation(
                operation="acquire",
                request_id="lease-owner-b",
                owner_id="syncer-b",
                owner_session_id="session-b",
                observed_fencing_epoch=before.fencing_epoch,
                requested_at_utc_ns=time.time_ns(),
                ttl_ns=ttl_ns,
            )
        )
        log.activate_owner(token=lease.record.owner_token, request_id="fence-owner-b")
        backend.put_immutable(f"{barrier}/owner-b-fenced", b"ready")
        _wait(backend, f"{barrier}/owner-a-rejected")
        proposal = _proposal(
            log, learner="learner-after-takeover", sequence=1, values=(2.0, 2.0)
        )
        result = log.commit_prepared(
            _prepare(
                log,
                proposal,
                request_id="optimizer-owner-b",
                values=(1.5, 1.5),
            )
        )
        if result.status != "committed":
            raise AssertionError("new owner optimizer transition did not commit")
        log.commit_stop(reason="p05-two-node-complete", request_id="stop-owner-b")
        backend.put_immutable(f"{barrier}/stopped", b"ready")

    _wait(backend, f"{barrier}/stopped")
    reopened = ProductionTransactionalLog.open(backend, run_id, 0)
    final = build_runtime_view(reopened, force_full=True)
    if final.fencing_epoch != 2 or final.owner_id != "syncer-b":
        raise AssertionError("final authority is not fenced to owner B epoch 2")
    if final.optimizer_transition_count != 1 or len(final.consumed_proposal_ids) != 1:
        raise AssertionError("takeover did not commit exactly one optimizer transition")
    if final.authoritative_stop is None:
        raise AssertionError("authoritative stop did not replay")
    if final.authoritative_stop.reason != "p05-two-node-complete":
        raise AssertionError("authoritative stop reason differs")

    report = {
        "status": "PASS",
        "rank": rank,
        "world_size": world,
        "hostname": os.uname().nodename,
        "fencing_epoch": final.fencing_epoch,
        "owner_id": final.owner_id,
        "owner_session_id": final.owner_session_id,
        "commit_seq": final.commit_seq,
        "optimizer_transition_count": final.optimizer_transition_count,
        "consumed_proposal_count": len(final.consumed_proposal_ids),
        "authoritative_stop_reason": final.authoritative_stop.reason,
        "committed_state_digest": final.committed_state_digest,
        "view_digest": final.view_digest,
        "stale_commit_rejected": stale_commit_rejected if rank == 0 else True,
        "stale_stop_rejected": stale_stop_rejected if rank == 0 else True,
        "takeover_started_with_strict_replay": True,
        "strict_replay_seconds": strict_replay_seconds,
        "takeover_wait_seconds": takeover_wait_seconds,
        "ttl_seconds": ttl_ns / 1_000_000_000,
        "max_clock_skew_seconds": max_clock_skew_ns / 1_000_000_000,
        "split_brain_commits": 0,
        "double_inclusions": 0,
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
    run_two_node(root=args.root, run_id=args.run_id, output_dir=args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
