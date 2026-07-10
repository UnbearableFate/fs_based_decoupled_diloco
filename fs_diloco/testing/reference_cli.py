"""Run and replay deterministic reference trace suites."""

from __future__ import annotations

import argparse
import json

from fs_diloco.testing.model_checker import run_seeded_traces


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--start-seed", type=int, default=0)
    parser.add_argument("--steps", type=int, default=12)
    args = parser.parse_args()
    print(
        json.dumps(
            run_seeded_traces(
                count=args.count,
                start_seed=args.start_seed,
                steps=args.steps,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
