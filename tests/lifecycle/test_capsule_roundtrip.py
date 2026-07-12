from __future__ import annotations

import random

import pytest
import torch

from fs_diloco.hf_data import SyntheticBatchSource, WikiTextBatchSource
from fs_diloco.learner_protocol.capsule import (
    LearnerCapsuleV1,
    load_capsule,
    publish_capsule,
)
from fs_diloco.learner_protocol.exact_recovery import (
    capture_exact_components,
    restore_exact_components,
)
from fs_diloco.log.layout import LogLayout
from fs_diloco.storage import InMemoryStorageBackend, NotFound


def _stack(seed: int = 7):
    torch.manual_seed(seed)
    random.seed(seed)
    model = torch.nn.Sequential(
        torch.nn.Linear(4, 8),
        torch.nn.Dropout(p=0.25),
        torch.nn.Linear(8, 2),
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.01)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=1, gamma=0.9)
    source = SyntheticBatchSource(
        vocab_size=16,
        block_size=4,
        micro_batch_size=2,
        seed=91,
        learner_index=0,
    )
    return model, optimizer, scheduler, source


def _step(model, optimizer, scheduler, source):
    batch = next(source).input_ids.float()
    optimizer.zero_grad(set_to_none=True)
    output = model(batch)
    loss = output.square().mean()
    loss.backward()
    optimizer.step()
    scheduler.step()
    return batch.clone(), loss.detach().clone(), random.random()


def _identity():
    return {
        "run_id": "capsule-test",
        "run_generation": 1,
        "learner_id": "learner-0",
        "learner_session_id": "session-old",
        "sequence": 3,
        "consistency_point": "interval_boundary",
        "frontier_commit_seq": 3,
        "frontier_commit_id": "commit-3",
        "pending_proposal_ids": [],
    }


def test_synthetic_capsule_restores_bitwise_tiny_continuation_and_new_session():
    backend = InMemoryStorageBackend()
    layout = LogLayout("capsule-test", 1)
    model, optimizer, scheduler, source = _stack()
    for _ in range(3):
        _step(model, optimizer, scheduler, source)
    components = capture_exact_components(
        model=model,
        optimizer=optimizer,
        scheduler=scheduler,
        scaler=None,
        data_source=source,
        interval_state={"open": False, "local_step": 3},
        frontier_state={"commit_id": "commit-3", "commit_seq": 3},
    )
    history_start = len(backend.history)
    publication = publish_capsule(
        backend, layout, identity=_identity(), components=components
    )
    writes = [
        record.key
        for record in backend.history[history_start:]
        if record.operation == "put_immutable"
    ]
    assert writes[-1] == publication.marker_ref.key
    expected = [_step(model, optimizer, scheduler, source) for _ in range(2)]
    expected_parameters = tuple(
        parameter.detach().clone() for parameter in model.parameters()
    )

    restored_model, restored_optimizer, restored_scheduler, restored_source = _stack(999)
    capsule = load_capsule(backend, publication.marker_ref.key)
    report = restore_exact_components(
        backend,
        capsule,
        model=restored_model,
        optimizer=restored_optimizer,
        scheduler=restored_scheduler,
        scaler=None,
        data_source=restored_source,
        new_session_id="session-new",
        expected_frontier_commit_id="commit-3",
    )
    actual = [
        _step(restored_model, restored_optimizer, restored_scheduler, restored_source)
        for _ in range(2)
    ]

    assert report.exact and not report.warm
    assert report.next_sequence == 4 and report.new_session_id == "session-new"
    for expected_row, actual_row in zip(expected, actual, strict=True):
        assert torch.equal(expected_row[0], actual_row[0])
        assert torch.equal(expected_row[1], actual_row[1])
        assert expected_row[2] == actual_row[2]
    assert all(
        torch.equal(expected_parameter, actual_parameter)
        for expected_parameter, actual_parameter in zip(
            expected_parameters, restored_model.parameters(), strict=True
        )
    )


def test_capsule_missing_component_or_frontier_session_mismatch_fails_closed():
    backend = InMemoryStorageBackend()
    layout = LogLayout("capsule-test", 1)
    model, optimizer, scheduler, source = _stack()
    components = capture_exact_components(
        model=model,
        optimizer=optimizer,
        scheduler=scheduler,
        scaler=None,
        data_source=source,
        interval_state={"open": False},
        frontier_state={"commit_id": "commit-3", "commit_seq": 3},
    )
    incomplete = dict(components)
    incomplete.pop("rng")
    with pytest.raises(ValueError, match="every component"):
        publish_capsule(backend, layout, identity=_identity(), components=incomplete)
    publication = publish_capsule(
        backend, layout, identity=_identity(), components=components
    )
    capsule = publication.capsule
    with pytest.raises(ValueError, match="new learner session"):
        restore_exact_components(
            backend,
            capsule,
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=None,
            data_source=source,
            new_session_id="session-old",
            expected_frontier_commit_id="commit-3",
        )
    with pytest.raises(ValueError, match="frontier advanced"):
        restore_exact_components(
            backend,
            capsule,
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=None,
            data_source=source,
            new_session_id="session-new",
            expected_frontier_commit_id="commit-4",
        )
    missing_ref = capsule.component_map["inner_optimizer"]
    backend.delete_batch([missing_ref])
    with pytest.raises(NotFound):
        load_capsule(backend, publication.marker_ref.key)


def test_wikitext_source_requires_dataset_and_tokenizer_identity_for_restore():
    blocks = [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]]
    source = WikiTextBatchSource(
        blocks,
        2,
        dataset_identity="dataset-a",
        tokenizer_identity="tokenizer-a",
    )
    next(source)
    state = source.state_dict()
    expected = next(source)
    restored = WikiTextBatchSource(
        blocks,
        2,
        dataset_identity="dataset-a",
        tokenizer_identity="tokenizer-a",
    )
    restored.load_state_dict(state)
    actual = next(restored)
    assert torch.equal(expected.input_ids, actual.input_ids)

    mismatched = WikiTextBatchSource(
        blocks,
        2,
        dataset_identity="dataset-b",
        tokenizer_identity="tokenizer-a",
    )
    with pytest.raises(ValueError, match="identity/state differs"):
        mismatched.load_state_dict(state)


def test_capsule_schema_rejects_missing_private_state_without_exact_claim():
    payload = {
        **_identity(),
        "schema": "duraloco-learner-capsule-v1",
        "components": {},
        "capsule_id": "capsule-invalid",
    }
    with pytest.raises(ValueError, match="missing exact-recovery components"):
        LearnerCapsuleV1.from_dict(payload)
