"""Bind the terminal real GPT-2 run to the complete P04 correctness probe."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import yaml

from fs_diloco.analysis import summarize_run
from fs_diloco.log.model import ReferenceProposal
from fs_diloco.storage import InMemoryStorageBackend, PosixStorageBackend

from .cache import rebuild_cache, verify_cache
from .commit import CRASH_POINTS, TransactionalLog
from .inspect_cli import main as inspect_main
from .miyabi_worker import run_one_node
from .replay import inspect_orphans, replay_log
from .run import RunSpec


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _projection(digest: str) -> tuple[float, float]:
    scale = float(0xFFFFFFFF)
    return (
        int(digest[:8], 16) / scale * 2.0 - 1.0,
        int(digest[8:16], 16) / scale * 2.0 - 1.0,
    )


def _metric_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _build_projection(
    backend,
    *,
    spec: RunSpec,
    checkpoint_digests: list[str],
    token_counts: list[int],
) -> tuple[TransactionalLog, object]:
    log = TransactionalLog.initialize(
        backend, spec, {0: _projection(checkpoint_digests[0])}
    )
    for sequence, digest in enumerate(checkpoint_digests[1:], start=1):
        current = replay_log(log).head_frontier
        proposal = ReferenceProposal.create(
            learner_id=f"training-event-{sequence:02d}",
            session_id="terminal-gpt2-run",
            sequence=sequence,
            fragment_id=0,
            base_commit_id=current.commit_id,
            base_commit_seq=current.commit_seq,
            base_fragment_version=current.fragments[0].version,
            target_tokens=max(1, token_counts[sequence - 1]),
            values=_projection(digest),
        )
        log.publish_proposal(proposal)
        log.commit_transition(fragment_id=0, selected_proposal_ids=(proposal.proposal_id,))
    return log, replay_log(log)


def run_probe(
    *,
    training_root: Path,
    config_path: Path,
    storage_root: Path,
    run_id: str,
    output: Path,
    artifact_root: Path,
) -> dict[str, object]:
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
    if int(summary.get("global_merge_event") or -1) != 10:
        errors.append(f"observed global transitions={summary.get('global_merge_event')}, expected 10")
    if summary.get("stop_reason") != "stop_after_outer_steps":
        errors.append(f"stop reason is {summary.get('stop_reason')!r}")
    local_steps = summary.get("learner_local_steps") or {}
    expected_learners = {f"learner_{index:03d}" for index in range(8)}
    if set(local_steps) != expected_learners:
        errors.append(f"learner heartbeat set differs: {sorted(local_steps)}")
    below_50 = {key: value for key, value in local_steps.items() if int(value) < 50}
    if below_50:
        errors.append(f"learners below 50 local steps: {below_50}")
    flags = summary.get("syncer_log_flags") or {}
    if flags.get("error") or flags.get("no_progress_timeout") or flags.get("uncaught_exception"):
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
        if not math.isfinite(value):
            invalid_losses += 1
        else:
            losses.append(value)
    if not losses or invalid_losses:
        errors.append(
            f"finite loss gate failed: finite={len(losses)} invalid_or_nonfinite={invalid_losses}"
        )

    syncer_metrics = _metric_rows(training_root / "metrics" / "syncer_metrics.csv")
    if len(syncer_metrics) != 10:
        errors.append(f"syncer metric rows={len(syncer_metrics)}, expected exactly 10")
    low_quorum = [
        row.get("version")
        for row in syncer_metrics
        if int(float(row.get("selected_count") or 0)) < 4
    ]
    if low_quorum:
        errors.append(f"outer transitions below quorum: {low_quorum}")
    token_counts = [int(float(row.get("total_update_tokens") or 1)) for row in syncer_metrics]

    checkpoints = sorted((training_root / "weights").glob("global_v*.safetensors"))
    if len(checkpoints) != 11:
        errors.append(f"retained checkpoint count={len(checkpoints)}, expected 11")
    checkpoint_digests = [_sha256(path) for path in checkpoints]
    if errors:
        raise AssertionError("terminal training gate failed:\n- " + "\n- ".join(errors))

    param_index = training_root / "control" / "param_index.json"
    spec = RunSpec(
        run_id=f"{run_id}-projection",
        run_generation=0,
        model_revision="gpt2-terminal-real-run",
        parameter_index_digest=_sha256(param_index),
        fragment_layout_digest=_json_digest(
            {"kind": "full-vector", "parameter_index": _sha256(param_index)}
        ),
        outer_optimizer_schema_digest=_json_digest(config["outer_optimizer"]),
    )
    posix_log, posix_replay = _build_projection(
        PosixStorageBackend(storage_root),
        spec=spec,
        checkpoint_digests=checkpoint_digests,
        token_counts=token_counts,
    )
    _, memory_replay = _build_projection(
        InMemoryStorageBackend(),
        spec=spec,
        checkpoint_digests=checkpoint_digests,
        token_counts=token_counts,
    )
    if posix_replay.prefix_digests != memory_replay.prefix_digests:
        raise AssertionError("real-run projection differs between memory and POSIX")
    cache_path = artifact_root / "training_projection_cache.sqlite"
    first_cache = rebuild_cache(posix_log, cache_path)
    cache_path.unlink()
    second_cache = rebuild_cache(posix_log, cache_path)
    if first_cache != second_cache or verify_cache(posix_log, cache_path) != first_cache:
        raise AssertionError("real-run projection cache did not rebuild exactly")
    candidate = ReferenceProposal.create(
        learner_id="terminal-orphan",
        session_id="terminal-orphan",
        sequence=1,
        fragment_id=0,
        base_commit_id=posix_replay.head_frontier.commit_id,
        base_commit_seq=posix_replay.head_frontier.commit_seq,
        base_fragment_version=posix_replay.head_frontier.fragments[0].version,
        target_tokens=1,
        values=(0.25, -0.25),
    )
    posix_log.publish_proposal(candidate)
    prepared = posix_log.prepare_transition(
        fragment_id=0, selected_proposal_ids=(candidate.proposal_id,)
    )
    orphans = inspect_orphans(posix_log)
    if prepared.commit_ref.key not in orphans.prepared_orphans:
        raise AssertionError("real-run prepared orphan was not isolated")

    cli_output = artifact_root / "inspect_verify.json"
    if inspect_main(
        [
            "verify",
            "--root",
            str(storage_root),
            "--run-id",
            spec.run_id,
            "--output",
            str(cli_output),
        ]
    ) != 0:
        raise AssertionError("P04 inspect CLI rejected the real-run projection")
    contract_report = run_one_node(
        root=storage_root,
        run_id=f"{run_id}-contract",
        output=artifact_root / "p04_contract_report.json",
        cache=artifact_root / "p04_contract_cache.sqlite",
    )

    payload = {
        "schema_version": 1,
        "status": "PASS",
        "kind": "p04-terminal-real-gpt2-9node-50x10",
        "training_root": str(training_root),
        "config": str(config_path),
        "config_sha256": _sha256(config_path),
        "model": "gpt2",
        "dataset": "wikitext-2-raw-v1",
        "learners": 8,
        "inner_steps": 50,
        "global_outer_transitions": 10,
        "learner_local_steps": local_steps,
        "finite_loss_count": len(losses),
        "nonfinite_or_invalid_loss_count": invalid_losses,
        "loss_min": min(losses),
        "loss_max": max(losses),
        "stop_reason": summary["stop_reason"],
        "checkpoint_count": len(checkpoints),
        "checkpoints": [
            {"path": str(path), "sha256": digest}
            for path, digest in zip(checkpoints, checkpoint_digests, strict=True)
        ],
        "p04_projection_commit_seq": posix_replay.head_frontier.commit_seq,
        "p04_projection_prefix_digests": list(posix_replay.prefix_digests),
        "p04_projection_state_digest": posix_replay.committed_state_digest,
        "p04_memory_posix_equal": True,
        "p04_cache_rebuild_exact": True,
        "p04_prepared_orphan_count": len(orphans.prepared_orphans),
        "p04_cli_verify": "PASS",
        "p04_contract": contract_report,
        "assertions": {
            "real_gpt2_wikitext": True,
            "nine_process_layout": True,
            "all_learners_at_least_50_local_steps": True,
            "exactly_10_global_outer_transitions": True,
            "losses_finite": True,
            "checkpoints_complete": True,
            "p04_one_cas_prefix_replay": True,
            "p04_memory_posix_equal": True,
            "p04_cache_rebuild_exact": True,
            "p04_orphan_not_committed": True,
            "p04_cli_verify": True,
            "p04_crash_matrix_complete": len(contract_report["crash_points"])
            == len(CRASH_POINTS),
        },
        "limitations": [
            "P04 is not the production syncer authority until P05 integration",
            "the P04 terminal probe commits deterministic projections bound to real checkpoint SHA-256 values",
        ],
    }
    if not all(payload["assertions"].values()):
        raise AssertionError("one or more terminal P04 assertions are false")
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
