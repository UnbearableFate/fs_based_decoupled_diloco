#!/usr/bin/env python3
"""Run the unmodified P06 CRS numeric path from a detached archive checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ARCHIVE_COMMIT = "06e3ca2299d5eb1a720c1d8f9107af5223095525"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    args = _parse_args()
    archive_root = args.archive_root.resolve()
    actual_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=archive_root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    if actual_commit != ARCHIVE_COMMIT:
        raise RuntimeError(f"archive checkout is {actual_commit}, expected {ARCHIVE_COMMIT}")

    current_root = Path(__file__).resolve().parents[2]
    os.environ["PYTHONPATH"] = str(archive_root)
    sys.path[:] = [
        entry
        for entry in sys.path
        if entry and Path(entry).resolve() != current_root
    ]
    sys.path.insert(0, str(archive_root))

    import torch

    from fs_diloco.log.production_codec import (
        encode_production_outer_state,
        encode_production_params,
    )
    from fs_diloco.outer_optim import OuterOptimizerConfig, outer_optimizer_step
    from fs_diloco.testing.deterministic_reference import (
        ReferenceWeightingConfig,
        normalized_weights,
    )

    module_path = Path(sys.modules["fs_diloco.outer_optim"].__file__).resolve()
    module_path.relative_to(archive_root)
    torch.manual_seed(0)
    current = torch.tensor([1.0, -2.0, 0.5, 3.0], dtype=torch.float32)
    proposals = {
        "proposal-a": torch.tensor([0.8, -1.7, 0.1, 2.5], dtype=torch.float32),
        "proposal-b": torch.tensor([1.3, -2.2, 0.9, 3.4], dtype=torch.float32),
    }
    tokens = {"proposal-a": 10, "proposal-b": 30}
    config = OuterOptimizerConfig(name="nesterov", lr=0.2, momentum=0.7)
    state = {"step": torch.tensor(2, dtype=torch.int64), "momentum": torch.zeros_like(current)}
    weights = normalized_weights(tokens, config=ReferenceWeightingConfig())
    selected_ids = tuple(sorted(proposals))
    aggregate = proposals[selected_ids[0]].mul(weights[selected_ids[0]])
    for proposal_id in selected_ids[1:]:
        aggregate = aggregate.add(proposals[proposal_id], alpha=weights[proposal_id])
    new_params, new_state = outer_optimizer_step(current, current - aggregate, state, config)
    aggregate_bytes = encode_production_params(aggregate)
    params_bytes = encode_production_params(new_params)
    state_bytes = encode_production_outer_state(new_state)
    trace = {
        "archive_commit": actual_commit,
        "module_path": str(module_path.relative_to(archive_root)),
        "selected_proposal_ids": list(selected_ids),
        "weights_hex": [weights[proposal_id].hex() for proposal_id in selected_ids],
        "aggregate_content_sha256": _sha256(aggregate_bytes),
        "params_content_sha256": _sha256(params_bytes),
        "outer_state_content_sha256": _sha256(state_bytes),
        "environment": {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "device": "cpu",
            "dtype": "float32",
            "threads": torch.get_num_threads(),
            "reduction_order": "proposal_id-ascending-left-fold-v1",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
