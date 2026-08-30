"""LangGraph graph construction.

Wires the v3 debate graph (node layout mirrors the plan diagram; the two
deterministic gates added for v2 behavior parity are ``evidence_gate`` /
``source_ingest_retry`` and ``post_turns``)::

    START
      → resume_router ─┬─ (fresh) → initialize_debate
                       ├─ (rounds) → round_entry          # resume: skip done rounds
                       └─ (final) → final_synthesis       # resume: skip all rounds
      initialize_debate → source_ingest_initial → freshness_check_initial
      → evidence_gate ─┬─ (insufficient, retries left) → source_ingest_retry ─┐
                       │            ▲────────────────────────────────────────┘
                       └─ (ok) → round_entry ─┬─ (refresh due) → per_round_ingest ─┐
                                              └─ (else) ───────────────────────────┴→ debate_prep
      debate_prep → pro_debater ─┐
                 └→ con_debater ─┴→ post_turns → judge_audit → post_round
      post_round ─┬─ (rounds remain) → next_round → round_entry
                  └─ (done) → final_synthesis → report_gate → quality_assessment → END
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from ..models.base import AgentRunner
from ..models.registry import get_runner
from .nodes import make_nodes
from .state import DebateState

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


def _route_resume(state: DebateState) -> str:
    entry = state.get("resume_entry", "fresh")
    if entry == "rounds":
        return "round_entry"
    if entry == "final":
        return "final_synthesis"
    return "initialize_debate"


def _route_after_evidence_gate(state: DebateState) -> str:
    if state.get("evidence_gate_passed"):
        return "round_entry"
    return "source_ingest_retry"


def _route_after_round_entry(state: DebateState) -> str:
    needs_refresh = state["evidence_refresh"] == "per_round" or (
        state["evidence_refresh"] == "hybrid" and state["current_round"] > 1
    )
    if needs_refresh:
        return "per_round_ingest"
    return "debate_prep"


def _route_after_post_round(state: DebateState) -> str:
    if state["current_round"] < state["rounds"]:
        return "next_round"
    return "final_synthesis"


def build_debate_graph(runner: AgentRunner | None = None) -> "CompiledStateGraph":
    nodes = make_nodes(runner if runner is not None else get_runner())

    graph = StateGraph(DebateState)
    for name, fn in nodes.items():
        graph.add_node(name, fn)

    graph.add_edge(START, "resume_router")
    graph.add_conditional_edges(
        "resume_router",
        _route_resume,
        {
            "initialize_debate": "initialize_debate",
            "round_entry": "round_entry",
            "final_synthesis": "final_synthesis",
        },
    )
    graph.add_edge("initialize_debate", "source_ingest_initial")
    graph.add_edge("source_ingest_initial", "freshness_check_initial")
    graph.add_edge("freshness_check_initial", "evidence_gate")
    graph.add_conditional_edges(
        "evidence_gate",
        _route_after_evidence_gate,
        {"source_ingest_retry": "source_ingest_retry", "round_entry": "round_entry"},
    )
    graph.add_edge("source_ingest_retry", "evidence_gate")
    graph.add_conditional_edges(
        "round_entry",
        _route_after_round_entry,
        {"per_round_ingest": "per_round_ingest", "debate_prep": "debate_prep"},
    )
    graph.add_edge("per_round_ingest", "debate_prep")
    # Parallel Pro/Con fan-out; both branches join at post_turns.
    graph.add_edge("debate_prep", "pro_debater")
    graph.add_edge("debate_prep", "con_debater")
    graph.add_edge("pro_debater", "post_turns")
    graph.add_edge("con_debater", "post_turns")
    graph.add_edge("post_turns", "judge_audit")
    graph.add_edge("judge_audit", "post_round")
    graph.add_conditional_edges(
        "post_round",
        _route_after_post_round,
        {"next_round": "next_round", "final_synthesis": "final_synthesis"},
    )
    graph.add_edge("next_round", "round_entry")
    graph.add_edge("final_synthesis", "report_gate")
    graph.add_edge("report_gate", "quality_assessment")
    graph.add_edge("quality_assessment", END)

    return graph.compile()
