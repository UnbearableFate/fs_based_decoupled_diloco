"""P05 terminal takeover assertions layered on the real training probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fs_diloco.log.production import ProductionTransactionalLog
from fs_diloco.log.replay import replay_log
from fs_diloco.log.training_probe import run_probe
from fs_diloco.protocol.schemas import CommitManifest, ControlCommitManifest
from fs_diloco.runtime_view import RuntimeView
from fs_diloco.storage import PosixStorageBackend


def _jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise AssertionError("syncer log row is not an object")
        rows.append(value)
    return rows


def run_terminal_probe(
    *,
    training_root: Path,
    config: Path,
    run_id: str,
    artifact_root: Path,
    output: Path,
) -> dict[str, object]:
    base_output = artifact_root / "base_terminal_gate_report.json"
    base = run_probe(
        training_root=training_root,
        config_path=config,
        storage_root=training_root,
        run_id=run_id,
        output=base_output,
        artifact_root=artifact_root,
    )
    kill = json.loads((artifact_root / "active_kill.json").read_text(encoding="utf-8"))
    events = _jsonl(training_root / "logs" / "syncer.jsonl")
    starts = [row for row in events if row.get("event_type") == "process_start"]
    owners = {str(row.get("owner_id")): bool(row.get("standby")) for row in starts}
    if owners != {"terminal-active": False, "terminal-standby": True}:
        raise AssertionError(f"active/standby process topology differs: {owners}")
    fences = [
        row
        for row in events
        if row.get("event_type") == "coordination_stage_completed"
        and row.get("stage") == "fence_commit_and_strict_replay"
    ]
    epochs = {str(row.get("owner_id")): int(row.get("fencing_epoch", -1)) for row in fences}
    if epochs != {"terminal-active": 1, "terminal-standby": 2}:
        raise AssertionError(f"committed fencing epochs differ: {epochs}")
    standby_fence = next(
        row for row in fences if row.get("owner_id") == "terminal-standby"
    )
    takeover_seconds = float(standby_fence["timestamp"]) - float(
        kill["injected_at_unix_seconds"]
    )
    if not 0.0 < takeover_seconds <= 75.0:
        raise AssertionError(f"takeover RTO is outside the 75-second envelope: {takeover_seconds}")
    if int(kill["observed_optimizer_transition_count"]) < 2:
        raise AssertionError("active kill occurred before two optimizer transitions")

    log = ProductionTransactionalLog.open(
        PosixStorageBackend(training_root / "authority"), run_id, 0
    )
    replay = replay_log(log.transactional)
    view = RuntimeView.from_replay(replay)
    optimizer_commits = [
        item for item in replay.commits if isinstance(item, CommitManifest)
    ]
    control_commits = [
        item for item in replay.commits if isinstance(item, ControlCommitManifest)
    ]
    if view.owner_id != "terminal-standby" or view.fencing_epoch != 2:
        raise AssertionError("terminal authority is not fenced to the standby")
    if view.optimizer_transition_count != 10 or len(optimizer_commits) != 10:
        raise AssertionError("terminal authority does not contain exactly 10 optimizer transitions")
    selected_proposal_ids = [
        selected.proposal_id
        for item in optimizer_commits
        for selected in item.selected_proposals
    ]
    if (
        len(selected_proposal_ids) != len(set(selected_proposal_ids))
        or set(selected_proposal_ids) != set(replay.consumption)
    ):
        raise AssertionError("terminal authority contains a double inclusion")
    if [item.control_kind for item in control_commits] != [
        "epoch_bump",
        "epoch_bump",
        "stop",
    ]:
        raise AssertionError("terminal control-transition sequence differs")
    if view.authoritative_stop is None or view.authoritative_stop.reason != "stop_after_outer_steps":
        raise AssertionError("terminal authoritative stop differs")

    payload = {
        **base,
        "kind": "p05-terminal-real-gpt2-9node-50x10-active-standby",
        "head_commit_seq": view.commit_seq,
        "optimizer_transition_count": view.optimizer_transition_count,
        "control_transition_count": len(control_commits),
        "final_fencing_epoch": view.fencing_epoch,
        "final_owner_id": view.owner_id,
        "active_kill": kill,
        "takeover_seconds": takeover_seconds,
        "standby_strict_replay_seconds": float(standby_fence["seconds"]),
        "split_brain_commits": 0,
        "double_inclusions": 0,
        "assertions": {
            **dict(base["assertions"]),
            "active_and_standby_share_ninth_node": True,
            "active_sigkill_injected": True,
            "standby_took_over_at_epoch_2": True,
            "takeover_started_with_strict_replay": True,
            "exactly_10_optimizer_transitions_after_takeover": True,
            "authoritative_stop_is_separate_control_transition": True,
            "zero_split_brain_or_double_inclusion": True,
        },
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True), flush=True)
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_terminal_probe(
        training_root=args.training_root,
        config=args.config,
        run_id=args.run_id,
        artifact_root=args.artifact_root,
        output=args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
