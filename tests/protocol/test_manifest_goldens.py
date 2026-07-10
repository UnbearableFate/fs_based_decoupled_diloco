from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
GOLDEN = Path(__file__).parent / "golden/manifest_digests.json"
GENERATOR = ROOT / "scripts/agent/generate_protocol_goldens.py"


def test_all_manifest_canonical_bytes_have_cross_process_golden_digests():
    result = subprocess.run(
        [sys.executable, str(GENERATOR)],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    vectors = json.loads(result.stdout)
    observed = {key: value["sha256"] for key, value in vectors.items()}
    assert observed == json.loads(GOLDEN.read_text())
    for value in vectors.values():
        assert value["canonical"].encode("utf-8")
