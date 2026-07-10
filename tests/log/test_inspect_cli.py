from __future__ import annotations

import json

from fs_diloco.log import replay_log
from fs_diloco.log.inspect_cli import main
from fs_diloco.storage import PosixStorageBackend

from .helpers import initialize, proposal


def test_cli_verifies_and_localizes_the_first_corrupt_commit(tmp_path):
    root = tmp_path / "store"
    log = initialize(PosixStorageBackend(root), "inspect-cli")
    item = proposal(log, learner="learner-a", sequence=1)
    log.commit_transition(fragment_id=0, selected_proposal_ids=(item.proposal_id,))
    output = tmp_path / "verify.json"
    assert main(
        [
            "verify",
            "--root",
            str(root),
            "--run-id",
            "inspect-cli",
            "--output",
            str(output),
        ]
    ) == 0
    assert json.loads(output.read_text())["commit_seq"] == 1

    replay = replay_log(log)
    commit = replay.commits[0]
    physical = root / log.layout.commit_key(commit.commit_seq, commit.commit_id)
    corrupted = bytearray(physical.read_bytes())
    corrupted[-1] ^= 1
    physical.write_bytes(corrupted)
    assert main(
        [
            "verify",
            "--root",
            str(root),
            "--run-id",
            "inspect-cli",
            "--output",
            str(output),
        ]
    ) == 2
    failure = json.loads(output.read_text())
    assert failure["status"] == "FAIL"
    assert failure["first_bad_commit_seq"] == 1
