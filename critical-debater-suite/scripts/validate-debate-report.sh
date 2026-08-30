#!/bin/bash
# validate-debate-report.sh — Validate debate_report.md against Section 8/12/12a format
set -euo pipefail

FILE="${1:?Usage: $0 <debate_report.md>}"

if [ ! -f "$FILE" ]; then
  echo "ERROR: File not found: $FILE" >&2
  exit 1
fi

fail() {
  echo "ERROR: $1" >&2
  exit 1
}

# Ensure top-level structure appears in strict order.
required=(
  "# Debate Report:"
  "## Executive Summary"
  "## Decision Matrix"
  "## Verified Facts"
  "## Contested Points"
  "## Key Arguments by Round"
  "## Scenario Outlook"
  "## Watchlist"
  "## Evidence Inventory"
  "## Methodology"
  "---"
  "# Chinese Translation / 中文翻译"
)

prev=0
for marker in "${required[@]}"; do
  if [ "$marker" = "---" ]; then
    line=$(grep -n -x -- "$marker" "$FILE" | head -n 1 | cut -d: -f1 || true)
  else
    line=$(grep -n -F -- "$marker" "$FILE" | head -n 1 | cut -d: -f1 || true)
  fi
  if [ -z "$line" ]; then
    fail "Missing required marker: $marker"
  fi
  if [ "$line" -le "$prev" ]; then
    fail "Marker out of order: $marker"
  fi
  prev="$line"
done

# Validate required table headers.
grep -F "| Factor / 因素 | Assessment / 评估 | Confidence / 置信度 | Key Evidence / 关键证据 |" "$FILE" >/dev/null \
  || fail "Missing Decision Matrix table header"
grep -F "| # | Fact / 事实 | Sources / 来源 | Confidence / 置信度 |" "$FILE" >/dev/null \
  || fail "Missing Verified Facts table header"
grep -F "| Scenario / 情景 | Probability / 概率 | Impact / 影响 | Key Trigger / 关键触发 |" "$FILE" >/dev/null \
  || fail "Missing Scenario Outlook table header"
grep -F "| Item / 监控项 | Reversal Trigger / 反转触发 | Source / 监控来源 | Timeframe / 时间 |" "$FILE" >/dev/null \
  || fail "Missing Watchlist table header"
grep -F "| ID | Source | Type | Credibility | Track | Freshness | Discovered By | Round |" "$FILE" >/dev/null \
  || fail "Missing Evidence Inventory table header"

# Validate contested point structure blocks.
grep -F "**Status / 状态**" "$FILE" >/dev/null || fail "Missing contested-point field: Status"
grep -F "**Pro Position / 正方立场**" "$FILE" >/dev/null || fail "Missing contested-point field: Pro Position"
grep -F "**Con Position / 反方立场**" "$FILE" >/dev/null || fail "Missing contested-point field: Con Position"
grep -F "**Key Rebuttals / 关键反驳**" "$FILE" >/dev/null || fail "Missing contested-point field: Key Rebuttals"
grep -F "**Judge Assessment / 裁判评估**" "$FILE" >/dev/null || fail "Missing contested-point field: Judge Assessment"

# Validate conclusion profile section exists.
grep -E "^### Conclusion:" "$FILE" >/dev/null || fail "Missing Conclusion profile section"
grep -F "| Dimension / 维度 | Value / 值 | Rationale / 依据 |" "$FILE" >/dev/null \
  || fail "Missing Conclusion profile table header"

# Ensure Chinese translation section mirrors enough structure (at least 9 second-level sections).
zh_line=$(grep -n -F "# Chinese Translation / 中文翻译" "$FILE" | head -n 1 | cut -d: -f1)
post_zh_sections=$(tail -n +"$zh_line" "$FILE" | grep -E '^## ' | wc -l | tr -d ' ')
if [ "$post_zh_sections" -lt 9 ]; then
  fail "Chinese translation block is incomplete: found $post_zh_sections sections (need >=9)"
fi

echo "OK: $FILE matches Section 8 debate_report.md format"
