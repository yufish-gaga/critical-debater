#!/bin/bash
# check-compat.sh — Validate core/adapters sync and compatibility constraints.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

REPORT_PATH=""
if [ "${1:-}" = "--report" ]; then
  REPORT_PATH="${2:-}"
  if [ -z "$REPORT_PATH" ]; then
    echo "ERROR: Usage: $0 [--report <debate_report.md>]" >&2
    exit 1
  fi
fi

python3 "$SCRIPT_DIR/build-skill-adapters.py" --check

for target in claude-code codex openclaw; do
  file="$ROOT_DIR/adapters/$target/SKILL.md"
  [ -f "$file" ] || { echo "ERROR: missing adapter file: $file" >&2; exit 1; }

  grep -q '^---' "$file" || { echo "ERROR: missing frontmatter in $file" >&2; exit 1; }
  grep -q '^name: critical-debater-suite$' "$file" || { echo "ERROR: missing name field in $file" >&2; exit 1; }
  grep -q '^description:' "$file" || { echo "ERROR: missing description field in $file" >&2; exit 1; }
  grep -q '^license:' "$file" || { echo "ERROR: missing license field in $file" >&2; exit 1; }
  grep -q '^compatibility:' "$file" || { echo "ERROR: missing compatibility field in $file" >&2; exit 1; }
  grep -q '^metadata:' "$file" || { echo "ERROR: missing metadata field in $file" >&2; exit 1; }

  # Reject actual traversal-style path entries, but allow explanatory text like
  # "No ../ traversal".
  if rg -n '^[[:space:]-]*`?\.\./' "$file" >/dev/null; then
    echo "ERROR: traversal-style relative path entry found in $file" >&2
    exit 1
  fi

  grep -Fq 'capabilities/final-synthesis.md' "$file" || {
    echo "ERROR: missing final-synthesis route in $file" >&2
    exit 1
  }

done

if [ -n "$REPORT_PATH" ]; then
  bash "$SCRIPT_DIR/validate-debate-report.sh" "$REPORT_PATH"
fi

echo "OK: compatibility checks passed"
