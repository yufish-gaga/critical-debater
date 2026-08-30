"""Tests for the eight-dimension quality assessment (v3 Phase 5)."""

from __future__ import annotations

import os

from critical_debater.quality.assessor import (
    DIMENSIONS,
    DebateQualityAssessor,
    assess_debate_quality,
    load_quality_weights,
)
from critical_debater.workspace import read_json

from fake_agent import _write_json, evidence_item, valid_judge_ruling, valid_turn


def _seed_workspace(workspace: str, rounds: int = 1) -> None:
    _write_json(os.path.join(workspace, "evidence", "evidence_store.json"),
                [evidence_item(i) for i in range(1, 4)])
    for round_num in range(1, rounds + 1):
        rdir = os.path.join(workspace, "rounds", f"round_{round_num}")
        _write_json(os.path.join(rdir, "pro_turn.json"), valid_turn(round_num, "pro"))
        _write_json(os.path.join(rdir, "con_turn.json"), valid_turn(round_num, "con"))
        _write_json(os.path.join(rdir, "judge_ruling.json"), valid_judge_ruling(round_num))
    _write_json(os.path.join(workspace, "claims", "claim_ledger.json"), [
        {"claim_id": "clm_1_pro_1", "round": 1, "speaker": "pro", "status": "verified",
         "evidence_ids": ["evi_test0001"]},
        {"claim_id": "clm_1_con_1", "round": 1, "speaker": "con", "status": "contested",
         "evidence_ids": ["evi_test0002"]},
    ])


def _report(workspace: str, **kwargs) -> dict:
    return DebateQualityAssessor(workspace, "Test topic", rounds_planned=1, **kwargs).assess()


def test_all_eight_dimensions_present_and_scored(workspace):
    _seed_workspace(workspace)
    report = _report(workspace)
    assert [d["dimension"] for d in report["dimensions"]] == list(DIMENSIONS)
    assert all(0.0 <= d["score"] <= 1.0 for d in report["dimensions"])
    assert 0.0 <= report["overall_score"] <= 1.0
    assert abs(sum(report["dimension_weights"].values()) - 1.0) < 1e-6
    assert report["assessment_version"] == "phase5_eight_dimensions"
    assert report["rounds_completed"] == 1


def test_reasoning_chain_incompleteness_lowers_depth(workspace):
    _seed_workspace(workspace)
    base = _report(workspace)

    turn_path = os.path.join(workspace, "rounds", "round_1", "pro_turn.json")
    turn = read_json(turn_path)
    del turn["arguments"][0]["reasoning_chain"]["mechanism"]
    _write_json(turn_path, turn)
    degraded = _report(workspace)

    depth = {d["dimension"]: d["score"] for d in degraded["dimensions"]}
    base_depth = {d["dimension"]: d["score"] for d in base["dimensions"]}
    assert depth["reasoning_depth"] < base_depth["reasoning_depth"]


def test_argument_imbalance_lowers_balance(workspace):
    _seed_workspace(workspace)
    turn_path = os.path.join(workspace, "rounds", "round_1", "pro_turn.json")
    turn = read_json(turn_path)
    turn["arguments"].append(dict(turn["arguments"][0]))  # pro doubles up
    _write_json(turn_path, turn)
    report = _report(workspace)
    balance = next(d for d in report["dimensions"] if d["dimension"] == "debate_balance")
    assert balance["score"] < 1.0
    assert balance["subscores"]["pro_arguments"] == 2
    assert balance["subscores"]["con_arguments"] == 1


def test_mrp_fulfilment_detected(workspace):
    # Round-1 ruling carries an MRP targeted at con; con answers in round 2.
    _seed_workspace(workspace, rounds=1)
    ruling = read_json(os.path.join(workspace, "rounds", "round_1", "judge_ruling.json"))
    ruling["mandatory_response_points"] = [
        {"point_id": "mrp_1_1", "target": "con", "point": "answer this", "reason": "needed"},
    ]
    _write_json(os.path.join(workspace, "rounds", "round_1", "judge_ruling.json"), ruling)

    rdir = os.path.join(workspace, "rounds", "round_2")
    _write_json(os.path.join(rdir, "pro_turn.json"), valid_turn(2, "pro"))
    _write_json(os.path.join(rdir, "con_turn.json"), valid_turn(2, "con"))
    _write_json(os.path.join(rdir, "judge_ruling.json"), valid_judge_ruling(2))
    con_turn_path = os.path.join(rdir, "con_turn.json")
    con_turn = read_json(con_turn_path)
    con_turn["mandatory_responses"] = [{"point_id": "mrp_1_1", "response_text": "answered"}]
    _write_json(con_turn_path, con_turn)

    assessor = DebateQualityAssessor(workspace, "Test topic", rounds_planned=2)
    assert assessor._rebuttal_effectiveness()["subscores"]["mrp_fulfilment"] == 1.0


def test_credibility_scores_feed_evidence_quality(workspace):
    _seed_workspace(workspace)
    _write_json(os.path.join(workspace, "evidence", "evidence_credibility.json"), {
        "average": 0.82,
        "items": [{"evidence_id": f"evi_test{i:04d}", "total": 0.82} for i in range(1, 4)],
    })
    report = _report(workspace)
    eq = next(d for d in report["dimensions"] if d["dimension"] == "evidence_quality")
    assert eq["subscores"]["average_credibility"] == 0.82


def test_conclusion_reliability_uses_final_report(workspace):
    _seed_workspace(workspace)
    _write_json(os.path.join(workspace, "reports", "final_report.json"), {
        "verified_facts": ["fact one"],
        "scenario_outlook": {"base_case": "x"},
        "watchlist_24h": [],
        "contested_points": [{"point": "p", "resolution_status": "leaning_pro"}],
        "conclusion_profiles": [{
            "conclusion_id": "concl_1", "conclusion_text": "c", "source_claims": [],
            "profile": {
                "falsifiability": {"value": "easily_testable", "test_method": "rerun the numbers"},
                "validity_window": {"value": "weeks", "expiry_condition": "new data"},
            },
        }],
    })
    report = _report(workspace)
    cr = next(d for d in report["dimensions"] if d["dimension"] == "conclusion_reliability")
    assert cr["subscores"]["grounded_verified_facts"] is True
    assert cr["subscores"]["profile_depth_share"] == 1.0
    assert cr["subscores"]["contested_resolution_labelled"] == 1.0


def test_weight_overrides_normalised(tmp_path):
    cfg = tmp_path / "quality_rules.yaml"
    cfg.write_text(
        "dimension_weights:\n  cross_validation_rate: 0.4\n  debate_balance: 0.1\n",
        encoding="utf-8",
    )
    weights = load_quality_weights(str(cfg))
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    assert weights["cross_validation_rate"] > weights["reasoning_depth"]


def test_artifacts_written(workspace):
    _seed_workspace(workspace)
    report = assess_debate_quality(workspace, "Test topic", 1)
    metrics = read_json(os.path.join(workspace, "reports", "quality_metrics.json"))
    assert metrics["overall_score"] == report["overall_score"]

    md_path = os.path.join(workspace, "reports", "quality_report.md")
    with open(md_path, encoding="utf-8") as f:
        md = f.read()
    assert "# Quality Report / 质量评估报告" in md
    assert "Overall Score / 综合得分" in md
    for dim in report["dimensions"]:
        assert dim["label"].split(" / ")[0] in md

    html_path = os.path.join(workspace, "reports", "quality_dashboard.html")
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    assert "<svg" in html and "radar-area" in html
    assert "综合 / overall" in html
    assert html.strip().endswith("</html>")
