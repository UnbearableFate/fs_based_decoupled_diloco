#!/usr/bin/env python3
"""Compare the P06A CRS C9 oracle and P06B D8 distributed generation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import torch
from safetensors.torch import load_file

from fs_diloco.log.codec import canonical_object
from fs_diloco.log.production import ProductionTransactionalLog
from fs_diloco.storage import PosixStorageBackend


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _stored_json(root: Path, path: Path):
    """Read a canonical JSON payload through the POSIX backend envelope."""
    return canonical_object(PosixStorageBackend(root).get(path.relative_to(root).as_posix()))


def _commits(root: Path):
    spec = _run_spec(root)
    log = ProductionTransactionalLog.open(
        PosixStorageBackend(root), spec["run_id"], spec["run_generation"]
    )
    return [item.to_dict() for item in log.replay(force_full=True).commits]


def _run_spec(root: Path):
    paths = [path for path in root.rglob("run_spec.json")]
    if len(paths) != 1:
        raise AssertionError(f"expected one run spec under {root}, found {len(paths)}")
    return _stored_json(root, paths[0])


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _losses(root: Path) -> list[float]:
    with (root / "metrics/learner_metrics.csv").open(newline="") as handle:
        return [float(row["train_loss"]) for row in csv.DictReader(handle) if row.get("train_loss")]


def _latest_weight(root: Path) -> Path:
    latest = _json(root / "control/latest.json")
    return Path(latest.get("weight_path") or latest["materialized_weight_path"])


def run(crs: Path, distributed: Path) -> dict[str, object]:
    crs_commits = _commits(crs / "authority")
    d_commits = _commits(distributed / "authority")
    crs_spec = _run_spec(crs / "authority")
    d_spec = _run_spec(distributed / "authority")
    crs_optimizer = [item for item in crs_commits if item["manifest_type"] == "commit"]
    d_optimizer = [item for item in d_commits if item["manifest_type"] == "commit"]
    if len(crs_optimizer) != 10 or len(d_optimizer) != 10:
        raise AssertionError("comparison requires ten optimizer transitions")
    crs_policy = [
        {
            "fragment_id": item["fragment_id"],
            "selected_count": len(item["selected_proposals"]),
            "weights": [row["weight_fp64_hex"] for row in item["selected_proposals"]],
            "outer_optimizer_impl_digest": item["outer_optimizer_impl_digest"],
        }
        for item in crs_optimizer
    ]
    d_policy = [
        {
            "fragment_id": item["fragment_id"],
            "selected_count": len(item["selected_proposals"]),
            "weights": [row["weight_fp64_hex"] for row in item["selected_proposals"]],
            "outer_optimizer_impl_digest": item["outer_optimizer_impl_digest"],
        }
        for item in d_optimizer
    ]
    if crs_policy != d_policy:
        raise AssertionError("CRS/D8 policy and hexadecimal weight identity differs")

    orders = {
        item["work_order_id"]: item
        for path in (distributed / "authority").rglob("*.json")
        if "/distributed/work-orders/" in path.as_posix() and not path.name.endswith(".inputs.json")
        for item in [_stored_json(distributed / "authority", path)]
    }
    results = {
        item["prepared_result_id"]: item
        for path in (distributed / "authority").rglob("*.json")
        if "/distributed/prepared/results/" in path.as_posix()
        for item in [_stored_json(distributed / "authority", path)]
    }
    events = [
        json.loads(line)
        for line in (distributed / "logs/distributed_committer.jsonl").read_text().splitlines()
        if "distributed_transition_committed" in line
    ]
    exact_links = []
    for event, commit in zip(events, d_optimizer, strict=True):
        order = orders[event["work_order_id"]]
        result = results[event["prepared_result_id"]]
        exact = {
            "selected_ids_exact": [p["proposal_id"] for p in order["proposals"]]
            == [p["proposal_id"] for p in commit["selected_proposals"]],
            "weights_exact": [p["weight_hex"] for p in order["proposals"]]
            == [p["weight_fp64_hex"] for p in commit["selected_proposals"]],
            "params_content_exact": result["params_ref"]["sha256"]
            == commit["new_params_ref"]["sha256"],
            "outer_state_content_exact": result["outer_state_ref"]["sha256"]
            == commit["new_outer_state_ref"]["sha256"],
            "aggregate_digest_exact": result["aggregate_digest"] == commit["aggregate_digest"],
        }
        if not all(exact.values()):
            raise AssertionError("FWO/PFT/final transition exact linkage differs")
        exact_links.append(exact)

    crs_weight = _latest_weight(crs)
    d_weight = _latest_weight(distributed)
    crs_tensors = load_file(str(crs_weight), device="cpu")
    d_tensors = load_file(str(d_weight), device="cpu")
    if set(crs_tensors) != set(d_tensors):
        raise AssertionError("CRS/D8 parameter names differ")
    atol, rtol = 0.05, 0.10
    max_abs = 0.0
    squared_error = 0.0
    squared_reference = 0.0
    allclose = True
    for name in sorted(crs_tensors):
        left = crs_tensors[name].float()
        right = d_tensors[name].float()
        delta = left - right
        max_abs = max(max_abs, float(delta.abs().max().item()))
        squared_error += float(delta.double().square().sum().item())
        squared_reference += float(left.double().square().sum().item())
        allclose = allclose and bool(torch.allclose(left, right, atol=atol, rtol=rtol))
    if not allclose:
        raise AssertionError(f"CRS/D8 numeric tolerance failed: max_abs={max_abs}")
    crs_losses, d_losses = _losses(crs), _losses(distributed)
    if not crs_losses or not d_losses or not all(map(math.isfinite, crs_losses + d_losses)):
        raise AssertionError("comparison loss smoke is not finite")
    ranges_overlap = max(min(crs_losses), min(d_losses)) <= min(max(crs_losses), max(d_losses))
    if not ranges_overlap:
        raise AssertionError("CRS/D8 loss smoke ranges do not overlap")
    crs_controls = [
        item["control_kind"]
        for item in crs_commits
        if item["manifest_type"] == "control_commit"
    ]
    d_controls = [
        item["control_kind"]
        for item in d_commits
        if item["manifest_type"] == "control_commit"
    ]
    expected_crs_controls = ["epoch_bump", "epoch_bump", "stop"]
    expected_distributed_controls = ["epoch_bump", "stop"]
    if crs_controls != expected_crs_controls or d_controls != expected_distributed_controls:
        raise AssertionError(
            f"control sequence differs: CRS={crs_controls}, distributed={d_controls}"
        )
    return {
        "schema": "duraloco-p06b-c9-d8-comparison-v1",
        "status": "PASS",
        "policy_identity_exact": True,
        "same_fwo_lfe_to_final_exact": True,
        "exact_transition_links": exact_links,
        "numeric_tolerance": {"atol": atol, "rtol": rtol, "allclose": allclose},
        "max_abs_parameter_difference": max_abs,
        "relative_l2_parameter_difference": math.sqrt(
            squared_error / max(squared_reference, 1e-30)
        ),
        "crs_final_weight_sha256": _sha(crs_weight),
        "distributed_final_weight_sha256": _sha(d_weight),
        "crs_execution_backend_digest": crs_spec["execution_backend_digest"],
        "distributed_execution_backend_digest": d_spec["execution_backend_digest"],
        "content_identity_claimed_across_backends": False,
        "crs_control_sequence": crs_controls,
        "distributed_control_sequence": d_controls,
        "control_semantics": {
            "epoch_bump_and_stop_schema_exact": True,
            "crs_extra_epoch_bump_is_injected_takeover": crs_controls == expected_crs_controls,
            "distributed_no_fault_control": d_controls == expected_distributed_controls,
        },
        "crs_loss": {"count": len(crs_losses), "min": min(crs_losses), "max": max(crs_losses)},
        "distributed_loss": {"count": len(d_losses), "min": min(d_losses), "max": max(d_losses)},
        "loss_ranges_overlap": ranges_overlap,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crs-root", type=Path, required=True)
    parser.add_argument("--distributed-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.crs_root, args.distributed_root)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
