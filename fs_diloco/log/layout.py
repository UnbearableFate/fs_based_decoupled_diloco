"""Backend-neutral logical keys for one isolated DuraLoCo run generation."""

from __future__ import annotations

from dataclasses import dataclass
import re

from fs_diloco.storage.layout import normalize_key


_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _component(value: str, field: str) -> str:
    if not isinstance(value, str) or _COMPONENT.fullmatch(value) is None:
        raise ValueError(f"{field} must be a safe 1..128 character identifier")
    return value


@dataclass(frozen=True)
class LogLayout:
    run_id: str
    run_generation: int = 0

    def __post_init__(self) -> None:
        _component(self.run_id, "run_id")
        if type(self.run_generation) is not int or self.run_generation < 0:
            raise ValueError("run_generation must be a non-negative integer")

    @property
    def root(self) -> str:
        return normalize_key(
            f"runs/{self.run_id}/generations/{self.run_generation:08d}"
        )

    @property
    def immutable_prefix(self) -> str:
        return f"{self.root}/immutable/"

    @property
    def proposal_prefix(self) -> str:
        return f"{self.root}/immutable/proposals/"

    @property
    def run_manifest_key(self) -> str:
        return f"{self.root}/control/run-manifest.json"

    @property
    def head_key(self) -> str:
        return f"{self.root}/control/head.json"

    @property
    def lease_key(self) -> str:
        return f"{self.root}/control/lease.json"

    def proposal_key(self, proposal_id: str) -> str:
        return normalize_key(f"{self.proposal_prefix}{_component(proposal_id, 'proposal_id')}.json")

    def proposal_payload_key(self, sha256: str) -> str:
        return self._content_key("proposals/payloads", sha256, "safetensors")

    def params_key(self, fragment_id: int, sha256: str) -> str:
        return self._payload_key("params", fragment_id, sha256)

    def outer_state_key(self, fragment_id: int, sha256: str) -> str:
        return self._payload_key("outer-state", fragment_id, sha256)

    def production_params_key(self, fragment_id: int, sha256: str) -> str:
        return self._payload_key("params", fragment_id, sha256, suffix="safetensors")

    def production_outer_state_key(self, fragment_id: int, sha256: str) -> str:
        return self._payload_key("outer-state", fragment_id, sha256, suffix="safetensors")

    def _payload_key(
        self,
        kind: str,
        fragment_id: int,
        sha256: str,
        *,
        suffix: str = "json",
    ) -> str:
        if type(fragment_id) is not int or fragment_id < 0:
            raise ValueError("fragment_id must be a non-negative integer")
        if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError("payload digest must be 64 lowercase hex characters")
        return normalize_key(
            f"{self.root}/immutable/fragments/{fragment_id:08d}/{kind}-{sha256}.{suffix}"
        )

    def _content_key(self, prefix: str, sha256: str, suffix: str) -> str:
        if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError("payload digest must be 64 lowercase hex characters")
        return normalize_key(f"{self.root}/immutable/{prefix}/{sha256}.{suffix}")

    def commit_key(self, commit_seq: int, commit_id: str) -> str:
        if type(commit_seq) is not int or commit_seq < 1:
            raise ValueError("commit_seq must be positive")
        return normalize_key(
            f"{self.root}/immutable/commits/{commit_seq:020d}-{_component(commit_id, 'commit_id')}.json"
        )

    def frontier_key(self, commit_seq: int, frontier_sha256: str) -> str:
        if type(commit_seq) is not int or commit_seq < 0:
            raise ValueError("commit_seq must be non-negative")
        if not isinstance(frontier_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", frontier_sha256
        ):
            raise ValueError("frontier digest must be 64 lowercase hex characters")
        return normalize_key(
            f"{self.root}/immutable/frontiers/{commit_seq:020d}-{frontier_sha256}.json"
        )
