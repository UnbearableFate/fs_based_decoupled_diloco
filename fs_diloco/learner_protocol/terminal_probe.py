"""P06 terminal learner interval/adoption/recovery assertions over P05 fencing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fs_diloco.coordination.terminal_probe import run_terminal_probe as run_p05_probe
from fs_diloco.log.layout import LogLayout
from fs_diloco.storage import PosixStorageBackend


def _events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def run_terminal_probe(
    *, training_root: Path, config: Path, run_id: str, artifact_root: Path, output: Path
) -> dict[str, object]:
    p05_output = artifact_root / "p05_terminal_gate_report.json"
    base = run_p05_probe(
        training_root=training_root,
        config=config,
        run_id=run_id,
        artifact_root=artifact_root,
        output=p05_output,
    )
    kill = json.loads((artifact_root / "learner_kill.json").read_text(encoding="utf-8"))
    if not kill.get("after_first_publication"):
        raise AssertionError("learner kill did not follow an immutable publication")
    sessions_by_learner: dict[str, set[str]] = {}
    recovery_by_learner: dict[str, int] = {}
    adoption_by_learner: dict[str, int] = {}
    recovery_backpressure_by_learner: dict[str, int] = {}
    for index in range(8):
        learner_id = f"learner_{index:03d}"
        events = _events(training_root / "logs" / f"{learner_id}.jsonl")
        recoveries = [row for row in events if row.get("event_type") == "warm_recovery"]
        sessions = {
            str(row["new_session"]["learner_session_id"])
            for row in recoveries
            if isinstance(row.get("new_session"), dict)
        }
        sessions_by_learner[learner_id] = sessions
        recovery_by_learner[learner_id] = len(recoveries)
        adoption_by_learner[learner_id] = sum(
            row.get("event_type") in {"global_adopted", "fragments_adopted"}
            for row in events
        )
        recovery_backpressure_by_learner[learner_id] = sum(
            row.get("event_type") == "recovery_backpressure_resolved" for row in events
        )
        if not recoveries or not all(bool(row.get("warm_not_exact")) for row in recoveries):
            raise AssertionError(f"{learner_id} lacks explicit warm-recovery semantics")
        if adoption_by_learner[learner_id] < 1:
            raise AssertionError(f"{learner_id} did not record boundary adoption")
    if len(sessions_by_learner["learner_000"]) < 2:
        raise AssertionError("restarted learner did not create a distinct session")
    if recovery_backpressure_by_learner["learner_000"] < 1:
        raise AssertionError("restarted learner bypassed committed-successor backpressure")

    backend = PosixStorageBackend(training_root / "authority")
    layout = LogLayout(run_id, 0)
    marker_keys = [
        key
        for key in backend.list_prefix(layout.learner_publication_prefix)
        if "/markers/" in key
    ]
    if not marker_keys:
        raise AssertionError("terminal run has no immutable learner publication markers")
    identities: set[tuple[str, str, int, int]] = set()
    bases: set[tuple[str, str, int, str, int]] = set()
    marker_sessions: dict[str, set[str]] = {}
    for key in marker_keys:
        marker = json.loads(backend.get(key))
        interval = marker["interval"]
        learner_id = str(interval["learner_id"])
        session_id = str(interval["learner_session_id"])
        sequence = int(interval["sequence"])
        fragment_id = int(interval["fragment_id"])
        identity = learner_id, session_id, sequence, fragment_id
        if identity in identities:
            raise AssertionError("learner publication identity was reused")
        identities.add(identity)
        interval_base = interval["base"]
        base_identity = (
            learner_id,
            session_id,
            fragment_id,
            str(interval_base["commit_id"]),
            int(interval_base["fragment_versions"][str(fragment_id)]),
        )
        if base_identity in bases:
            raise AssertionError("same-session/base interval publication overlapped")
        bases.add(base_identity)
        if interval["transport_dtype"] != "bfloat16" or interval["committed_dtype"] != "float32":
            raise AssertionError("terminal numeric transport/commit identity regressed")
        if interval["numeric_contract"] != "proposal-transport-to-float32-commit-v1":
            raise AssertionError("terminal numeric contract identity regressed")
        if int(interval["target_tokens"]) <= 0:
            raise AssertionError("terminal interval has no target tokens")
        marker_sessions.setdefault(learner_id, set()).add(session_id)
    if set(marker_sessions) != {f"learner_{index:03d}" for index in range(8)}:
        raise AssertionError("immutable marker learner set differs")
    if len(marker_sessions["learner_000"]) < 2:
        raise AssertionError("immutable markers do not preserve the restart session boundary")

    payload = {
        **base,
        "kind": "p06-terminal-real-gpt2-9node-50x10-learner-warm-restart",
        "learner_kill": kill,
        "immutable_publication_marker_count": len(marker_keys),
        "learner_sessions": {key: sorted(value) for key, value in sessions_by_learner.items()},
        "warm_recovery_events": recovery_by_learner,
        "boundary_adoption_events": adoption_by_learner,
        "recovery_backpressure_events": recovery_backpressure_by_learner,
        "optimizer_adoption_policy": "reset_all",
        "numeric_contract": "bfloat16-proposal-to-float32-aggregate-commit-v1",
        "assertions": {
            **dict(base["assertions"]),
            "learner_sigkill_after_publication": True,
            "warm_restart_uses_distinct_session": True,
            "warm_restart_waits_for_committed_successor": True,
            "interval_bases_are_frozen_and_nonoverlapping": True,
            "adoption_occurs_at_boundaries": True,
            "marker_last_publication_is_immutable": True,
            "bfloat16_transport_float32_commit_preserved": True,
        },
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True), flush=True)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
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
