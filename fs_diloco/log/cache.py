"""Rebuildable SQLite materialization of committed proposal consumption."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sqlite3

from .commit import TransactionalLog
from .errors import VerificationError
from .replay import ReplayResult, replay_log


SCHEMA = """
PRAGMA journal_mode=DELETE;
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE consumption (
    proposal_id TEXT PRIMARY KEY,
    commit_seq INTEGER NOT NULL,
    learner_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    fragment_id INTEGER NOT NULL,
    sequence INTEGER NOT NULL
);
"""


@dataclass(frozen=True)
class CacheSnapshot:
    spec_digest: str
    committed_state_digest: str
    head_commit_id: str
    head_commit_seq: int
    consumption: tuple[tuple[str, int, str, str, int, int], ...]


def _snapshot_from_replay(log: TransactionalLog, replay: ReplayResult) -> CacheSnapshot:
    rows = tuple(
        sorted(
            (
                proposal_id,
                replay.consumption[proposal_id],
                replay.proposals[proposal_id].learner_id,
                replay.proposals[proposal_id].session_id,
                replay.proposals[proposal_id].fragment_id,
                replay.proposals[proposal_id].sequence,
            )
            for proposal_id in replay.consumption
        )
    )
    return CacheSnapshot(
        spec_digest=log.spec.digest,
        committed_state_digest=replay.committed_state_digest,
        head_commit_id=replay.head_frontier.commit_id,
        head_commit_seq=replay.head_frontier.commit_seq,
        consumption=rows,
    )


def rebuild_cache(log: TransactionalLog, path: Path) -> CacheSnapshot:
    replay = replay_log(log)
    snapshot = _snapshot_from_replay(log, replay)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.unlink(missing_ok=True)
        connection = sqlite3.connect(temporary)
        try:
            connection.executescript(SCHEMA)
            connection.executemany(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                (
                    ("spec_digest", snapshot.spec_digest),
                    ("committed_state_digest", snapshot.committed_state_digest),
                    ("head_commit_id", snapshot.head_commit_id),
                    ("head_commit_seq", str(snapshot.head_commit_seq)),
                ),
            )
            connection.executemany(
                "INSERT INTO consumption VALUES (?, ?, ?, ?, ?, ?)",
                snapshot.consumption,
            )
            connection.commit()
            if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise VerificationError("rebuilt SQLite cache failed integrity_check")
        finally:
            connection.close()
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return snapshot


def load_cache(path: Path) -> CacheSnapshot:
    try:
        connection = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
        try:
            if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise VerificationError("SQLite cache failed integrity_check")
            metadata = dict(connection.execute("SELECT key, value FROM metadata"))
            if set(metadata) != {
                "spec_digest",
                "committed_state_digest",
                "head_commit_id",
                "head_commit_seq",
            }:
                raise VerificationError("SQLite cache metadata is incomplete")
            rows = tuple(
                connection.execute(
                    "SELECT proposal_id, commit_seq, learner_id, session_id, fragment_id, sequence "
                    "FROM consumption ORDER BY proposal_id"
                )
            )
        finally:
            connection.close()
        return CacheSnapshot(
            spec_digest=metadata["spec_digest"],
            committed_state_digest=metadata["committed_state_digest"],
            head_commit_id=metadata["head_commit_id"],
            head_commit_seq=int(metadata["head_commit_seq"]),
            consumption=rows,
        )
    except VerificationError:
        raise
    except Exception as exc:
        raise VerificationError(f"cannot load SQLite cache: {exc}") from exc


def verify_cache(log: TransactionalLog, path: Path) -> CacheSnapshot:
    observed = load_cache(path)
    expected = _snapshot_from_replay(log, replay_log(log))
    if observed != expected:
        raise VerificationError("SQLite cache differs from authoritative log replay")
    return observed
