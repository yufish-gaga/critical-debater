#!/bin/bash
# validate-json.sh — Validate JSON files against data contract schemas
set -euo pipefail

FILE="${1:?Usage: $0 <file> <schema_type>}"
SCHEMA="${2:?Usage: $0 <file> <schema_type>}"

if [ ! -f "$FILE" ]; then
  echo "ERROR: File not found: $FILE" >&2
  exit 1
fi

if ! jq empty "$FILE" 2>/dev/null; then
  echo "ERROR: Invalid JSON in $FILE" >&2
  exit 1
fi

case "$SCHEMA" in
  config)
    REQUIRED='["topic", "round_count", "depth", "mode", "evidence_refresh", "language", "current_round", "status", "created_at"]'
    ;;
  evidence_item)
    REQUIRED='["evidence_id", "source_type", "url", "snippet", "hash", "credibility_tier", "freshness_status", "evidence_track"]'
    ;;
  claim_item)
    REQUIRED='["claim_id", "round", "speaker", "claim_type", "claim_text", "evidence_ids", "status"]'
    ;;
  judge_ruling)
    REQUIRED='["round", "verification_results", "mandatory_response_points", "round_summary"]'
    DEEP_CHECK="judge_ruling"
    ;;
  final_report)
    REQUIRED='["topic", "total_rounds", "verified_facts", "probable_conclusions", "contested_points", "to_verify", "scenario_outlook", "watchlist_24h"]'
    ;;
  pro_turn|con_turn)
    REQUIRED='["round", "side", "arguments", "rebuttals"]'
    DEEP_CHECK="reasoning_chain"
    ;;
  *)
    echo "ERROR: Unknown schema type: $SCHEMA" >&2
    exit 1
    ;;
esac

ERRORS=0
for field in $(echo "$REQUIRED" | jq -r '.[]'); do
  IS_ARRAY=$(jq 'type == "array"' "$FILE")
  if [ "$IS_ARRAY" = "true" ]; then
    HAS_ELEMENTS=$(jq 'length > 0' "$FILE")
    if [ "$HAS_ELEMENTS" = "true" ]; then
      HAS_FIELD=$(jq --arg f "$field" '.[0] | has($f)' "$FILE")
      if [ "$HAS_FIELD" = "false" ]; then
        echo "ERROR: Missing required field '$field' in first element of $FILE" >&2
        ERRORS=$((ERRORS + 1))
      fi
    fi
  else
    HAS_FIELD=$(jq --arg f "$field" 'has($f)' "$FILE")
    if [ "$HAS_FIELD" = "false" ]; then
      echo "ERROR: Missing required field '$field' in $FILE" >&2
      ERRORS=$((ERRORS + 1))
    fi
  fi
done

# Deep check: reasoning_chain 5 elements in arguments
if [ -n "${DEEP_CHECK:-}" ] && [ "$DEEP_CHECK" = "reasoning_chain" ]; then
  ARG_COUNT=$(jq '.arguments | length' "$FILE" 2>/dev/null || echo 0)
  if [ "$ARG_COUNT" -gt 0 ] 2>/dev/null; then
    for idx in $(seq 0 $((ARG_COUNT - 1))); do
      for elem in observed_facts mechanism scenario_implication trigger_conditions falsification_conditions; do
        HAS=$(jq --argjson i "$idx" --arg e "$elem" '.arguments[$i].reasoning_chain | has($e)' "$FILE" 2>/dev/null)
        if [ "$HAS" != "true" ]; then
          echo "ERROR: arguments[$idx].reasoning_chain missing '$elem' in $FILE" >&2
          ERRORS=$((ERRORS + 1))
        fi
      done
    done
  fi
fi

# Deep check: judge_ruling historical_wisdom_assessment key names.
if [ -n "${DEEP_CHECK:-}" ] && [ "$DEEP_CHECK" = "judge_ruling" ]; then
  HAS_HWA=$(jq 'has("historical_wisdom_assessment")' "$FILE")
  if [ "$HAS_HWA" = "true" ]; then
    HWA_IS_ARRAY=$(jq '.historical_wisdom_assessment | type == "array"' "$FILE")
    if [ "$HWA_IS_ARRAY" != "true" ]; then
      echo "ERROR: historical_wisdom_assessment must be an array in $FILE" >&2
      ERRORS=$((ERRORS + 1))
    else
      HWA_COUNT=$(jq '.historical_wisdom_assessment | length' "$FILE")
      if [ "$HWA_COUNT" -gt 0 ] 2>/dev/null; then
        for idx in $(seq 0 $((HWA_COUNT - 1))); do
          HAS_REL=$(jq --argjson i "$idx" '.historical_wisdom_assessment[$i] | has("relevance_grade")' "$FILE")
          HAS_HON=$(jq --argjson i "$idx" '.historical_wisdom_assessment[$i] | has("honesty_grade")' "$FILE")
          if [ "$HAS_REL" != "true" ]; then
            echo "ERROR: historical_wisdom_assessment[$idx] missing 'relevance_grade' in $FILE" >&2
            ERRORS=$((ERRORS + 1))
          fi
          if [ "$HAS_HON" != "true" ]; then
            echo "ERROR: historical_wisdom_assessment[$idx] missing 'honesty_grade' in $FILE" >&2
            ERRORS=$((ERRORS + 1))
          fi
        done
      fi
    fi
  fi
fi

if [ $ERRORS -gt 0 ]; then
  echo "FAILED: $ERRORS missing field(s) in $FILE (schema: $SCHEMA)" >&2
  exit 1
fi

echo "OK: $FILE validates against $SCHEMA"
exit 0
