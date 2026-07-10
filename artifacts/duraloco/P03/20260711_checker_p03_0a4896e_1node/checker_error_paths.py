from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import sys

from fs_diloco.storage import PosixStorageBackend, StorageIOError
import fs_diloco.storage.posix as posix_module


def expected_retryable(code: int) -> bool:
    return code in {errno.EIO, errno.ESTALE}


def classify(exc: BaseException) -> dict[str, object]:
    return {
        "type": type(exc).__name__,
        "errno": getattr(exc, "errno", None),
        "retryable": getattr(exc, "retryable", None),
        "typed_storage_io": isinstance(exc, StorageIOError),
    }


def main() -> int:
    work = Path(sys.argv[1])
    output = Path(sys.argv[2])
    target_commit = (
        sys.argv[3]
        if len(sys.argv) > 3
        else "0a4896e38748cbe33aaefe0d51451df1496b0db7"
    )
    work.mkdir(parents=True, exist_ok=True)
    backend = PosixStorageBackend(work / "store")
    initial = backend.put_if_absent("control/head", b"zero")
    observations: dict[str, object] = {}
    failures: list[str] = []

    original_mkstemp = posix_module.tempfile.mkstemp
    for code in (errno.EIO, errno.ESTALE, errno.EACCES, errno.ENOSPC, errno.EDQUOT):
        def fail_mkstemp(*args, _code=code, **kwargs):
            raise OSError(_code, os.strerror(_code))

        posix_module.tempfile.mkstemp = fail_mkstemp
        try:
            backend.conditional_replace(
                "control/head",
                expected_version=initial.version,
                data=b"one",
                request_id=f"mkstemp-{code}",
            )
        except BaseException as exc:
            observed = classify(exc)
        else:
            observed = {"type": "NO_EXCEPTION"}
        finally:
            posix_module.tempfile.mkstemp = original_mkstemp
        observations[f"mkstemp_errno_{code}"] = observed
        if not (
            observed.get("typed_storage_io")
            and observed.get("errno") == code
            and observed.get("retryable") is expected_retryable(code)
        ):
            failures.append(f"mkstemp errno {code} escaped typed translation")

    original_flock = posix_module.fcntl.flock
    for code in (errno.EIO, errno.ESTALE, errno.EACCES):
        def fail_exclusive(descriptor, operation, _code=code):
            if operation & posix_module.fcntl.LOCK_EX:
                raise OSError(_code, os.strerror(_code))
            return original_flock(descriptor, operation)

        posix_module.fcntl.flock = fail_exclusive
        try:
            backend.conditional_replace(
                "control/head",
                expected_version=initial.version,
                data=b"one",
                request_id=f"flock-{code}",
            )
        except BaseException as exc:
            observed = classify(exc)
        else:
            observed = {"type": "NO_EXCEPTION"}
        finally:
            posix_module.fcntl.flock = original_flock
        observations[f"flock_errno_{code}"] = observed
        if not (
            observed.get("typed_storage_io")
            and observed.get("errno") == code
            and observed.get("retryable") is expected_retryable(code)
        ):
            failures.append(f"flock errno {code} escaped typed translation")

    readonly = backend.root / "readonly"
    readonly.mkdir()
    readonly.chmod(0o555)
    try:
        backend.put_immutable("readonly/object", b"value")
    except BaseException as exc:
        observed = classify(exc)
    else:
        observed = {"type": "NO_EXCEPTION"}
    finally:
        readonly.chmod(0o755)
    observations["real_readonly_parent"] = observed
    if not (
        observed.get("typed_storage_io")
        and observed.get("errno") in {errno.EACCES, errno.EPERM}
        and observed.get("retryable") is False
    ):
        failures.append("real read-only parent error escaped typed translation")

    report = {
        "target_commit": target_commit,
        "hostname": os.uname().nodename,
        "observations": observations,
        "required_failures": failures,
    }
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
