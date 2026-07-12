from __future__ import annotations

import inspect

import fs_diloco.cli as training_cli
import fs_diloco.lifecycle_cli as lifecycle_cli


def test_lifecycle_cli_is_a_distinct_module_and_gc_defaults_to_mark_only():
    assert lifecycle_cli is not training_cli
    assert lifecycle_cli.main is not training_cli.main
    args = lifecycle_cli.parse_args(
        [
            "--storage-root",
            "/tmp/store",
            "--run-id",
            "run-a",
            "gc-mark",
        ]
    )
    assert args.command == "gc-mark"
    assert not hasattr(args, "approval_token")
    source = inspect.getsource(lifecycle_cli)
    assert "fs_diloco.cli" in source
    assert 'choices=("synthetic",)' in source


def test_gc_apply_requires_separate_mark_token_namespace_and_request():
    args = lifecycle_cli.parse_args(
        [
            "--storage-root",
            "/tmp/store",
            "--run-id",
            "synthetic-run",
            "gc-apply",
            "--mark",
            "mark.json",
            "--approval-token",
            "token",
            "--namespace",
            "synthetic",
            "--request-id",
            "request-a",
        ]
    )
    assert args.command == "gc-apply"
    assert args.namespace == "synthetic"
