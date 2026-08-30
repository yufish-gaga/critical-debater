"""High-level entry point: run a full debate through the LangGraph graph."""

from __future__ import annotations

from typing import Optional

from ..config import DebateOptions
from ..models.base import AgentRunner
from ..models.registry import get_runner
from ..workspace import load_config, timestamp
from .builder import build_debate_graph
from .state import DebateState


def build_initial_state(workspace: str, opts: DebateOptions) -> DebateState:
    """Seed the graph state from run options + workspace config."""
    try:
        cfg = load_config(workspace)
    except (FileNotFoundError, OSError):
        cfg = {}
    return DebateState(
        topic=opts.topic,
        rounds=opts.rounds,
        current_round=1,
        depth=opts.depth,
        mode=opts.mode,
        language=opts.language,
        output_format=opts.output_format,
        evidence_store=[],
        evidence_weights={},
        claim_ledger=[],
        pro_arguments=[],
        con_arguments=[],
        judge_rulings=[],
        pro_model=cfg.get("pro_model", "balanced"),
        con_model=cfg.get("con_model", "balanced"),
        judge_model=cfg.get("judge_model", "deep"),
        model_provider="cli",
        quality_metrics={},
        workspace_path=workspace,
        status="initialized",
        speculation=opts.speculation,
        evidence_refresh=opts.evidence_refresh,
        min_evidence=opts.min_evidence,
        source_retries=opts.source_retries,
        ingest_retries_used=0,
        step_timeout_sec=opts.step_timeout_sec,
        evidence_gate_passed=False,
    )


def run_debate(workspace: str, opts: DebateOptions, runner: Optional[AgentRunner] = None) -> DebateState:
    """Run the full debate orchestration flow through the LangGraph graph.

    Raises :class:`DebateStepFailure` on hard step failure (audit + config
    status are already updated at that point).
    """
    initial_state = build_initial_state(workspace, opts)
    effective_runner = runner if runner is not None else get_runner()
    initial_state["model_provider"] = effective_runner.runtime
    graph = build_debate_graph(effective_runner)

    # Long loops (many rounds + ingest retries) exceed LangGraph's default
    # recursion limit of 25; budget generously per round.
    recursion_limit = max(50, opts.rounds * 15 + 20)
    final_state = graph.invoke(initial_state, config={"recursion_limit": recursion_limit})

    print(f"\n[{timestamp()}] Debate finished with status: {final_state.get('status')}")
    return final_state
