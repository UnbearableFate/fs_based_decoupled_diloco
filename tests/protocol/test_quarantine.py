from __future__ import annotations

import pytest

from fs_diloco.protocol.errors import ErrorCategory, ProtocolError
from fs_diloco.protocol.quarantine import QuarantineRegistry


def test_repeated_quarantine_is_idempotent_and_auditable():
    registry = QuarantineRegistry()
    error = ProtocolError("PAYLOAD_HASH", "bad hash")
    first = registry.record(observed_identity="p-test", content_sha256="a" * 64, error=error)
    second = registry.record(observed_identity="p-test", content_sha256="a" * 64, error=error)
    assert first == second
    assert len(registry.records) == 1
    assert first.category == "quarantine"


def test_conflicting_identity_is_fatal():
    registry = QuarantineRegistry()
    error = ProtocolError("PAYLOAD_HASH", "bad hash")
    registry.record(observed_identity="p-test", content_sha256="a" * 64, error=error)
    with pytest.raises(ProtocolError) as caught:
        registry.record(observed_identity="p-test", content_sha256="b" * 64, error=error)
    assert caught.value.category == ErrorCategory.FATAL
