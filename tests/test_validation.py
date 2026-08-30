"""Unit tests for the ported validation module."""

from __future__ import annotations

import json
import os

from critical_debater.validation import (
    validate_debate_report_file,
    validate_debate_report_text,
    validate_json_file,
)

from fake_agent import valid_judge_ruling, valid_turn

REPORT_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "debate_report.md")


def _write(tmp_path, name, data):
    path = str(tmp_path / name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def test_valid_pro_turn(tmp_path):
    path = _write(tmp_path, "pro_turn.json", valid_turn(1, "pro"))
    ok, msg = validate_json_file(path, "pro_turn")
    assert ok, msg


def test_turn_missing_reasoning_chain_element(tmp_path):
    turn = valid_turn(1, "pro")
    del turn["arguments"][0]["reasoning_chain"]["mechanism"]
    path = _write(tmp_path, "pro_turn.json", turn)
    ok, msg = validate_json_file(path, "pro_turn")
    assert not ok
    assert "mechanism" in msg


def test_judge_ruling_historical_wisdom_checks(tmp_path):
    ruling = valid_judge_ruling(1)
    ruling["historical_wisdom_assessment"] = [{"side": "pro"}]
    path = _write(tmp_path, "judge_ruling.json", ruling)
    ok, msg = validate_json_file(path, "judge_ruling")
    assert not ok
    assert "relevance_grade" in msg and "honesty_grade" in msg


def test_final_report_missing_field(tmp_path):
    report = {"topic": "t", "total_rounds": 1}
    path = _write(tmp_path, "final_report.json", report)
    ok, msg = validate_json_file(path, "final_report")
    assert not ok
    assert "verified_facts" in msg


def test_invalid_json(tmp_path):
    path = str(tmp_path / "bad.json")
    with open(path, "w") as f:
        f.write("{not json")
    ok, msg = validate_json_file(path, "config")
    assert not ok
    assert "Invalid JSON" in msg


def test_unknown_schema(tmp_path):
    path = _write(tmp_path, "x.json", {})
    ok, msg = validate_json_file(path, "nope")
    assert not ok
    assert "Unknown schema" in msg


def test_report_fixture_passes():
    ok, msg = validate_debate_report_file(REPORT_FIXTURE)
    assert ok, msg


def test_report_missing_chinese_sections():
    with open(REPORT_FIXTURE, encoding="utf-8") as f:
        text = f.read()
    # Keep the Chinese marker line itself but drop its sections.
    marker = "# Chinese Translation / 中文翻译"
    head, _, _ = text.partition(marker)
    truncated = head + marker + "\n"
    errors = validate_debate_report_text(truncated)
    assert any("Chinese translation block is incomplete" in e for e in errors)


def test_report_marker_out_of_order():
    with open(REPORT_FIXTURE, encoding="utf-8") as f:
        text = f.read()
    # Move Executive Summary below Methodology → ordering violation.
    reordered = text.replace("## Executive Summary", "##zzz", 1)
    reordered = reordered.replace("## Methodology", "## Executive Summary", 1)
    errors = validate_debate_report_text(reordered)
    assert any("out of order" in e for e in errors)
