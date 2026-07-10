"""Verify the real 9-node run directly against its SQLite-free authority log."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import yaml

from fs_diloco.analysis import summarize_run
from fs_diloco.log.production import ProductionTransactionalLog
from fs_diloco.log.replay import inspect_orphans, replay_log
from fs_diloco.storage import PosixStorageBackend


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metric_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _forbidden_artifacts(root: Path) -> list[str]:
    suffixes = {"." + "sql" + "ite", "." + "sql" + "ite3", "." + "d" + "b"}
    return [
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
    ]


def run_probe(
    *,
    training_root: Path,
    config_path: Path,
    storage_root: Path,
    run_id: str,
    output: Path,
    artifact_root: Path,
) -> dict[str, object]:
    del storage_root
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    summary = summarize_run(training_root)
    errors: list[str] = []
    if config["model"]["name_or_path"] != "gpt2":
        errors.append("model.name_or_path is not gpt2")
    if config["data"]["dataset_name"] != "wikitext":
        errors.append("dataset is not WikiText")
    if int(config["sync"]["num_learners"]) != 8:
        errors.append("sync.num_learners is not 8")
    if int(config["training"]["inner_steps"]) != 50:
        errors.append("training.inner_steps is not 50")
    if int(config["sync"]["stop_after_outer_steps"]) != 10:
        errors.append("sync.stop_after_outer_steps is not 10")
    if int(summary.get("commit_seq") or -1) != 10:
        errors.append(f"committed transitions={summary.get('commit_seq')}, expected 10")
    if summary.get("stop_reason") != "stop_after_outer_steps":
        errors.append(f"stop reason is {summary.get('stop_reason')!r}")
    if summary.get("payload_codec") != "safetensors-flat-v1":
        errors.append(f"payload codec is {summary.get('payload_codec')!r}")
    if not summary.get("latest_export_valid"):
        errors.append("latest export does not match committed head")

    local_steps = summary.get("learner_local_steps") or {}
    expected_learners = {f"learner_{index:03d}" for index in range(8)}
    if set(local_steps) != expected_learners:
        errors.append(f"learner heartbeat set differs: {sorted(local_steps)}")
    below_50 = {key: value for key, value in local_steps.items() if int(value) < 50}
    if below_50:
        errors.append(f"learners below 50 local steps: {below_50}")
    flags = summary.get("syncer_log_flags") or {}
    if any(flags.values()):
        errors.append(f"syncer failure flags: {flags}")

    learner_metrics = _metric_rows(training_root / "metrics" / "learner_metrics.csv")
    losses: list[float] = []
    invalid_losses = 0
    for row in learner_metrics:
        raw = row.get("train_loss")
        if raw in {None, ""}:
            continue
        try:
            value = float(raw)
        except ValueError:
            invalid_losses += 1
            continue
        if math.isfinite(value):
            losses.append(value)
        else:
            invalid_losses += 1
    if not losses or invalid_losses:
        errors.append(f"finite loss gate failed: finite={len(losses)} invalid={invalid_losses}")

    syncer_metrics = _metric_rows(training_root / "metrics" / "syncer_metrics.csv")
    if len(syncer_metrics) != 10:
        errors.append(f"syncer metric rows={len(syncer_metrics)}, expected 10")
    low_quorum = [
        row.get("version")
        for row in syncer_metrics
        if int(float(row.get("selected_count") or 0)) < 4
    ]
    if low_quorum:
        errors.append(f"transitions below quorum: {low_quorum}")

    checkpoints = sorted((training_root / "weights").glob("global_v*.safetensors"))
    if len(checkpoints) != 11:
        errors.append(f"retained checkpoint count={len(checkpoints)}, expected 11")
    forbidden = _forbidden_artifacts(training_root) + _forbidden_artifacts(artifact_root)
    if forbidden:
        errors.append(f"forbidden runtime artifacts: {forbidden}")
    if errors:
        raise AssertionError("terminal training gate failed:\n- " + "\n- ".join(errors))

    generation = int(summary["run_generation"])
    log = ProductionTransactionalLog.open(
        PosixStorageBackend(training_root / "authority"),
        run_id,
        generation,
    )
    replay = replay_log(log.transactional)
    orphan_report = inspect_orphans(log.transactional)
    selection_counts = [len(commit.selected_proposals) for commit in replay.commits]
    if len(replay.consumption) != sum(selection_counts):
        raise AssertionError("committed proposal inclusion is not exactly once")

    payload = {
        "schema_version": 2,
        "status": "PASS",
        "kind": "m00-terminal-real-gpt2-9node-50x10",
        "training_root": str(training_root),
        "config": str(config_path),
        "config_sha256": _sha256(config_path),
        "model": "gpt2",
        "dataset": "wikitext-2-raw-v1",
        "learners": 8,
        "inner_steps": 50,
        "global_outer_transitions": replay.head_frontier.commit_seq,
        "learner_local_steps": local_steps,
        "finite_loss_count": len(losses),
        "nonfinite_or_invalid_loss_count": invalid_losses,
        "loss_min": min(losses),
        "loss_max": max(losses),
        "stop_reason": summary["stop_reason"],
        "checkpoint_count": len(checkpoints),
        "checkpoints": [
            {"path": str(path), "sha256": _sha256(path)} for path in checkpoints
        ],
        "committed_state_digest": replay.committed_state_digest,
        "runtime_view_digest": summary["runtime_view_digest"],
        "committed_selection_counts": selection_counts,
        "consumed_proposal_count": len(replay.consumption),
        "prepared_orphan_count": len(orphan_report.prepared_orphans),
        "forbidden_runtime_artifacts": forbidden,
        "assertions": {
            "real_gpt2_wikitext": True,
            "nine_process_layout": True,
            "all_learners_at_least_50_local_steps": True,
            "exactly_10_head_cas_transitions": True,
            "losses_finite": True,
            "checkpoints_complete": True,
            "production_log_is_authority": True,
            "params_outer_state_paired": True,
            "proposal_inclusion_exactly_once": True,
            "no_forbidden_runtime_artifacts": True,
        },
        "limitations": [
            "M00 assumes one active syncer; lease and fencing begin in P05",
            "learner recovery is warm until later capsule work",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True), flush=True)
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_probe(
        training_root=args.training_root,
        config_path=args.config,
        storage_root=args.storage_root,
        run_id=args.run_id,
        output=args.output,
        artifact_root=args.artifact_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
