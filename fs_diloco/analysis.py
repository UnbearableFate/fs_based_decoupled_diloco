"""Deterministic run analysis from the committed log and append-only telemetry."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import sys
from typing import Any

import yaml

from .atomic_io import safe_read_json
from .fragment_scheduler import expected_fragment_versions_after_events
from .log.production import ProductionTransactionalLog
from .log.replay import replay_log
from .runtime_view import RuntimeView
from .storage import PosixStorageBackend


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_csv_summary(path: Path) -> dict[str, Any]:
    rows = _read_csv_rows(path)
    return {"path": str(path), "exists": path.exists(), "rows": len(rows)}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _heartbeats(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted((root / "heartbeats").glob("learner_*.json")):
        value = safe_read_json(path)
        if isinstance(value, dict) and isinstance(value.get("learner_id"), str):
            result[value["learner_id"]] = value
    return result


def _loss_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    values: list[float] = []
    invalid = 0
    for row in rows:
        raw = row.get("train_loss")
        if raw in {None, ""}:
            continue
        try:
            value = float(raw)
        except ValueError:
            invalid += 1
            continue
        if math.isfinite(value):
            values.append(value)
        else:
            invalid += 1
    return {
        "count": len(values),
        "invalid_or_nonfinite": invalid,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "obvious_divergence": invalid > 0,
    }


def _syncer_log_flags(root: Path) -> dict[str, bool]:
    rows = _read_jsonl(root / "logs" / "syncer.jsonl")
    events = {str(row.get("event")) for row in rows}
    text = json.dumps(rows, sort_keys=True)
    return {
        "error": "error" in events,
        "no_progress_timeout": "no_progress_timeout" in events,
        "uncaught_exception": "uncaught_exception" in text,
    }


def _learner_adoption(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted((root / "logs").glob("learner_*.jsonl")):
        events = _read_jsonl(path)
        adopted = [
            row for row in events if row.get("event") in {"fragments_adopted", "global_adopted"}
        ]
        result[path.stem] = {
            "adoption_events": len(adopted),
            "has_adopted_after_initial": bool(adopted),
        }
    return result


def _resolved_config(root: Path) -> dict[str, Any]:
    path = root / "control" / "run_config.resolved.yaml"
    if not path.exists():
        return {}
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return value if isinstance(value, dict) else {}


def _open_replay(root: Path, config: dict[str, Any]):
    run = config.get("run") if isinstance(config.get("run"), dict) else {}
    init = config.get("init") if isinstance(config.get("init"), dict) else {}
    run_id = run.get("run_id")
    generation = int(init.get("run_generation", 0))
    if not isinstance(run_id, str) or not run_id:
        latest = safe_read_json(root / "control" / "latest.json") or {}
        run_id = latest.get("run_id")
        generation = int(latest.get("run_generation", 0))
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run identity is unavailable")
    log = ProductionTransactionalLog.open(
        PosixStorageBackend(root / "authority"),
        run_id,
        generation,
    )
    replay = replay_log(log.transactional)
    return log, replay, RuntimeView.from_replay(replay)


def summarize_run(shared_root: str | Path) -> dict[str, Any]:
    root = Path(shared_root)
    config = _resolved_config(root)
    log, replay, view = _open_replay(root, config)
    latest = safe_read_json(root / "control" / "latest.json")
    stop = safe_read_json(root / "control" / "stop.json") or {}
    heartbeats = _heartbeats(root)
    learner_rows = _read_csv_rows(root / "metrics" / "learner_metrics.csv")
    selection_counts = {
        str(commit.commit_seq): len(commit.selected_proposals) for commit in replay.commits
    }
    fragment_versions = {
        str(fragment_id): state.version for fragment_id, state in view.fragments.items()
    }
    materialized = root / "weights" / f"global_v{view.commit_seq:06d}.safetensors"
    return {
        "shared_root": str(root),
        "run_id": view.run_id,
        "run_generation": view.run_generation,
        "authority": "committed-transition-log",
        "commit_seq": view.commit_seq,
        "commit_id": view.commit_id,
        "frontier_sha256": view.frontier_sha256,
        "committed_state_digest": view.committed_state_digest,
        "runtime_view_digest": view.view_digest,
        "global_merge_event": view.commit_seq,
        "total_seen_tokens": view.total_seen_tokens,
        "consumed_proposal_count": len(view.consumed_proposal_ids),
        "fragment_versions": fragment_versions,
        "latest_kind": "fragment" if len(view.fragments) > 1 else "full",
        "latest": latest,
        "latest_export_valid": bool(
            latest
            and latest.get("commit_id") == view.commit_id
            and latest.get("committed_state_digest") == view.committed_state_digest
        ),
        "materialized_weight_exists": materialized.exists(),
        "stop_reason": stop.get("reason"),
        "heartbeats": heartbeats,
        "learner_local_steps": {
            key: int(value.get("last_local_step") or 0) for key, value in heartbeats.items()
        },
        "learner_fragment_adoption": _learner_adoption(root),
        "loss_summary": _loss_summary(learner_rows),
        "syncer_metrics": _read_csv_summary(root / "metrics" / "syncer_metrics.csv"),
        "learner_metrics": _read_csv_summary(root / "metrics" / "learner_metrics.csv"),
        "update_manifest": _read_csv_summary(root / "metrics" / "update_manifest.csv"),
        "committed_selected_counts_by_event": selection_counts,
        "syncer_log_flags": _syncer_log_flags(root),
        "payload_codec": log.spec.payload_codec,
    }


def _parse_fragment_ids(text: str) -> list[int]:
    return [int(part) for part in text.split(",") if part.strip()]


def assert_fragment_run(args: argparse.Namespace, *, require_local_steps: bool) -> None:
    summary = summarize_run(args.run_root)
    errors: list[str] = []
    expected_ids = _parse_fragment_ids(args.expected_fragment_ids)
    if summary.get("latest_kind") != "fragment":
        errors.append(f"latest_kind is {summary.get('latest_kind')!r}, expected 'fragment'")
    events = int(args.expected_global_merge_events)
    if int(summary.get("global_merge_event") or -1) != events:
        errors.append(f"global_merge_event is {summary.get('global_merge_event')}, expected {events}")
    actual_versions = {
        int(key): int(value) for key, value in (summary.get("fragment_versions") or {}).items()
    }
    expected_versions = expected_fragment_versions_after_events(len(expected_ids), events)
    for fragment_id in expected_ids:
        if actual_versions.get(fragment_id) != expected_versions[fragment_id]:
            errors.append(
                f"fragment {fragment_id} version is {actual_versions.get(fragment_id)}, "
                f"expected {expected_versions[fragment_id]}"
            )
    if summary.get("stop_reason") != "stop_after_outer_steps":
        errors.append(f"stop_reason is {summary.get('stop_reason')!r}")
    if not summary.get("materialized_weight_exists"):
        errors.append("materialized full checkpoint is missing")
    selected = summary.get("committed_selected_counts_by_event") or {}
    for event in range(1, events + 1):
        if int(selected.get(str(event), 0)) < int(args.min_selected_count):
            errors.append(f"committed selection count for event {event} is too small")
    heartbeats = summary.get("heartbeats") or {}
    if len(heartbeats) < int(args.expected_learners):
        errors.append("learner heartbeat count is too small")
    if require_local_steps:
        for index in range(int(args.expected_learners)):
            learner_id = f"learner_{index:03d}"
            if int((summary.get("learner_local_steps") or {}).get(learner_id, 0)) < int(
                args.expected_local_steps
            ):
                errors.append(f"{learner_id} did not reach the required local steps")
    loss = summary.get("loss_summary") or {}
    if int(loss.get("count") or 0) == 0 or loss.get("obvious_divergence"):
        errors.append(f"learner loss evidence is invalid: {loss}")
    flags = summary.get("syncer_log_flags") or {}
    if any(flags.values()):
        errors.append(f"syncer log contains failure markers: {flags}")
    if errors:
        raise SystemExit("fragment assertion failed:\n" + "\n".join(f"- {item}" for item in errors))


def _summary_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shared_root", help="Run shared root")
    parser.add_argument("--json", action="store_true", help="Emit JSON summary")
    return parser


def _assert_parser(name: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=f"analysis {name}")
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--expected-learners", type=int, required=True)
    parser.add_argument("--expected-local-steps", type=int, default=0)
    parser.add_argument("--expected-global-merge-events", type=int, required=True)
    parser.add_argument("--expected-fragment-ids", required=True)
    parser.add_argument("--min-selected-count", type=int, required=True)
    return parser


def _print_summary(summary: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, indent=2, sort_keys=True, default=str))
        return
    print(f"shared_root: {summary['shared_root']}")
    print(f"commit_seq: {summary['commit_seq']}")
    print(f"commit_id: {summary['commit_id']}")
    print(f"committed_state_digest: {summary['committed_state_digest']}")
    print(f"stop_reason: {summary.get('stop_reason')}")
    print(f"fragment_versions: {summary.get('fragment_versions')}")
    print(f"consumed_proposal_count: {summary['consumed_proposal_count']}")


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] == "summary":
        args = _summary_parser().parse_args(argv[1:])
        _print_summary(summarize_run(args.shared_root), as_json=args.json)
        return
    if argv and argv[0] in {"assert-fragment-smoke", "assert-fragment-5000"}:
        args = _assert_parser(argv[0]).parse_args(argv[1:])
        assert_fragment_run(args, require_local_steps=argv[0] == "assert-fragment-5000")
        return
    args = _summary_parser().parse_args(argv)
    _print_summary(summarize_run(args.shared_root), as_json=args.json)


if __name__ == "__main__":
    main()
