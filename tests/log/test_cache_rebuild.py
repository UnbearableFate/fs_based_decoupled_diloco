from __future__ import annotations

import pytest

from fs_diloco.log import VerificationError, load_cache, rebuild_cache, verify_cache
from fs_diloco.storage import InMemoryStorageBackend

from .helpers import initialize, proposal


def test_deleted_and_corrupt_sqlite_cache_rebuilds_exactly(tmp_path):
    log = initialize(InMemoryStorageBackend(), "cache-rebuild")
    for sequence in range(1, 4):
        item = proposal(log, learner=f"learner-{sequence}", sequence=sequence)
        log.commit_transition(fragment_id=0, selected_proposal_ids=(item.proposal_id,))
    path = tmp_path / "derived" / "consumption.sqlite"
    first = rebuild_cache(log, path)
    assert verify_cache(log, path) == first
    path.unlink()
    second = rebuild_cache(log, path)
    assert second == first
    path.write_bytes(b"not a sqlite database")
    with pytest.raises(VerificationError):
        load_cache(path)
    third = rebuild_cache(log, path)
    assert third == first
