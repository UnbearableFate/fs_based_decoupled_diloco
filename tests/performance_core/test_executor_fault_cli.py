from fs_diloco.distributed_syncer.cli import parse_args


def test_executor_controlled_fault_flag_is_explicit_and_default_off():
    common = [
        "executor",
        "--config",
        "config.yaml",
        "--run-id",
        "run",
        "--shared-root",
        "root",
        "--num-learners",
        "8",
        "--member-id",
        "member-000",
        "--executor-id",
        "executor-000",
        "--executor-session-id",
        "session",
    ]
    assert parse_args(common).inject_error_before_first_attempt is False
    assert parse_args(common + ["--inject-error-before-first-attempt"]).inject_error_before_first_attempt
