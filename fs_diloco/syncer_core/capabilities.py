"""Prepare-only immutable object facade used by future learner-hosted executors."""

from __future__ import annotations

from typing import Any, Iterable


def _within_prefixes(key: str, prefixes: tuple[str, ...]) -> bool:
    return any(key == prefix.rstrip("/") or key.startswith(prefix) for prefix in prefixes)


class PrepareObjectFacade:
    """Expose immutable reads/writes without lease, head, listing, or mutation APIs.

    This is a software least-authority boundary for the crash/omission model. It
    is deliberately not described as an OS sandbox against malicious same-user code.
    """

    __slots__ = ("__backend", "_read_prefixes", "_write_prefixes")

    def __init__(
        self,
        backend: Any,
        *,
        read_prefixes: Iterable[str],
        write_prefixes: Iterable[str],
    ) -> None:
        self.__backend = backend
        self._read_prefixes = tuple(read_prefixes)
        self._write_prefixes = tuple(write_prefixes)
        if not self._read_prefixes or not self._write_prefixes:
            raise ValueError("prepare facade requires explicit read and write prefixes")

    def get(self, key: str, *, expected_version: str | None = None) -> bytes:
        if not _within_prefixes(key, self._read_prefixes):
            raise PermissionError(f"prepare facade cannot read {key!r}")
        return self.__backend.get(key, expected_version=expected_version)

    def put_immutable(self, key: str, data: bytes, *, sha256: str | None = None) -> Any:
        if not _within_prefixes(key, self._write_prefixes):
            raise PermissionError(f"prepare facade cannot write {key!r}")
        return self.__backend.put_immutable(key, data, sha256=sha256)

