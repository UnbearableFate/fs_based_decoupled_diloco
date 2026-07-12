"""Canonical storage discovery with a deletable process-local observation cursor."""

from __future__ import annotations

from dataclasses import dataclass

from fs_diloco.protocol.canonical_json import canonical_digest


@dataclass(frozen=True)
class DiscoveryResult:
    keys: tuple[str, ...]
    newly_observed: tuple[str, ...]
    inventory_digest: str


class DiscoveryCursor:
    """Tracks observation cost only; never filters correctness inventory."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def observe(self, keys) -> DiscoveryResult:
        canonical = tuple(sorted(set(keys)))
        new = tuple(key for key in canonical if key not in self._seen)
        self._seen.update(canonical)
        return DiscoveryResult(
            keys=canonical,
            newly_observed=new,
            inventory_digest=canonical_digest({"keys": list(canonical)}),
        )

    def clear(self) -> None:
        self._seen.clear()
