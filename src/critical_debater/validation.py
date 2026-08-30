"""Deterministic output validation.

Python port of ``validate-json.sh`` (data-contract schema checks) and
``validate-debate-report.sh`` (Section 8 report format checks). Ported so the
v3 graph has no bash/jq dependency and tests stay hermetic; semantics match
the v2 scripts.
"""

from __future__ import annotations

import json
import os
from typing import Optional

# Required top-level (or first-element) fields per schema type.
REQUIRED_FIELDS: dict[str, list[str]] = {
    "config": ["topic", "round_count", "depth", "mode", "evidence_refresh", "language", "current_round", "status", "created_at"],
    "evidence_item": ["evidence_id", "source_type", "url", "snippet", "hash", "credibility_tier", "freshness_status", "evidence_track"],
    "claim_item": ["claim_id", "round", "speaker", "claim_type", "claim_text", "evidence_ids", "status"],
    "judge_ruling": ["round", "verification_results", "mandatory_response_points", "round_summary"],
    "final_report": ["topic", "total_rounds", "verified_facts", "probable_conclusions", "contested_points", "to_verify", "scenario_outlook", "watchlist_24h"],
    "pro_turn": ["round", "side", "arguments", "rebuttals"],
    "con_turn": ["round", "side", "arguments", "rebuttals"],
}

REASONING_CHAIN_ELEMENTS = (
    "observed_facts",
    "mechanism",
    "scenario_implication",
    "trigger_conditions",
    "falsification_conditions",
)

REPORT_SECTION_MARKERS = [
    "# Debate Report:",
    "## Executive Summary",
    "## Decision Matrix",
    "## Verified Facts",
    "## Contested Points",
    "## Key Arguments by Round",
    "## Scenario Outlook",
    "## Watchlist",
    "## Evidence Inventory",
    "## Methodology",
    "---",
    "# Chinese Translation / 中文翻译",
]

REPORT_TABLE_HEADERS = [
    "| Factor / 因素 | Assessment / 评估 | Confidence / 置信度 | Key Evidence / 关键证据 |",
    "| # | Fact / 事实 | Sources / 来源 | Confidence / 置信度 |",
    "| Scenario / 情景 | Probability / 概率 | Impact / 影响 | Key Trigger / 关键触发 |",
    "| Item / 监控项 | Reversal Trigger / 反转触发 | Source / 监控来源 | Timeframe / 时间 |",
    "| ID | Source | Type | Credibility | Track | Freshness | Discovered By | Round |",
]

REPORT_CONTESTED_FIELDS = [
    "**Status / 状态**",
    "**Pro Position / 正方立场**",
    "**Con Position / 反方立场**",
    "**Key Rebuttals / 关键反驳**",
    "**Judge Assessment / 裁判评估**",
]

CONCLUSION_SECTION_MARKER = "### Conclusion:"
CONCLUSION_TABLE_HEADER = "| Dimension / 维度 | Value / 值 | Rationale / 依据 |"
CHINESE_SECTION_MARKER = "# Chinese Translation / 中文翻译"


def _validate_contract(data, schema_type: str) -> list[str]:
    errors: list[str] = []
    if schema_type not in REQUIRED_FIELDS:
        return [f"Unknown schema type: {schema_type}"]

    is_array = isinstance(data, list)
    if is_array and len(data) == 0:
        # jq-based check only inspects fields when the array has elements.
        return errors

    target = data[0] if is_array else data
    if not isinstance(target, dict):
        return [f"Unexpected JSON shape in {schema_type} payload"]

    for field in REQUIRED_FIELDS[schema_type]:
        if field not in target:
            errors.append(f"Missing required field '{field}' (schema: {schema_type})")

    if schema_type in ("pro_turn", "con_turn"):
        arguments = target.get("arguments") or []
        if isinstance(arguments, list):
            for idx, argument in enumerate(arguments):
                chain = (argument or {}).get("reasoning_chain")
                if not isinstance(chain, dict):
                    errors.append(f"arguments[{idx}].reasoning_chain missing in {schema_type}")
                    continue
                for elem in REASONING_CHAIN_ELEMENTS:
                    if elem not in chain:
                        errors.append(f"arguments[{idx}].reasoning_chain missing '{elem}' in {schema_type}")

    if schema_type == "judge_ruling":
        hwa = target.get("historical_wisdom_assessment")
        if hwa is not None:
            if not isinstance(hwa, list):
                errors.append("historical_wisdom_assessment must be an array in judge_ruling")
            else:
                for idx, item in enumerate(hwa):
                    if not isinstance(item, dict):
                        errors.append(f"historical_wisdom_assessment[{idx}] must be an object")
                        continue
                    if "relevance_grade" not in item:
                        errors.append(f"historical_wisdom_assessment[{idx}] missing 'relevance_grade'")
                    if "honesty_grade" not in item:
                        errors.append(f"historical_wisdom_assessment[{idx}] missing 'honesty_grade'")

    return errors


def validate_json_file(filepath: str, schema_type: str) -> tuple[bool, str]:
    """Validate a JSON file against a data-contract schema.

    Returns (ok, message); message mirrors v2 script output.
    """
    if not os.path.exists(filepath):
        return False, f"ERROR: File not found: {filepath}"
    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return False, f"ERROR: Invalid JSON in {filepath}: {e}"

    errors = _validate_contract(data, schema_type)
    if errors:
        return False, f"FAILED: {len(errors)} problem(s) in {filepath} (schema: {schema_type}): " + "; ".join(errors)
    return True, f"OK: {filepath} validates against {schema_type}"


def _marker_line(lines: list[str], marker: str) -> Optional[int]:
    exact = marker == "---"
    for idx, line in enumerate(lines, start=1):
        if exact:
            if line.strip() == marker:
                return idx
        elif marker in line:
            return idx
    return None


def validate_debate_report_text(text: str) -> list[str]:
    lines = text.splitlines()
    errors: list[str] = []

    prev = 0
    for marker in REPORT_SECTION_MARKERS:
        line_no = _marker_line(lines, marker)
        if line_no is None:
            errors.append(f"Missing required marker: {marker}")
            continue
        if line_no <= prev:
            errors.append(f"Marker out of order: {marker}")
            break
        prev = line_no

    for header in REPORT_TABLE_HEADERS:
        if not any(header in line for line in lines):
            errors.append(f"Missing required table header: {header}")

    for field in REPORT_CONTESTED_FIELDS:
        if not any(field in line for line in lines):
            errors.append(f"Missing contested-point field: {field}")

    if not any(line.startswith(CONCLUSION_SECTION_MARKER) for line in lines):
        errors.append("Missing Conclusion profile section")
    if not any(CONCLUSION_TABLE_HEADER in line for line in lines):
        errors.append("Missing Conclusion profile table header")

    zh_line = next((i for i, line in enumerate(lines, start=1) if CHINESE_SECTION_MARKER in line), None)
    if zh_line is not None:
        zh_sections = sum(1 for line in lines[zh_line:] if line.startswith("## "))
        if zh_sections < 9:
            errors.append(
                f"Chinese translation block is incomplete: found {zh_sections} sections (need >=9)"
            )
    return errors


def validate_debate_report_file(filepath: str) -> tuple[bool, str]:
    if not os.path.exists(filepath):
        return False, f"ERROR: File not found: {filepath}"
    with open(filepath, encoding="utf-8") as f:
        errors = validate_debate_report_text(f.read())
    if errors:
        return False, "ERROR: " + "; ".join(errors)
    return True, f"OK: {filepath} matches Section 8 debate_report.md format"
