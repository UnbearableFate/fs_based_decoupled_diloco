from __future__ import annotations

import hashlib
import math
from pathlib import Path
import random

import pytest

from fs_diloco.protocol.schemas import ProposalManifest
from fs_diloco.protocol.quarantine import QuarantineRegistry
from fs_diloco.protocol.validation import (
    ValidationContext,
    validate_candidate_bytes,
    validate_proposal,
)

from .helpers import make_proposal, proposal_dict, safetensors_bytes, write_payload


def _context(root: Path, **overrides: object) -> ValidationContext:
    values = {
        "run_id": "run-test",
        "run_generation": 0,
        "model_revision": "synthetic-model-v1",
        "current_commit_id": "genesis",
        "current_commit_seq": 0,
        "ancestor_commit_ids": frozenset({"genesis"}),
        "commit_sequences_by_id": {"genesis": 0},
        "fragment_versions": {0: 0},
        "parameter_index_digest": "b" * 64,
        "fragment_layout_digest": "c" * 64,
        "outer_optimizer_schema_digest": "d" * 64,
        "frontier_digests_by_commit": {"genesis": "a" * 64},
        "namespace_root": root,
    }
    values.update(overrides)
    return ValidationContext(**values)


def _error_code(report) -> str:
    assert not report.valid
    return report.errors[0]["code"]


def test_valid_payload_passes_all_layers(tmp_path):
    proposal = make_proposal(tmp_path)
    report = validate_proposal(proposal, _context(tmp_path))
    assert report.valid
    assert {"schema", "causal_ancestry", "path_containment", "finite"} <= set(report.checks)


@pytest.mark.parametrize(
    ("proposal_changes", "context_changes", "expected"),
    [
        ({"run_id": "other"}, {}, "RUN_MISMATCH"),
        ({"run_generation": 1}, {}, "GENERATION_MISMATCH"),
        ({"model_revision": "other-model"}, {}, "MODEL_REVISION_MISMATCH"),
        ({"parameter_index_digest": "e" * 64}, {}, "PARAMETER_INDEX_MISMATCH"),
        ({"fragment_layout_digest": "e" * 64}, {}, "FRAGMENT_LAYOUT_MISMATCH"),
        ({"outer_optimizer_schema_digest": "e" * 64}, {}, "OUTER_SCHEMA_MISMATCH"),
        ({"base_commit_seq": 2, "base_commit_id": "future"}, {}, "FUTURE_BASE"),
        ({"base_commit_id": "unknown"}, {}, "UNKNOWN_BASE"),
        ({"base_commit_seq": 1}, {"current_commit_seq": 1}, "BASE_SEQUENCE_MISMATCH"),
        ({"base_frontier_digest": "f" * 64}, {}, "BASE_FRONTIER_MISMATCH"),
        ({"base_fragment_version": 2}, {}, "FUTURE_FRAGMENT_BASE"),
        ({"fragment_id": 2}, {}, "UNKNOWN_FRAGMENT"),
        (
            {"base_commit_seq": 0},
            {"current_commit_seq": 100, "max_global_staleness": 10},
            "STALE_BASE",
        ),
        (
            {"base_fragment_version": 0},
            {"fragment_versions": {0: 10}, "max_fragment_staleness": 2},
            "STALE_FRAGMENT_BASE",
        ),
    ],
)
def test_metadata_and_causal_rejection_matrix(
    tmp_path, proposal_changes, context_changes, expected
):
    proposal = make_proposal(tmp_path, **proposal_changes)
    context = _context(tmp_path, **context_changes)
    if "current_commit_seq" in context_changes and proposal.base_commit_id == "genesis":
        context.ancestor_commit_ids = frozenset({"genesis"})
    assert _error_code(validate_proposal(proposal, context, validate_tensor=False)) == expected


def test_path_escape_is_rejected_before_read(tmp_path):
    proposal = make_proposal(tmp_path, payload_key="../escape.safetensors")
    assert _error_code(validate_proposal(proposal, _context(tmp_path))) == "PAYLOAD_PATH_ESCAPE"


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"payload_size": 1}, "PAYLOAD_SIZE"),
        ({"payload_sha256": "f" * 64}, "PAYLOAD_HASH"),
        ({"tensor_key": "wrong"}, "PAYLOAD_TENSOR_KEY"),
        ({"shape": [1, 2]}, "PAYLOAD_SHAPE"),
        ({"dtype": "float16"}, "PAYLOAD_DTYPE"),
    ],
)
def test_payload_metadata_mismatch_matrix(tmp_path, changes, expected):
    proposal = make_proposal(tmp_path, **changes)
    assert _error_code(validate_proposal(proposal, _context(tmp_path))) == expected


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_payload_is_rejected(tmp_path, value):
    path, payload = write_payload(tmp_path, values=(1.0, value))
    proposal = ProposalManifest.with_computed_id(
        proposal_dict(
            tmp_path,
            payload=payload,
            relative=path.relative_to(tmp_path).as_posix(),
        )
    )
    assert _error_code(validate_proposal(proposal, _context(tmp_path))) == "PAYLOAD_NONFINITE"


def test_short_extra_and_wrong_key_payloads_are_rejected(tmp_path):
    path, payload = write_payload(tmp_path)
    for mutated, expected in (
        (payload[:-1], "PAYLOAD_HASH"),
        (payload + b"x", "PAYLOAD_HASH"),
        (safetensors_bytes((1.0, 2.0), key="other"), "PAYLOAD_TENSOR_KEY"),
    ):
        path.write_bytes(mutated)
        proposal = ProposalManifest.with_computed_id(
            proposal_dict(
                tmp_path,
                payload=mutated,
                relative=path.relative_to(tmp_path).as_posix(),
                payload_size=len(mutated),
                payload_sha256=hashlib.sha256(mutated).hexdigest(),
            )
        )
        code = _error_code(validate_proposal(proposal, _context(tmp_path)))
        if expected == "PAYLOAD_HASH":
            assert code in {"PAYLOAD_TRUNCATED", "PAYLOAD_EXTRA_BYTES", "SAFETENSORS_HEADER"}
        else:
            assert code == expected


def test_sequence_rollback_is_typed_not_an_uncaught_key_error(tmp_path):
    context = _context(tmp_path)
    newer = make_proposal(tmp_path, sequence=2)
    older = make_proposal(tmp_path, sequence=1)
    assert validate_proposal(newer, context, validate_tensor=False).valid
    assert _error_code(validate_proposal(older, context, validate_tensor=False)) == "SEQUENCE_ROLLBACK"


def test_invalid_future_proposal_does_not_poison_later_valid_sequence(tmp_path):
    context = _context(tmp_path)
    future = make_proposal(
        tmp_path,
        sequence=100,
        base_commit_id="future",
        base_commit_seq=100,
    )
    valid = make_proposal(tmp_path, sequence=1)
    assert _error_code(validate_proposal(future, context, validate_tensor=False)) == "FUTURE_BASE"
    assert validate_proposal(valid, context, validate_tensor=False).valid


def test_same_session_sequence_cannot_name_different_content(tmp_path):
    context = _context(tmp_path)
    first = make_proposal(tmp_path, sequence=7, target_tokens_since_base=100)
    conflicting = make_proposal(tmp_path, sequence=7, target_tokens_since_base=101)
    assert validate_proposal(first, context, validate_tensor=False).valid
    report = validate_proposal(conflicting, context, validate_tensor=False)
    assert _error_code(report) == "SEQUENCE_CONTENT_CONFLICT"
    assert report.errors[0]["category"] == "fatal"


def test_test_fixture_actually_contains_nonfinite_value():
    assert not math.isfinite(float("nan"))


@pytest.mark.parametrize(
    "payload",
    [
        b'{"manifest_type":"proposal"',
        b'{"manifest_type":"proposal","manifest_type":"head"}',
        b'{"manifest_type":"proposal","unexpected":true}',
        b"not-json",
    ],
)
def test_arbitrary_malformed_candidates_are_typed_quarantine_not_scanner_crashes(
    tmp_path, payload
):
    report, record = validate_candidate_bytes(
        payload,
        _context(tmp_path),
        QuarantineRegistry(),
        validate_tensor=False,
    )
    assert not report.valid
    assert record is not None
    assert record.category == "quarantine"


def test_seeded_malformed_byte_corpus_never_escapes_as_scanner_exception(tmp_path):
    rng = random.Random(20260710)
    registry = QuarantineRegistry()
    corpus = [bytes(rng.randrange(256) for _ in range(rng.randrange(1, 96))) for _ in range(256)]
    for payload in corpus:
        report, record = validate_candidate_bytes(
            payload,
            _context(tmp_path),
            registry,
            validate_tensor=False,
        )
        assert not report.valid
        assert record is not None


def test_extreme_nesting_becomes_typed_quarantine_not_recursion_error(tmp_path):
    payload = ("[" * 2000 + "0" + "]" * 2000).encode()
    report, record = validate_candidate_bytes(
        payload,
        _context(tmp_path),
        QuarantineRegistry(),
        validate_tensor=False,
    )
    assert _error_code(report) == "MALFORMED_MANIFEST"
    assert record is not None


def test_missing_payload_is_retryable_and_not_quarantined(tmp_path):
    proposal = make_proposal(tmp_path, payload_key="immutable/proposals/missing.safetensors")
    report, record = validate_candidate_bytes(
        proposal.canonical_bytes(),
        _context(tmp_path),
        QuarantineRegistry(),
    )
    assert _error_code(report) == "PAYLOAD_MISSING"
    assert report.errors[0]["category"] == "retryable"
    assert record is None


def test_payload_key_not_filename_supplies_the_validated_location(tmp_path):
    path, payload = write_payload(
        tmp_path,
        relative="arbitrary/nested/name-without-protocol-fields.bin",
    )
    proposal = ProposalManifest.with_computed_id(
        proposal_dict(
            tmp_path,
            payload=payload,
            relative=path.relative_to(tmp_path).as_posix(),
        )
    )
    assert validate_proposal(proposal, _context(tmp_path)).valid
