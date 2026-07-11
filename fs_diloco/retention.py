"""Local checkpoint/update retention helpers."""

from __future__ import annotations

import re
from pathlib import Path
import time
from typing import Any

from .atomic_io import safe_read_json
from .paths import RunPaths

_GLOBAL_WEIGHT_RE = re.compile(r"^global_v(\d{6})\.safetensors$")
_OUTER_OPTIM_RE = re.compile(r"^outer_v(\d{6})\.safetensors$")
_FRAGMENT_ARTIFACT_RE = re.compile(r"^v(\d{6})\.safetensors$")


def _safe_unlink(path: Path, logger: Any | None = None) -> bool:
    try:
        path.unlink(missing_ok=True)
    except Exception as exc:
        if logger is not None:
            logger.event("retention_delete_failed", path=str(path), error=repr(exc))
        return False
    return True


def _versioned_files(directory: Path, pattern: str, regex: re.Pattern[str]) -> list[tuple[int, Path]]:
    files: list[tuple[int, Path]] = []
    for path in directory.glob(pattern):
        match = regex.match(path.name)
        if match is None:
            continue
        files.append((int(match.group(1)), path))
    return files


def cleanup_global_artifacts(paths: RunPaths, *, keep_last: int | None, logger: Any | None = None) -> int:
    """Keep only the newest global weight/outer-optimizer versions produced by the syncer."""
    if keep_last is None:
        return 0
    keep_last = max(0, int(keep_last))
    artifacts = [
        *_versioned_files(paths.weights, "global_v*.safetensors", _GLOBAL_WEIGHT_RE),
        *_versioned_files(paths.optim, "outer_v*.safetensors", _OUTER_OPTIM_RE),
    ]
    versions = sorted({version for version, _path in artifacts})
    keep_versions = set(versions[-keep_last:]) if keep_last else set()
    deleted = 0
    for version, path in artifacts:
        if version in keep_versions:
            continue
        if _safe_unlink(path, logger):
            deleted += 1
    if deleted and logger is not None:
        logger.event("retention_cleanup", role="syncer", deleted_files=deleted, keep_last=keep_last)
    return deleted


def cleanup_fragment_artifacts(
    paths: RunPaths,
    *,
    keep_last: int | None,
    logger: Any | None = None,
) -> int:
    """Keep the newest fragment checkpoint versions for every fragment."""
    if keep_last is None:
        return 0
    keep_last = max(0, int(keep_last))
    deleted = 0
    for root in (paths.fragment_weights, paths.fragment_optim):
        if not root.exists():
            continue
        for fragment_dir in root.glob("fragment_*"):
            if not fragment_dir.is_dir():
                continue
            artifacts = _versioned_files(fragment_dir, "v*.safetensors", _FRAGMENT_ARTIFACT_RE)
            versions = sorted({version for version, _path in artifacts})
            keep_versions = set(versions[-keep_last:]) if keep_last else set()
            for version, path in artifacts:
                if version in keep_versions:
                    continue
                if _safe_unlink(path, logger):
                    deleted += 1
    if deleted and logger is not None:
        logger.event(
            "retention_cleanup",
            role="syncer",
            artifact_kind="fragment",
            deleted_files=deleted,
            keep_last=keep_last,
        )
    return deleted


def cleanup_syncer_model_artifacts(
    paths: RunPaths,
    *,
    keep_last: int,
    logger: Any | None = None,
) -> int:
    """Retain complete recent syncer checkpoints in full and fragment layouts."""
    keep_last = max(1, int(keep_last))
    return (
        cleanup_global_artifacts(paths, keep_last=keep_last, logger=logger)
        + cleanup_fragment_artifacts(
            paths,
            keep_last=keep_last,
            logger=logger,
        )
    )


def _inside_directory(path: Path, directory: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(directory.resolve(strict=False))
    except ValueError:
        return False
    return True


def cleanup_learner_update_artifacts(
    update_dir: Path,
    *,
    keep_last: int | None,
    orphan_grace_seconds: float = 300.0,
    logger: Any | None = None,
) -> int:
    """Keep only the newest update metadata/tensor pairs produced by one learner."""
    if keep_last is None:
        return 0
    keep_last = max(0, int(keep_last))
    orphan_grace_seconds = max(0.0, float(orphan_grace_seconds))
    orphan_cutoff = time.time() - orphan_grace_seconds
    entries: list[tuple[int, float, str, Path, Path | None]] = []
    invalid_meta_paths: list[Path] = []
    for meta_path in update_dir.glob("update_*.meta.json"):
        payload = safe_read_json(meta_path)
        if not isinstance(payload, dict):
            invalid_meta_paths.append(meta_path)
            continue
        try:
            local_step_end = int(payload.get("local_step_end", -1))
        except (TypeError, ValueError):
            local_step_end = -1
        try:
            committed_at = float(payload.get("committed_at", meta_path.stat().st_mtime))
        except (OSError, TypeError, ValueError):
            committed_at = 0.0
        tensor_path: Path | None = None
        raw_file_path = payload.get("file_path")
        if raw_file_path:
            candidate = Path(raw_file_path)
            if not candidate.is_absolute():
                candidate = update_dir / candidate
            if _inside_directory(candidate, update_dir):
                tensor_path = candidate
        if tensor_path is None:
            candidate = update_dir / meta_path.name.removesuffix(".meta.json")
            candidate = candidate.with_name(candidate.name + ".params.safetensors")
            if candidate.exists():
                tensor_path = candidate
        entries.append((local_step_end, committed_at, meta_path.name, meta_path, tensor_path))

    entries.sort(key=lambda item: (item[0], item[1], item[2]))
    keep_entries = entries[-keep_last:] if keep_last else []
    keep_meta_paths = {entry[3].resolve(strict=False) for entry in keep_entries}
    keep_tensor_paths = {
        entry[4].resolve(strict=False)
        for entry in keep_entries
        if entry[4] is not None
    }

    deleted = 0
    for meta_path in invalid_meta_paths:
        if _safe_unlink(meta_path, logger):
            deleted += 1
    for _step, _committed_at, _name, meta_path, tensor_path in entries:
        if meta_path.resolve(strict=False) in keep_meta_paths:
            continue
        if tensor_path is not None and _safe_unlink(tensor_path, logger):
            deleted += 1
        if _safe_unlink(meta_path, logger):
            deleted += 1

    for tensor_path in update_dir.glob("update_*.params.safetensors"):
        if tensor_path.resolve(strict=False) in keep_tensor_paths:
            continue
        try:
            if tensor_path.stat().st_mtime > orphan_cutoff:
                continue
        except OSError:
            continue
        if _safe_unlink(tensor_path, logger):
            deleted += 1

    for tmp_path in update_dir.glob(".update_*.tmp"):
        try:
            if tmp_path.stat().st_mtime > orphan_cutoff:
                continue
        except OSError:
            continue
        if _safe_unlink(tmp_path, logger):
            deleted += 1

    if deleted and logger is not None:
        logger.event(
            "retention_cleanup",
            role="learner",
            update_dir=str(update_dir),
            deleted_files=deleted,
            keep_last=keep_last,
        )
    return deleted


def cleanup_all_learner_update_artifacts(
    paths: RunPaths,
    *,
    keep_last: int | None,
    orphan_grace_seconds: float = 300.0,
    logger: Any | None = None,
) -> int:
    """Apply learner retention to every learner mailbox in a run."""
    deleted = 0
    for update_dir in sorted(paths.updates_pending.glob("learner_*")):
        if not update_dir.is_dir():
            continue
        deleted += cleanup_learner_update_artifacts(
            update_dir,
            keep_last=keep_last,
            orphan_grace_seconds=orphan_grace_seconds,
            logger=logger,
        )
    return deleted
