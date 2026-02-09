#!/usr/bin/env bash
set -euo pipefail

BASEDIR="$(cd "$(dirname "$0")" && pwd)"

if [[ $# -gt 0 ]]; then
  INPUT="$1"
  shift
else
  LIST=()
  while IFS= read -r file; do
    LIST+=("$file")
  done < <(ls "$BASEDIR/custom_checklists"/*.json 2>/dev/null || true)
  if [[ ${#LIST[@]} -eq 0 ]]; then
    echo "No JSON checklists found in $BASEDIR/custom_checklists/"
    exit 1
  fi
  echo "Select checklist:"
  select INPUT in "${LIST[@]}"; do
    if [[ -n "${INPUT:-}" ]]; then
      break
    fi
  done
fi

python3 "$BASEDIR/custom_checklist_generator.py" --test true --input "$INPUT" "$@"
