from __future__ import annotations

import pytest

from fs_diloco.protocol.errors import ProtocolError
from fs_diloco.protocol.v1_adapter import parse_v1_manifest, write_v2_authority


def test_v1_adapter_parses_without_granting_v2_authority():
    legacy = parse_v1_manifest(
        {
            "format_version": 1,
            "run_id": "legacy",
            "update_id": "u1",
            "learner_id": "learner_000",
            "base_global_version": 3,
            "local_step_start": 10,
            "local_step_end": 20,
            "tokens_since_global_load": 100,
            "file_path": "/tmp/update.safetensors",
            "file_size_bytes": 42,
            "sha256": None,
        }
    )
    assert legacy.base_global_sequence == 3
    assert legacy.fragment_id == 0
    with pytest.raises(ProtocolError, match="read-only|cannot write"):
        write_v2_authority(legacy)


@pytest.mark.parametrize(
    "bad",
    [
        [],
        {"run_id": "x"},
        {
            "run_id": "x",
            "update_id": "u",
            "learner_id": "l",
            "file_path": "p",
            "file_size_bytes": [],
        },
        {
            "run_id": "x",
            "update_id": "u",
            "learner_id": "l",
            "file_path": "p",
            "file_size_bytes": float("inf"),
        },
    ],
)
def test_v1_adapter_malformed_inputs_are_typed(bad):
    with pytest.raises(ProtocolError):
        parse_v1_manifest(bad)
