"""Public verification and inspection entry points."""

from __future__ import annotations

from .commit import TransactionalLog
from .replay import OrphanReport, ReplayResult, inspect_orphans, replay_log


def verify_log(log: TransactionalLog) -> ReplayResult:
    return replay_log(log)


def orphan_report(log: TransactionalLog) -> OrphanReport:
    return inspect_orphans(log)
