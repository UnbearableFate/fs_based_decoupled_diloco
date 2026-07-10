from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from fs_diloco.protocol.canonical_json import (
    CanonicalJSONError,
    canonical_digest,
    canonical_text,
    loads_strict,
)


GOLDEN = Path(__file__).parent / "golden/canonical_vector.json"


def test_golden_bytes_and_digest_are_stable():
    fixture = json.loads(GOLDEN.read_text())
    assert canonical_text(fixture["input"]) == fixture["canonical"]
    assert canonical_digest(fixture["input"]) == fixture["sha256"]


def test_key_order_and_unicode_normalization_do_not_change_identity():
    first = {"z": "e\u0301", "a": [1, True, None]}
    second = {"a": [1, True, None], "z": "é"}
    assert canonical_text(first) == canonical_text(second)
    assert canonical_digest(first) == canonical_digest(second)


@pytest.mark.parametrize("value", [1.0, float("nan"), float("inf"), -float("inf")])
def test_floats_are_forbidden(value):
    with pytest.raises(CanonicalJSONError):
        canonical_text({"value": value})


def test_duplicate_json_keys_and_nonfinite_constants_are_rejected():
    with pytest.raises(CanonicalJSONError, match="duplicate"):
        loads_strict('{"a":1,"a":2}')
    with pytest.raises(CanonicalJSONError, match="non-finite"):
        loads_strict('{"a":NaN}')


def test_unknown_python_types_are_rejected():
    with pytest.raises(CanonicalJSONError, match="unsupported"):
        canonical_text({"bad": object()})


def test_extreme_json_nesting_is_a_typed_canonical_error():
    payload = "[" * 2000 + "0" + "]" * 2000
    with pytest.raises(CanonicalJSONError, match="depth|recursion|maximum"):
        loads_strict(payload)


def test_golden_digest_is_stable_in_a_fresh_process():
    command = [
        sys.executable,
        "-c",
        (
            "from fs_diloco.protocol.canonical_json import canonical_digest; "
            "print(canonical_digest({'z':'e\\u0301','a':[1,True,None]}))"
        ),
    ]
    result = subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE)
    assert result.stdout.strip() == "7268de922179fe369bffb347eb399ffbfaa36f1e7a34502bd6425cb69ca4ac67"
