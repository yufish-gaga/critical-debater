"""Capability dispatch prompts.

Verbatim port of the prompt strings the v2 orchestrator sends to the agent
runtime; the capability markdown files live in
``critical-debater-suite/capabilities/`` and are resolved by the agent CLI
itself, so v3 keeps the exact same surface.
"""

from __future__ import annotations


def build_source_ingest_broad_prompt(topic: str, depth: str, num_queries: int, workspace: str) -> str:
    return (
        f"Execute source-ingest.md: topic={topic}, mode=broad, round=0, "
        f"depth={depth}, num_queries={num_queries}. "
        f"Workspace: {workspace}"
    )


def build_source_ingest_broaden_prompt(topic: str, workspace: str) -> str:
    return (
        f"Execute source-ingest.md: topic={topic}, mode=broad, round=0, "
        f"broaden keywords. Workspace: {workspace}"
    )


def build_source_ingest_focused_prompt(topic: str, round_num: int, search_focus: str, workspace: str) -> str:
    return (
        f"Execute source-ingest.md: topic={topic}, mode=focused, "
        f"round={round_num}, search_focus={search_focus}. Workspace: {workspace}"
    )


def build_freshness_check_prompt(workspace: str) -> str:
    return f"Execute freshness-check.md: workspace={workspace}"


def build_debate_turn_prompt(side: str, round_num: int, topic: str, mode: str,
                             speculation: str, depth: str,
                             prev_round_context: str, workspace: str) -> str:
    return (
        f"Execute debate-turn.md: side={side}, round={round_num}, topic={topic}, "
        f"mode={mode}, speculation={speculation}, depth={depth}. "
        f"{prev_round_context}. Workspace: {workspace}"
    )


def build_debate_turn_fix_prompt(side: str, round_num: int, workspace: str) -> str:
    return (
        f"Re-execute debate-turn.md: fix JSON validation errors. "
        f"side={side}, round={round_num}. Workspace: {workspace}"
    )


def build_judge_audit_prompt(round_num: int, workspace: str) -> str:
    return f"Execute judge-audit.md: round={round_num}. Workspace: {workspace}"


def build_claim_ledger_update_prompt(round_num: int, workspace: str) -> str:
    return f"Execute claim-ledger-update.md: round={round_num}. Workspace: {workspace}"


def build_final_synthesis_prompt(workspace: str) -> str:
    return f"Execute final-synthesis.md: workspace={workspace}"
