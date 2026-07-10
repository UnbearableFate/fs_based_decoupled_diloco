from __future__ import annotations

from fs_diloco.log import replay_log
from fs_diloco.storage import InMemoryStorageBackend, PosixStorageBackend

from .helpers import initialize, proposal


def _build(backend, run_id: str):
    log = initialize(backend, run_id)
    observed = [replay_log(log).committed_state_digest]
    for sequence in range(1, 6):
        item = proposal(
            log,
            learner=f"learner-{sequence}",
            sequence=sequence,
            fragment_id=(sequence - 1) % 2,
            values=(float(sequence), -float(sequence) / 2.0),
        )
        log.commit_transition(
            fragment_id=item.fragment_id,
            selected_proposal_ids=(item.proposal_id,),
        )
        replay = replay_log(log)
        observed.append(replay.committed_state_digest)
        assert list(replay.prefix_digests) == observed
    return replay_log(log)


def test_every_prefix_replays_and_memory_matches_posix(tmp_path):
    memory = _build(InMemoryStorageBackend(), "backend-equality")
    posix = _build(PosixStorageBackend(tmp_path / "store"), "backend-equality")
    assert posix.prefix_digests == memory.prefix_digests
    assert posix.committed_state_digest == memory.committed_state_digest
    assert posix.head_frontier.to_dict() == memory.head_frontier.to_dict()
