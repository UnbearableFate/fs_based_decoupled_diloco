"""Conditional observational lease operations for P05 syncer liveness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from fs_diloco.log.layout import LogLayout
from fs_diloco.protocol.canonical_json import canonical_bytes, canonical_digest, loads_strict
from fs_diloco.storage import InjectedTimeout, NotFound, PreconditionFailed
from fs_diloco.storage.base import ObjectMetadata, StorageBackend

from .state_machine import CoordinationConflict, MutationRequestConflict, OwnerToken


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise CoordinationConflict(f"{name} must be a non-empty string")
    return value


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise CoordinationConflict(f"{name} must be an integer >= {minimum}")
    return value


@dataclass(frozen=True)
class LeaseMutation:
    operation: str
    request_id: str
    owner_id: str
    owner_session_id: str
    observed_fencing_epoch: int
    requested_at_utc_ns: int
    ttl_ns: int

    def __post_init__(self) -> None:
        if self.operation not in {"acquire", "renew", "release"}:
            raise ValueError(f"unsupported lease operation: {self.operation}")
        _string(self.request_id, "request_id")
        _string(self.owner_id, "owner_id")
        _string(self.owner_session_id, "owner_session_id")
        _integer(self.observed_fencing_epoch, "observed_fencing_epoch")
        _integer(self.requested_at_utc_ns, "requested_at_utc_ns")
        _integer(self.ttl_ns, "ttl_ns", minimum=1)

    def identity(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "request_id": self.request_id,
            "owner_id": self.owner_id,
            "owner_session_id": self.owner_session_id,
            "observed_fencing_epoch": self.observed_fencing_epoch,
            "requested_at_utc_ns": self.requested_at_utc_ns,
            "ttl_ns": self.ttl_ns,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.identity())


@dataclass(frozen=True)
class LeaseRecord:
    protocol_version: int
    run_id: str
    run_generation: int
    owner_id: str
    owner_session_id: str
    proposed_fencing_epoch: int
    lease_sequence: int
    expires_at_utc_ns: int
    mutation_operation: str
    mutation_request_id: str
    mutation_digest: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LeaseRecord":
        required = {
            "protocol_version",
            "run_id",
            "run_generation",
            "owner_id",
            "owner_session_id",
            "proposed_fencing_epoch",
            "lease_sequence",
            "expires_at_utc_ns",
            "mutation_operation",
            "mutation_request_id",
            "mutation_digest",
        }
        if not isinstance(payload, Mapping):
            raise CoordinationConflict("lease record root must be an object")
        missing = required - set(payload)
        unknown = set(payload) - required
        if missing or unknown:
            raise CoordinationConflict(
                f"lease record fields differ: missing={sorted(missing)}, "
                f"unknown={sorted(unknown)}"
            )
        operation = payload["mutation_operation"]
        if operation not in {"acquire", "renew", "release"}:
            raise CoordinationConflict("lease mutation operation is invalid")
        digest = _string(payload["mutation_digest"], "mutation_digest")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise CoordinationConflict("mutation_digest must be 64 lowercase hex")
        if payload["protocol_version"] != 2:
            raise CoordinationConflict("lease protocol_version must equal 2")
        return cls(
            protocol_version=2,
            run_id=_string(payload["run_id"], "run_id"),
            run_generation=_integer(payload["run_generation"], "run_generation"),
            owner_id=_string(payload["owner_id"], "owner_id"),
            owner_session_id=_string(
                payload["owner_session_id"], "owner_session_id"
            ),
            proposed_fencing_epoch=_integer(
                payload["proposed_fencing_epoch"],
                "proposed_fencing_epoch",
                minimum=1,
            ),
            lease_sequence=_integer(
                payload["lease_sequence"], "lease_sequence", minimum=1
            ),
            expires_at_utc_ns=_integer(
                payload["expires_at_utc_ns"], "expires_at_utc_ns"
            ),
            mutation_operation=operation,
            mutation_request_id=_string(
                payload["mutation_request_id"], "mutation_request_id"
            ),
            mutation_digest=digest,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "LeaseRecord":
        try:
            payload = loads_strict(data)
        except Exception as exc:
            raise CoordinationConflict(f"cannot parse lease record: {exc}") from exc
        return cls.from_dict(payload)

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol_version": self.protocol_version,
            "run_id": self.run_id,
            "run_generation": self.run_generation,
            "owner_id": self.owner_id,
            "owner_session_id": self.owner_session_id,
            "proposed_fencing_epoch": self.proposed_fencing_epoch,
            "lease_sequence": self.lease_sequence,
            "expires_at_utc_ns": self.expires_at_utc_ns,
            "mutation_operation": self.mutation_operation,
            "mutation_request_id": self.mutation_request_id,
            "mutation_digest": self.mutation_digest,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_bytes(self.to_dict())

    @property
    def owner_token(self) -> OwnerToken:
        return OwnerToken(
            owner_id=self.owner_id,
            owner_session_id=self.owner_session_id,
            fencing_epoch=self.proposed_fencing_epoch,
        )


@dataclass(frozen=True)
class LoadedLease:
    record: LeaseRecord
    metadata: ObjectMetadata


class LeaseManager:
    """Mutate the observational lease with one backend conditional object."""

    def __init__(
        self,
        backend: StorageBackend,
        layout: LogLayout,
        *,
        max_clock_skew_ns: int,
    ) -> None:
        if type(max_clock_skew_ns) is not int or max_clock_skew_ns < 0:
            raise ValueError("max_clock_skew_ns must be a non-negative integer")
        self.backend = backend
        self.layout = layout
        self.max_clock_skew_ns = max_clock_skew_ns

    def load(self) -> LoadedLease:
        last_error: Exception | None = None
        for _ in range(5):
            try:
                metadata = self.backend.head(self.layout.lease_key)
                data = self.backend.get(
                    self.layout.lease_key, expected_version=metadata.version
                )
                record = LeaseRecord.from_bytes(data)
                if (
                    record.run_id != self.layout.run_id
                    or record.run_generation != self.layout.run_generation
                ):
                    raise CoordinationConflict("lease belongs to another run generation")
                return LoadedLease(record, metadata)
            except PreconditionFailed as exc:
                last_error = exc
        raise CoordinationConflict(f"lease changed repeatedly while reading: {last_error}")

    @staticmethod
    def _same_request(record: LeaseRecord, mutation: LeaseMutation) -> bool:
        if record.mutation_request_id != mutation.request_id:
            return False
        if record.mutation_digest != mutation.digest:
            raise MutationRequestConflict(
                "lease request identity maps to different canonical content"
            )
        return True

    def _record(
        self,
        mutation: LeaseMutation,
        *,
        proposed_epoch: int,
        lease_sequence: int,
        expires_at_utc_ns: int,
    ) -> LeaseRecord:
        return LeaseRecord(
            protocol_version=2,
            run_id=self.layout.run_id,
            run_generation=self.layout.run_generation,
            owner_id=mutation.owner_id,
            owner_session_id=mutation.owner_session_id,
            proposed_fencing_epoch=proposed_epoch,
            lease_sequence=lease_sequence,
            expires_at_utc_ns=expires_at_utc_ns,
            mutation_operation=mutation.operation,
            mutation_request_id=mutation.request_id,
            mutation_digest=mutation.digest,
        )

    def acquire(self, mutation: LeaseMutation) -> LoadedLease:
        if mutation.operation != "acquire":
            raise ValueError("acquire requires an acquire mutation")
        try:
            current = self.load()
        except NotFound:
            if mutation.observed_fencing_epoch != 0:
                raise CoordinationConflict(
                    "missing lease after a committed fencing epoch is ambiguous"
                )
            record = self._record(
                mutation,
                proposed_epoch=1,
                lease_sequence=1,
                expires_at_utc_ns=mutation.requested_at_utc_ns + mutation.ttl_ns,
            )
            try:
                metadata = self.backend.put_if_absent(
                    self.layout.lease_key, record.canonical_bytes()
                )
            except InjectedTimeout:
                observed = self.load()
                if self._same_request(observed.record, mutation):
                    return observed
                raise
            return LoadedLease(record, metadata)

        if self._same_request(current.record, mutation):
            return current
        if (
            mutation.requested_at_utc_ns
            < current.record.expires_at_utc_ns + self.max_clock_skew_ns
        ):
            raise CoordinationConflict("lease is not takeover-eligible")
        if mutation.observed_fencing_epoch < current.record.proposed_fencing_epoch:
            # A candidate epoch can be abandoned, but the caller must first
            # replay current head rather than silently allocate from stale input.
            raise CoordinationConflict("acquire observed a stale fencing epoch")
        record = self._record(
            mutation,
            proposed_epoch=mutation.observed_fencing_epoch + 1,
            lease_sequence=current.record.lease_sequence + 1,
            expires_at_utc_ns=mutation.requested_at_utc_ns + mutation.ttl_ns,
        )
        return self._replace(current, mutation, record)

    def renew(self, mutation: LeaseMutation) -> LoadedLease:
        if mutation.operation != "renew":
            raise ValueError("renew requires a renew mutation")
        current = self.load()
        if self._same_request(current.record, mutation):
            return current
        if (
            current.record.owner_id != mutation.owner_id
            or current.record.owner_session_id != mutation.owner_session_id
            or current.record.proposed_fencing_epoch
            != mutation.observed_fencing_epoch
        ):
            raise CoordinationConflict("renew token differs from current lease")
        if mutation.requested_at_utc_ns >= current.record.expires_at_utc_ns:
            raise CoordinationConflict("expired lease cannot be renewed")
        record = self._record(
            mutation,
            proposed_epoch=current.record.proposed_fencing_epoch,
            lease_sequence=current.record.lease_sequence + 1,
            expires_at_utc_ns=mutation.requested_at_utc_ns + mutation.ttl_ns,
        )
        return self._replace(current, mutation, record)

    def release(self, mutation: LeaseMutation) -> LoadedLease:
        if mutation.operation != "release":
            raise ValueError("release requires a release mutation")
        current = self.load()
        if self._same_request(current.record, mutation):
            return current
        if (
            current.record.owner_id != mutation.owner_id
            or current.record.owner_session_id != mutation.owner_session_id
            or current.record.proposed_fencing_epoch
            != mutation.observed_fencing_epoch
        ):
            raise CoordinationConflict("release token differs from current lease")
        record = self._record(
            mutation,
            proposed_epoch=current.record.proposed_fencing_epoch,
            lease_sequence=current.record.lease_sequence + 1,
            expires_at_utc_ns=mutation.requested_at_utc_ns,
        )
        return self._replace(current, mutation, record)

    def _replace(
        self,
        current: LoadedLease,
        mutation: LeaseMutation,
        record: LeaseRecord,
    ) -> LoadedLease:
        try:
            metadata = self.backend.conditional_replace(
                self.layout.lease_key,
                expected_version=current.metadata.version,
                data=record.canonical_bytes(),
                request_id=mutation.request_id,
            )
        except InjectedTimeout:
            observed = self.load()
            if self._same_request(observed.record, mutation):
                return observed
            raise
        except PreconditionFailed as exc:
            observed = self.load()
            if self._same_request(observed.record, mutation):
                return observed
            raise CoordinationConflict("lease conditional mutation lost") from exc
        return LoadedLease(record, metadata)
