"""High-level entry point: run a full debate through the LangGraph graph."""

from __future__ import annotations

import re
from typing import Optional

from ..config import DebateOptions
from ..models.base import AgentRunner
from ..models.registry import get_runner
from ..workspace import load_config, timestamp
from .builder import build_debate_graph
from .state import DebateState


def map_resume_entry(config: dict, rounds: int) -> str:
    """Map a workspace checkpoint (config.json status) to a graph entry point.

    - ``in_progress`` / ``failed_round_N``  → re-enter the round loop there
    - ``round_N_complete``                  → continue at round N+1 (final when done)
    - ``failed_final_synthesis`` / ``failed_report_validation`` / ``complete`` → final stage
    - anything else (new workspace)          → fresh start
    """
    status = str(config.get("status") or "")

    if status == "in_progress" or status.startswith("failed_round_"):
        return "rounds"
    if status in ("failed_final_synthesis", "failed_report_validation", "complete"):
        return "final"
    match = re.fullmatch(r"round_(\d+)_complete", status)
    if match:
        return "rounds" if int(match.group(1)) < rounds else "final"
    return "fresh"


def _resume_round(config: dict, rounds: int) -> int:
    """Round to re-enter on a 'rounds' resume."""
    status = str(config.get("status") or "")
    match = re.fullmatch(r"round_(\d+)_complete", status)
    if match:
        return min(int(match.group(1)) + 1, rounds)
    if status.startswith("failed_round_"):
        return min(int(status.rsplit("_", 1)[1]), rounds)
    return max(1, min(int(config.get("current_round") or 1), rounds))


def build_initial_state(workspace: str, opts: DebateOptions,
                        resume: bool = False) -> DebateState:
    """Seed the graph state from run options + workspace config.

    With ``resume=True`` the workspace checkpoint (config.json status) decides
    where the graph re-enters: completed rounds are skipped (断点恢复).
    """
    try:
        cfg = load_config(workspace)
    except (FileNotFoundError, OSError):
        cfg = {}

    resume_entry = map_resume_entry(cfg, opts.rounds) if resume else "fresh"
    current_round = 1
    if resume_entry == "rounds":
        current_round = _resume_round(cfg, opts.rounds)

    return DebateState(
        topic=opts.topic,
        rounds=opts.rounds,
        current_round=current_round,
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
        resume_entry=resume_entry,
    )


def run_debate(workspace: str, opts: DebateOptions, runner: Optional[AgentRunner] = None,
               resume: bool = False) -> DebateState:
    """Run the full debate orchestration flow through the LangGraph graph.

    With ``resume=True`` an interrupted workspace continues from its
    checkpoint instead of restarting (断点恢复).

    Raises :class:`DebateStepFailure` on hard step failure (audit + config
    status are already updated at that point).
    """
    initial_state = build_initial_state(workspace, opts, resume=resume)
    effective_runner = runner if runner is not None else get_runner()
    initial_state["model_provider"] = effective_runner.runtime
    graph = build_debate_graph(effective_runner)

    # Long loops (many rounds + ingest retries) exceed LangGraph's default
    # recursion limit of 25; budget generously per round.
    recursion_limit = max(50, opts.rounds * 15 + 20)
    final_state = graph.invoke(initial_state, config={"recursion_limit": recursion_limit})

    print(f"\n[{timestamp()}] Debate finished with status: {final_state.get('status')}")
    return final_state
