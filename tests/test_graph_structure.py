"""Graph structure tests: nodes, edges, fan-out, and loop wiring."""

from __future__ import annotations

from critical_debater.graph.builder import build_debate_graph

from fake_agent import FakeScriptedRunner

EXPECTED_NODES = {
    "initialize_debate",
    "source_ingest_initial",
    "freshness_check_initial",
    "evidence_gate",
    "source_ingest_retry",
    "round_entry",
    "per_round_ingest",
    "debate_prep",
    "pro_debater",
    "con_debater",
    "post_turns",
    "judge_audit",
    "post_round",
    "next_round",
    "final_synthesis",
    "report_gate",
    "quality_assessment",
}


def _edges(graph):
    return {(e.source, e.target) for e in graph.get_graph().edges if e.source != "__start__"}


def test_graph_contains_all_plan_nodes():
    graph = build_debate_graph(FakeScriptedRunner())
    nodes = set(graph.get_graph().nodes)
    assert EXPECTED_NODES.issubset(nodes)


def test_graph_edges_and_fan_out():
    graph = build_debate_graph(FakeScriptedRunner())
    edges = _edges(graph)
    # Linear backbone.
    for src, dst in [
        ("initialize_debate", "source_ingest_initial"),
        ("source_ingest_initial", "freshness_check_initial"),
        ("freshness_check_initial", "evidence_gate"),
        ("source_ingest_retry", "evidence_gate"),
        ("per_round_ingest", "debate_prep"),
        ("pro_debater", "post_turns"),
        ("con_debater", "post_turns"),
        ("post_turns", "judge_audit"),
        ("judge_audit", "post_round"),
        ("next_round", "round_entry"),
        ("final_synthesis", "report_gate"),
        ("report_gate", "quality_assessment"),
    ]:
        assert (src, dst) in edges, f"missing edge {src} -> {dst}"

    # Conditional edges.
    assert ("evidence_gate", "source_ingest_retry") in edges
    assert ("evidence_gate", "round_entry") in edges
    assert ("round_entry", "per_round_ingest") in edges
    assert ("round_entry", "debate_prep") in edges
    assert ("post_round", "next_round") in edges
    assert ("post_round", "final_synthesis") in edges

    # Parallel Pro/Con fan-out from debate_prep.
    assert ("debate_prep", "pro_debater") in edges
    assert ("debate_prep", "con_debater") in edges


def test_routing_functions():
    from critical_debater.graph.builder import (
        _route_after_evidence_gate,
        _route_after_post_round,
        _route_after_round_entry,
    )

    assert _route_after_evidence_gate({"evidence_gate_passed": True}) == "round_entry"
    assert _route_after_evidence_gate({"evidence_gate_passed": False}) == "source_ingest_retry"

    hybrid_r1 = {"evidence_refresh": "hybrid", "current_round": 1}
    hybrid_r2 = {"evidence_refresh": "hybrid", "current_round": 2}
    per_round = {"evidence_refresh": "per_round", "current_round": 1}
    upfront = {"evidence_refresh": "upfront_only", "current_round": 2}
    assert _route_after_round_entry(hybrid_r1) == "debate_prep"
    assert _route_after_round_entry(hybrid_r2) == "per_round_ingest"
    assert _route_after_round_entry(per_round) == "per_round_ingest"
    assert _route_after_round_entry(upfront) == "debate_prep"

    assert _route_after_post_round({"current_round": 1, "rounds": 2}) == "next_round"
    assert _route_after_post_round({"current_round": 2, "rounds": 2}) == "final_synthesis"
