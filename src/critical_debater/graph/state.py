"""Debate graph state definition.

The workspace files (``evidence/evidence_store.json``,
``claims/claim_ledger.json``, round artifacts) remain the source of truth in
Phase 1 because the agent capabilities run as CLI subprocesses that
read/write those files directly. The graph state carries orchestration
control fields plus *mirrors* of the evidence store / claim ledger, refreshed
at gate and post-round nodes; Phase 2's in-process model providers will
consume these mirrors directly.

``pro_arguments`` / ``con_arguments`` / ``judge_rulings`` use an
append-only reducer so the parallel Pro/Con branches never clobber each
other's updates (``add_messages`` semantics are inappropriate for plain
argument dicts).
"""

from __future__ import annotations

import operator
from typing import Annotated, Dict, List, TypedDict


class DebateState(TypedDict):
    """辩论状态 / Debate state flowing through the LangGraph graph."""

    # --- 基础配置 / base configuration ---
    topic: str
    rounds: int
    current_round: int
    depth: str
    mode: str
    language: str
    output_format: str

    # --- 证据系统 / evidence system ---
    evidence_store: List[Dict]          # mirror of evidence_store.json
    evidence_weights: Dict[str, float]  # NEW (Phase 4): 证据权重

    # --- 声明系统 / claim system ---
    claim_ledger: List[Dict]            # mirror of claim_ledger.json

    # --- 辩论轮次数据 / per-round artifacts (append-only) ---
    pro_arguments: Annotated[List[Dict], operator.add]
    con_arguments: Annotated[List[Dict], operator.add]
    judge_rulings: Annotated[List[Dict], operator.add]

    # --- 模型配置 / model configuration ---
    pro_model: str
    con_model: str
    judge_model: str
    model_provider: str                 # NEW: cli for Phase 1, provider id in Phase 2+

    # --- 质量评估 / quality assessment (NEW, Phase 5 expands) ---
    quality_metrics: Dict

    # --- 工作空间与控制流 / workspace & orchestration control ---
    workspace_path: str
    status: str
    speculation: str
    evidence_refresh: str
    min_evidence: int
    source_retries: int
    ingest_retries_used: int
    step_timeout_sec: int
    evidence_gate_passed: bool
    resume_entry: str  # 'fresh' | 'rounds' | 'final': where a resumed run re-enters
