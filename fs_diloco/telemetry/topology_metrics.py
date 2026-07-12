"""Resource/topology evidence helpers used by P08 launchers and reports."""

from __future__ import annotations

from pathlib import Path
import os
import resource


def current_resource_placement() -> dict[str, object]:
    cpus = sorted(os.sched_getaffinity(0))
    mems = None
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("Mems_allowed_list:"):
                mems = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return {
        "cpu_affinity": cpus,
        "numa_mems_allowed_list": mems,
        "rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
    }
