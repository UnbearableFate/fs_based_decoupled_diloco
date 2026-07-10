"""Inspect a Protocol v2 or legacy v1 JSON manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .manifests import load_manifest
from .v1_adapter import parse_v1_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--v1", action="store_true", help="parse as a read-only legacy manifest")
    args = parser.parse_args()
    if args.v1:
        value = parse_v1_manifest(json.loads(args.manifest.read_text(encoding="utf-8")))
        print(json.dumps(value.__dict__, indent=2, sort_keys=True))
    else:
        value = load_manifest(args.manifest)
        print(json.dumps(value.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
