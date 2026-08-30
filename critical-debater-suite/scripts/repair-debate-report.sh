#!/bin/bash
# repair-debate-report.sh — One-shot repair for debate_report.md from final_report.json
set -euo pipefail

WORKSPACE="${1:?Usage: $0 <workspace_dir>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

REPORT_JSON="$WORKSPACE/reports/final_report.json"
REPORT_MD="$WORKSPACE/reports/debate_report.md"
AUDIT_FILE="$WORKSPACE/logs/audit_trail.jsonl"

if [ ! -f "$REPORT_JSON" ]; then
  echo "ERROR: missing final_report.json at $REPORT_JSON" >&2
  exit 1
fi

bash "$SCRIPT_DIR/validate-json.sh" "$REPORT_JSON" final_report
python3 "$SCRIPT_DIR/render-debate-report-from-json.py" "$WORKSPACE"
bash "$SCRIPT_DIR/validate-debate-report.sh" "$REPORT_MD"

if [ -f "$AUDIT_FILE" ]; then
  LINE=$(python3 - <<'PY' "$WORKSPACE"
import json
import sys
from datetime import datetime, timezone

workspace = sys.argv[1]
entry = {
    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "action": "report_repaired_from_json",
    "details": {
        "workspace": workspace,
        "script": "repair-debate-report.sh",
    },
}
print(json.dumps(entry, ensure_ascii=False))
PY
)
  bash "$SCRIPT_DIR/append-audit.sh" "$AUDIT_FILE" "$LINE"
fi

echo "OK: repaired $REPORT_MD"
