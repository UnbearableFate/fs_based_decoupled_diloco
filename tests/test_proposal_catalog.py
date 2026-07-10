from __future__ import annotations

import hashlib
import json
import time

import torch
from safetensors.torch import save_file

from fs_diloco.atomic_io import atomic_write_json
from fs_diloco.log import ProductionTransactionalLog, RunSpec
from fs_diloco.log.production_codec import (
    PRODUCTION_CODEC,
    encode_production_outer_state,
    encode_production_params,
)
from fs_diloco.outer_optim import init_outer_state
from fs_diloco.proposal_catalog import ProposalCatalog
from fs_diloco.runtime_view import build_runtime_view
from fs_diloco.storage import InMemoryStorageBackend


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _log():
    params = torch.tensor([0.0, 0.0])
    spec = RunSpec(
        run_id="catalog-run",
        run_generation=0,
        model_revision="catalog-model",
        parameter_index_digest=_digest("params"),
        fragment_layout_digest=_digest("layout"),
        outer_optimizer_schema_digest=_digest("outer"),
        payload_codec=PRODUCTION_CODEC,
    )
    return ProductionTransactionalLog.initialize(
        InMemoryStorageBackend(),
        spec,
        {
            0: (
                encode_production_params(params),
                encode_production_outer_state(init_outer_state(params, spec.optimizer_config)),
            )
        },
    )


def _candidate(root, view, *, suffix, sequence, values):
    directory = root / "updates" / "pending" / "learner_000"
    directory.mkdir(parents=True, exist_ok=True)
    tensor = directory / f"update_{suffix}.params.safetensors"
    marker = directory / f"update_{suffix}.meta.json"
    save_file({"local_params": torch.tensor(values, dtype=torch.float32)}, str(tensor))
    atomic_write_json(
        marker,
        {
            "format_version": 1,
            "run_id": view.run_id,
            "run_generation": view.run_generation,
            "update_id": f"observed-{suffix}",
            "learner_id": "learner_000",
            "learner_session_id": "session-0",
            "proposal_sequence": sequence,
            "base_global_version": view.commit_seq,
            "base_commit_id": view.commit_id,
            "base_commit_seq": view.commit_seq,
            "base_frontier_digest": view.frontier_sha256,
            "local_step_start": sequence - 1,
            "local_step_end": sequence,
            "inner_steps": 1,
            "tokens_this_update": 10,
            "file_path": str(tensor),
            "file_size_bytes": tensor.stat().st_size,
            "sha256": hashlib.sha256(tensor.read_bytes()).hexdigest(),
            "created_at": str(time.time()),
            "committed_at": time.time(),
        },
    )
    return marker


def test_listing_omission_duplicate_reorder_and_catalog_restart_do_not_change_view(tmp_path):
    log = _log()
    view = build_runtime_view(log)
    older = _candidate(tmp_path, view, suffix="older", sequence=1, values=[1.0, 2.0])
    newer = _candidate(tmp_path, view, suffix="newer", sequence=2, values=[2.0, 3.0])
    catalog = ProposalCatalog(namespace_root=tmp_path, quarantine_root=tmp_path / "quarantine")
    assert catalog.scan(metadata_paths=[], log=log, view=view) == ()
    observed = catalog.scan(
        metadata_paths=[newer, older, newer],
        log=log,
        view=view,
    )
    assert len(observed) == 2
    selected = catalog.select(observed, fragment_id=0, quorum_max=1)
    assert selected[0].manifest.sequence == 1
    restarted = ProposalCatalog(namespace_root=tmp_path, quarantine_root=tmp_path / "quarantine")
    again = restarted.scan(metadata_paths=[older, newer], log=log, view=build_runtime_view(log))
    assert [item.proposal_id for item in again] == [item.proposal_id for item in observed]
    assert build_runtime_view(log).view_digest == view.view_digest


def test_future_candidate_is_quarantined_without_affecting_authority(tmp_path):
    log = _log()
    view = build_runtime_view(log)
    marker = _candidate(tmp_path, view, suffix="future", sequence=1, values=[1.0, 2.0])
    payload = json.loads(marker.read_text())
    payload["base_commit_seq"] = 99
    atomic_write_json(marker, payload)
    catalog = ProposalCatalog(namespace_root=tmp_path, quarantine_root=tmp_path / "quarantine")
    assert catalog.scan(metadata_paths=[marker], log=log, view=view) == ()
    assert list((tmp_path / "quarantine").glob("q-*.json"))
    assert build_runtime_view(log).view_digest == view.view_digest
