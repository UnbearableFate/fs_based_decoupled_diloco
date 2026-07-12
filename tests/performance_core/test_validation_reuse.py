from __future__ import annotations

from dataclasses import replace
import json

from fs_diloco.atomic_io import atomic_write_json
from fs_diloco.proposal_catalog import ProposalCatalog
from fs_diloco.runtime_view import build_runtime_view
from tests.test_proposal_catalog import _candidate, _log


def test_catalog_reuses_head_scoped_validation_without_retaining_payload_bytes(tmp_path):
    log = _log()
    view = build_runtime_view(log)
    marker = _candidate(tmp_path, view, suffix="reuse", sequence=1, values=[1.0, 2.0])
    catalog = ProposalCatalog(
        namespace_root=tmp_path,
        quarantine_root=tmp_path / "quarantine",
    )
    first = catalog.scan(metadata_paths=[marker], log=log, view=view)
    assert len(first) == 1
    assert first[0].payload.data is None
    assert catalog.last_scan_counters["payload_reads"] == 1
    assert catalog.last_scan_counters["sha_checks"] == 1
    assert catalog.last_scan_counters["finite_checks"] == 1
    assert catalog.last_scan_counters["validation_token_hits"] == 0

    second = catalog.scan(metadata_paths=[marker, marker], log=log, view=view)
    assert [item.proposal_id for item in second] == [first[0].proposal_id]
    assert catalog.last_scan_counters["payload_reads"] == 0
    assert catalog.last_scan_counters["sha_checks"] == 0
    assert catalog.last_scan_counters["finite_checks"] == 0
    assert catalog.last_scan_counters["validation_token_hits"] == 1

    catalog.clear_validation_tokens()
    third = catalog.scan(metadata_paths=[marker], log=log, view=view)
    assert [item.proposal_id for item in third] == [first[0].proposal_id]
    assert catalog.last_scan_counters["payload_reads"] == 1


def test_cheap_future_rejection_precedes_payload_io(tmp_path):
    log = _log()
    view = build_runtime_view(log)
    marker = _candidate(tmp_path, view, suffix="future", sequence=1, values=[1.0, 2.0])
    metadata = json.loads(marker.read_text(encoding="utf-8"))
    metadata["base_commit_seq"] = view.commit_seq + 100
    atomic_write_json(marker, metadata)
    catalog = ProposalCatalog(
        namespace_root=tmp_path,
        quarantine_root=tmp_path / "quarantine",
    )
    assert catalog.scan(metadata_paths=[marker], log=log, view=view) == ()
    assert catalog.last_scan_counters["cheap_rejections"] == 1
    assert catalog.last_scan_counters["payload_reads"] == 0
    assert catalog.last_scan_counters["finite_checks"] == 0


def test_authority_payload_ref_needs_no_mailbox_tensor_or_republication(tmp_path):
    log = _log()
    view = build_runtime_view(log)
    marker = _candidate(tmp_path, view, suffix="authority", sequence=1, values=[3.0, 4.0])
    bootstrap_catalog = ProposalCatalog(
        namespace_root=tmp_path,
        quarantine_root=tmp_path / "quarantine-bootstrap",
    )
    legacy_entry = bootstrap_catalog.scan(metadata_paths=[marker], log=log, view=view)[0]
    metadata = json.loads(marker.read_text(encoding="utf-8"))
    versioned_ref = replace(
        legacy_entry.payload_ref,
        version=log.backend.head(legacy_entry.payload_ref.key).version,
    )
    metadata["payload_ref"] = versioned_ref.to_dict()
    tensor_path = legacy_entry.payload_path
    assert tensor_path is not None
    tensor_path.unlink()
    atomic_write_json(marker, metadata)

    catalog = ProposalCatalog(
        namespace_root=tmp_path,
        quarantine_root=tmp_path / "quarantine-active",
    )
    active = catalog.scan(metadata_paths=[marker], log=log, view=view)[0]
    assert active.payload_path is None
    assert active.payload_ref == versioned_ref
    assert catalog.load_payload(active, backend=log.backend)
    payload_puts_before = len(
        [
            item
            for item in log.backend.history
            if item.operation == "put_immutable" and item.key == active.payload_ref.key
        ]
    )
    catalog.publish_entry(log, active)
    payload_puts_after = len(
        [
            item
            for item in log.backend.history
            if item.operation == "put_immutable" and item.key == active.payload_ref.key
        ]
    )
    assert payload_puts_after == payload_puts_before
