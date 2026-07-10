"""Canonical logical-key validation and POSIX layout helpers."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import stat

from .errors import InvalidKey, StorageIOError


RESERVED_ROOT = ".duraloco-locks"


def normalize_key(key: str) -> str:
    if not isinstance(key, str) or not key:
        raise InvalidKey("storage key must be a non-empty string")
    pure = PurePosixPath(key)
    if (
        pure.is_absolute()
        or pure.as_posix() != key
        or "\\" in key
        or any(ord(char) < 32 or ord(char) == 127 for char in key)
        or any(part in {"", ".", ".."} for part in pure.parts)
        or pure.parts[0] == RESERVED_ROOT
    ):
        raise InvalidKey(f"storage key is not canonical and contained: {key!r}")
    return key


def normalize_prefix(prefix: str) -> str:
    if prefix == "":
        return ""
    if prefix.endswith("/"):
        return normalize_key(prefix[:-1]) + "/"
    return normalize_key(prefix)


def normalize_request_id(request_id: str | None) -> str | None:
    if request_id is None:
        return None
    if (
        not isinstance(request_id, str)
        or not request_id
        or len(request_id) > 128
        or any(ord(char) < 33 or ord(char) > 126 for char in request_id)
    ):
        raise ValueError("request_id must be 1..128 visible ASCII characters")
    return request_id


def contained_path(root: Path, key: str) -> Path:
    normalized = normalize_key(key)
    root = root.resolve(strict=False)
    candidate = root.joinpath(*PurePosixPath(normalized).parts)
    try:
        candidate.resolve(strict=False).relative_to(root)
    except OSError as exc:
        raise StorageIOError.from_oserror(exc, operation="resolve_key", key=key) from exc
    except (RuntimeError, ValueError) as exc:
        raise InvalidKey(f"storage key escapes backend root: {key!r}") from exc
    current = root
    for part in PurePosixPath(normalized).parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise StorageIOError.from_oserror(exc, operation="lstat_key", key=key) from exc
        if stat.S_ISLNK(mode):
            raise InvalidKey(f"storage key traverses a symbolic link: {key!r}")
    return candidate
