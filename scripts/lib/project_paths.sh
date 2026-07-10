#!/usr/bin/env bash

require_project_paths() {
  local project_root candidate resolved
  project_root=$(realpath -e -- "$1")
  shift
  for candidate in "$@"; do
    resolved=$(realpath -m -- "$candidate")
    case "$resolved" in
      "$project_root" | "$project_root"/*) ;;
      *)
        echo "Refusing generated path outside project root $project_root: $resolved" >&2
        return 2
        ;;
    esac
  done
}
