#!/bin/bash
# append-audit.sh — Atomically append a JSONL line to audit trail
set -euo pipefail

AUDIT_FILE="${1:?Usage: $0 <audit_file> <json_line>}"
JSON_LINE="${2:?Usage: $0 <audit_file> <json_line>}"

if ! echo "$JSON_LINE" | jq empty 2>/dev/null; then
  echo "ERROR: Invalid JSON: $JSON_LINE" >&2
  exit 1
fi

touch "$AUDIT_FILE"

ACTION=$(echo "$JSON_LINE" | jq -r '.action')
KEY=$(echo "$JSON_LINE" | jq -c '
  if (.action == "pro_turn_complete" or .action == "con_turn_complete" or .action == "judge_ruling_complete")
  then {"action": .action, "round": (.details.round // null)}
  else {"action": .action, "details": (.details // {})}
  end
')

# Idempotent dedupe:
# - Lifecycle actions dedupe by action+round
# - Other actions dedupe by action+details
if [ -s "$AUDIT_FILE" ]; then
  if jq -c '
      if (.action == "pro_turn_complete" or .action == "con_turn_complete" or .action == "judge_ruling_complete")
      then {"action": .action, "round": (.details.round // null)}
      else {"action": .action, "details": (.details // {})}
      end
    ' "$AUDIT_FILE" | grep -Fxq "$KEY"; then
    # Duplicate entry already exists; treat as success without appending.
    exit 0
  fi
fi

TEMP_FILE=$(mktemp "${AUDIT_FILE}.XXXXXX")
cp "$AUDIT_FILE" "$TEMP_FILE"
echo "$JSON_LINE" >> "$TEMP_FILE"
mv "$TEMP_FILE" "$AUDIT_FILE"
