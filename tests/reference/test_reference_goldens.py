from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
GOLDEN = Path(__file__).parent / "golden/reference_digests.json"
GENERATOR = ROOT / "scripts/agent/generate_reference_goldens.py"


def test_optimizer_tensors_and_reference_traces_match_cross_process_goldens():
    result = subprocess.run(
        [sys.executable, str(GENERATOR)],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    observed = json.loads(result.stdout)
    reduced = {
        "optimizer_digests": {
            key: value["digest"] for key, value in observed["optimizers"].items()
        },
        "suite_100": observed["suite_100"],
        "trace": observed["trace"],
    }
    assert reduced == json.loads(GOLDEN.read_text())
