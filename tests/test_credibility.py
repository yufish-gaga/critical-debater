"""Tests for evidence credibility scoring and the relationship graph (v3 Phase 4)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from critical_debater.evidence.credibility import (
    DIMENSIONS,
    EvidenceCredibilityScorer,
    ScoringContext,
    load_credibility_scores,
    load_rules,
    score_evidence_store,
)
from critical_debater.evidence.relations import build_evidence_graph

from fake_agent import _write_json, evidence_item

NOW = datetime(2026, 8, 30, tzinfo=timezone.utc)


def make_scorer(store: list, claims: list | None = None, mode: str = "balanced",
                round_num: int = 1) -> tuple[EvidenceCredibilityScorer, ScoringContext, dict]:
    scorer = EvidenceCredibilityScorer()  # built-in default rules
    context = ScoringContext(mode=mode, round_num=round_num, store=store, claims=claims or [])
    weights, _ = scorer.adjust_weights(context)
    return scorer, context, weights


# --- rules -------------------------------------------------------------------


def test_default_weights_match_plan():
    weights = load_rules()["weights"]
    assert abs(weights["authority"] - 0.30) < 1e-9
    assert abs(weights["freshness"] - 0.15) < 1e-9
    assert abs(weights["cross_validation"] - 0.25) < 1e-9
    assert abs(weights["content_quality"] - 0.20) < 1e-9
    assert abs(weights["transparency"] - 0.10) < 1e-9


def test_yaml_rules_override_defaults(tmp_path):
    cfg = tmp_path / "rules.yaml"
    cfg.write_text("weights:\n  authority: 0.5\n", encoding="utf-8")
    rules = load_rules(str(cfg))
    assert rules["weights"]["authority"] == 0.5
    assert rules["weights"]["freshness"] == 0.15  # untouched default


# --- dynamic weight adjustment ------------------------------------------------


def test_weights_normalised_after_adjustment():
    scorer = EvidenceCredibilityScorer()
    hot_store = [evidence_item(i, credibility_tier="tier4_social") for i in range(5)]
    context = ScoringContext(mode="red_team", round_num=3, store=hot_store)
    weights, applied = scorer.adjust_weights(context)
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    assert "red_team_mode" in applied
    assert "late_round_scrutiny" in applied
    # red_team boosts cross-validation above its 0.25 base share
    assert weights["cross_validation"] > weights["authority"]


def test_no_adjustment_in_balanced_first_round():
    scorer = EvidenceCredibilityScorer()
    context = ScoringContext(mode="balanced", round_num=1,
                             store=[evidence_item(i) for i in range(3)])
    weights, applied = scorer.adjust_weights(context)
    assert applied == []
    assert abs(sum(weights.values()) - 1.0) < 1e-6


# --- dimensions ---------------------------------------------------------------


def test_authoritative_fresh_corroborated_scores_high():
    item = evidence_item(1, source_type="government",
                         credibility_tier="tier1_authoritative",
                         url="https://www.gov.cn/policy",
                         published_at=(NOW - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                         corroboration_status="corroborated", snippet="x" * 300)
    scorer, context, weights = make_scorer([item])
    result = scorer.score_item(item, context, weights, now=NOW)
    assert result["total"] > 0.9
    assert result["dimensions"]["authority"] == 1.0
    assert result["dimensions"]["freshness"] == 1.0
    assert result["dimensions"]["cross_validation"] == 1.0


def test_social_stale_unverified_scores_low():
    item = evidence_item(2, source_type="twitter", credibility_tier="tier4_social",
                         published_at=(NOW - timedelta(days=900)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                         corroboration_status=None, snippet="short")
    item["freshness_status"] = "stale"
    item["social_credibility_flag"] = "likely_unreliable"
    scorer, context, weights = make_scorer([item])
    result = scorer.score_item(item, context, weights, now=NOW)
    assert result["total"] < 0.3


def test_reasoning_track_never_decays():
    item = evidence_item(3, evidence_track="reasoning",
                         published_at="2001-09-11T00:00:00Z")
    item["freshness_status"] = "timeless"
    scorer, context, weights = make_scorer([item])
    result = scorer.score_item(item, context, weights, now=NOW)
    assert result["dimensions"]["freshness"] == 1.0  # contract-critical rule


def test_contradicted_evidence_loses_cross_validation():
    item = evidence_item(4, corroboration_status="contradicted")
    scorer, context, weights = make_scorer([item])
    result = scorer.score_item(item, context, weights, now=NOW)
    assert result["dimensions"]["cross_validation"] == 0.0


def test_claim_verdicts_adjust_cross_validation():
    item = evidence_item(5)
    claims_verified = [{"claim_id": "clm_1_pro_1", "status": "verified",
                        "evidence_ids": ["evi_test0005"]}]
    claims_contested = [{"claim_id": "clm_1_con_1", "status": "contested",
                         "evidence_ids": ["evi_test0005"]}]

    scorer, context, weights = make_scorer([item], claims_verified)
    boosted = scorer.score_item(item, context, weights, now=NOW)
    base = 0.4
    assert boosted["dimensions"]["cross_validation"] == pytest_approx(base + 0.15)

    scorer2, context2, weights2 = make_scorer([item], claims_verified + claims_contested)
    mixed = scorer2.score_item(item, context2, weights2, now=NOW)
    assert mixed["dimensions"]["cross_validation"] == pytest_approx(base)  # boost and penalty cancel


def pytest_approx(value: float) -> float:
    return round(min(max(value, 0.0), 1.0), 6)


def test_duplicate_domain_dilutes_independence():
    a = evidence_item(6, url="https://www.repub.com/a")
    b = evidence_item(7, url="https://www.repub.com/b")
    scorer, context, weights = make_scorer([a, b])
    result = scorer.score_item(a, context, weights, now=NOW)
    assert result["dimensions"]["cross_validation"] < 0.4  # diluted below null baseline


def test_score_store_reports_average_and_weights():
    store = [evidence_item(i) for i in range(1, 4)]
    scorer = EvidenceCredibilityScorer()
    context = ScoringContext(store=store)
    report = scorer.score_store(context)
    assert set(report["weights_used"]) == set(DIMENSIONS)
    assert 0.0 <= report["average"] <= 1.0
    assert len(report["items"]) == 3


# --- workspace integration ----------------------------------------------------


def test_score_evidence_store_writes_artifact(workspace):
    _write_json(os.path.join(workspace, "evidence", "evidence_store.json"),
                [evidence_item(1), evidence_item(2, corroboration_status="corroborated")])
    report = score_evidence_store(workspace, round_num=1)
    assert os.path.exists(os.path.join(workspace, "evidence", "evidence_credibility.json"))
    assert load_credibility_scores(workspace)["evi_test0001"] == report["items"][0]["total"]


def test_graph_links_duplicates_and_co_citations(workspace):
    store = [
        {**evidence_item(1), "corroboration_status": "corroborated"},
        {**evidence_item(2), "url": evidence_item(1)["url"]},  # duplicate url
        {**evidence_item(3), "url": "https://other.example/x"},
    ]
    _write_json(os.path.join(workspace, "evidence", "evidence_store.json"), store)
    _write_json(os.path.join(workspace, "claims", "claim_ledger.json"), [
        {"claim_id": "clm_1_pro_1", "status": "verified", "speaker": "pro", "round": 1,
         "evidence_ids": ["evi_test0001", "evi_test0003"],
         "conflict_details": [{
             "source_a": {"evidence_id": "evi_test0001"},
             "source_b": {"evidence_id": "evi_test0003"},
             "divergence_point": "differing figures",
         }]},
    ])

    graph = build_evidence_graph(workspace)
    kinds = {(e["kind"]) for e in graph["edges"]}
    assert "duplicate_of" in kinds
    assert "supports" in kinds
    assert "co_cited" in kinds
    assert "contradicts" in kinds
    assert "same_domain" in kinds

    contradict = [e for e in graph["edges"] if e["kind"] == "contradicts"][0]
    assert contradict["divergence_point"] == "differing figures"

    stats = graph["stats"]
    assert stats["evidence_nodes"] == 3
    assert stats["claim_nodes"] == 1
    assert stats["domain_clusters"] >= 1


def test_graph_includes_credibility_scores(workspace):
    _write_json(os.path.join(workspace, "evidence", "evidence_store.json"), [evidence_item(1)])
    report = score_evidence_store(workspace, round_num=1)
    graph = build_evidence_graph(workspace)
    node = graph["nodes"][0]
    assert node["credibility_score"] == report["items"][0]["total"]
