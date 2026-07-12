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
    production_optimizer_digest,
)
from fs_diloco.outer_optim import init_outer_state
from fs_diloco.proposal_catalog import ProposalCatalog
from fs_diloco.runtime_view import build_runtime_view
from fs_diloco.protocol.canonical_json import canonical_digest
from fs_diloco.storage import InMemoryStorageBackend


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _log(*, max_global_staleness=64):
    params = torch.tensor([0.0, 0.0])
    spec = RunSpec(
        run_id="catalog-run",
        run_generation=0,
        model_revision="catalog-model",
        parameter_index_digest=_digest("params"),
        fragment_layout_digest=_digest("layout"),
        outer_optimizer_schema_digest=_digest("outer"),
        payload_codec=PRODUCTION_CODEC,
        max_global_staleness=max_global_staleness,
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


def _candidate(
    root,
    view,
    *,
    suffix,
    sequence,
    values,
    learner="learner_000",
    tensor_dtype=torch.float32,
):
    directory = root / "updates" / "pending" / learner
    directory.mkdir(parents=True, exist_ok=True)
    tensor = directory / f"update_{suffix}.params.safetensors"
    marker = directory / f"update_{suffix}.meta.json"
    save_file({"local_params": torch.tensor(values, dtype=tensor_dtype)}, str(tensor))
    atomic_write_json(
        marker,
        {
            "format_version": 1,
            "run_id": view.run_id,
            "run_generation": view.run_generation,
            "update_id": f"observed-{suffix}",
            "learner_id": learner,
            "learner_session_id": f"session-{learner}",
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


def test_unsupported_payload_dtype_has_typed_quarantine_reason(tmp_path):
    log = _log()
    view = build_runtime_view(log)
    marker = _candidate(
        tmp_path,
        view,
        suffix="i64",
        sequence=1,
        values=[1, 2],
        tensor_dtype=torch.int64,
    )
    catalog = ProposalCatalog(
        namespace_root=tmp_path,
        quarantine_root=tmp_path / "quarantine",
    )
    assert catalog.scan(metadata_paths=[marker], log=log, view=view) == ()
    records = list((tmp_path / "quarantine").glob("q-*.json"))
    assert len(records) == 1
    assert json.loads(records[0].read_text(encoding="utf-8"))["error_code"] == "PAYLOAD_DTYPE"


def test_malformed_future_and_stale_flood_cannot_hide_current_valid_candidate(tmp_path):
    log = _log(max_global_staleness=0)
    initial = build_runtime_view(log)
    catalog = ProposalCatalog(
        namespace_root=tmp_path,
        quarantine_root=tmp_path / "quarantine",
    )

    advance = _candidate(
        tmp_path,
        initial,
        suffix="advance",
        sequence=1,
        values=[1.0, 2.0],
        learner="learner_advance",
    )
    entry = catalog.scan(metadata_paths=[advance], log=log, view=initial)[0]
    catalog.publish_entry(log, entry)
    params = torch.tensor([0.5, 1.0])
    outer = init_outer_state(params, log.spec.optimizer_config)
    log.commit_transition(
        fragment_id=0,
        selected_proposal_ids=[entry.proposal_id],
        new_params=encode_production_params(params),
        new_outer_state=encode_production_outer_state(outer),
        aggregate_digest=canonical_digest({"proposal": entry.proposal_id}),
        outer_optimizer_impl_digest=production_optimizer_digest(
            log.spec.optimizer_config.identity()
        ),
    )
    current = build_runtime_view(log)

    stale = _candidate(
        tmp_path,
        initial,
        suffix="stale",
        sequence=1,
        values=[2.0, 3.0],
        learner="learner_stale",
    )
    future = _candidate(
        tmp_path,
        current,
        suffix="future-flood",
        sequence=1,
        values=[3.0, 4.0],
        learner="learner_future",
    )
    future_payload = json.loads(future.read_text())
    future_payload["base_commit_seq"] = current.commit_seq + 100
    atomic_write_json(future, future_payload)
    malformed = tmp_path / "updates" / "pending" / "learner_bad" / "broken.meta.json"
    malformed.parent.mkdir(parents=True, exist_ok=True)
    malformed.write_text("{not-json", encoding="utf-8")
    valid = _candidate(
        tmp_path,
        current,
        suffix="valid",
        sequence=1,
        values=[4.0, 5.0],
        learner="learner_valid",
    )

    observed = catalog.scan(
        metadata_paths=[future, malformed, stale, future, valid, malformed, stale],
        log=log,
        view=current,
    )
    assert len(observed) == 1
    assert observed[0].manifest.learner_id == "learner_valid"
    assert catalog.select(observed, fragment_id=0, quorum_max=1) == observed
    assert len(list((tmp_path / "quarantine").glob("q-*.json"))) >= 3
    assert build_runtime_view(log).view_digest == current.view_digest
