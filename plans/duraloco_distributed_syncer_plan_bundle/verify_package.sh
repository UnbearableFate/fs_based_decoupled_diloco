#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$ROOT/repo_patch/plans/duraloco/codex/DuraLoCo_Codex_Loop_Plans"
python3 "$ROOT/tools/build_duraloco_master.py" --bundle "$BUNDLE" --lint
python3 "$ROOT/tools/build_duraloco_master.py" --bundle "$BUNDLE" --check
(
  cd "$BUNDLE"
  sha256sum -c SHA256SUMS.txt
)
(
  cd "$ROOT"
  sha256sum -c PACKAGE_SHA256SUMS.txt
)
echo "DuraLoCo plan rewrite bundle: verification PASS"
