from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "scripts/agent/capture_baseline.py"


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=path, check=True, stdout=subprocess.PIPE)


def _make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "critical.txt").write_text("baseline\n")
    _git(root, "add", "critical.txt")
    _git(root, "commit", "-qm", "baseline")
    return root


def test_capture_binds_git_dirty_state_and_detects_digest_drift(tmp_path):
    root = _make_repo(tmp_path)
    output = root / "manifest.json"
    command = [
        sys.executable,
        str(CAPTURE),
        "--root",
        str(root),
        "--critical-path",
        "critical.txt",
        "--output",
        str(output),
    ]
    assert subprocess.run(command).returncode == 0
    payload = json.loads(output.read_text())
    assert payload["git"]["dirty"] is False
    assert payload["files"][0]["path"] == "critical.txt"

    (root / "critical.txt").write_text("changed\n")
    verify = subprocess.run(
        [sys.executable, str(CAPTURE), "--root", str(root), "--verify", str(output)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert verify.returncode != 0
    assert "verification failed" in verify.stderr


def test_capture_rejects_dirty_or_wrong_branch_when_required(tmp_path):
    root = _make_repo(tmp_path)
    (root / "critical.txt").write_text("dirty\n")
    result = subprocess.run(
        [
            sys.executable,
            str(CAPTURE),
            "--root",
            str(root),
            "--critical-path",
            "critical.txt",
            "--require-clean",
        ]
    )
    assert result.returncode != 0


def test_capture_can_freeze_committed_files_while_reporting_dirty_overlay(tmp_path):
    root = _make_repo(tmp_path)
    baseline_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    (root / "critical.txt").write_text("dirty overlay\n")
    output = root / "committed.json"
    result = subprocess.run(
        [
            sys.executable,
            str(CAPTURE),
            "--root",
            str(root),
            "--critical-path",
            "critical.txt",
            "--source-commit",
            baseline_commit,
            "--output",
            str(output),
        ]
    )
    assert result.returncode == 0
    payload = json.loads(output.read_text())
    assert payload["git"]["dirty"] is True
    assert payload["file_source"] == {"kind": "git_commit", "commit": baseline_commit}
    assert payload["files"][0]["sha256"] != __import__("hashlib").sha256(
        b"dirty overlay\n"
    ).hexdigest()

    result = subprocess.run(
        [
            sys.executable,
            str(CAPTURE),
            "--root",
            str(root),
            "--critical-path",
            "critical.txt",
            "--expect-branch",
            "definitely-not-current",
        ]
    )
    assert result.returncode != 0
