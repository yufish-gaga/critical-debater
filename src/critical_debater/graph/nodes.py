"""Graph node implementations.

One-to-one port of the v2 orchestration phases
(``debate_orchestrator_generic.run_debate``) onto LangGraph nodes:

- LLM-backed capability steps (source ingest, freshness check, debate turns,
  judge audit, claim ledger update, final synthesis) dispatch through the
  :class:`~critical_debater.models.base.AgentRunner` exactly as v2 dispatched
  CLI subprocesses — same prompts, model tiers, step ids, retry counts.
- Deterministic steps (validation gates, evidence merge, claim consistency,
  report fallback, audit) are pure Python, ported from v2.

Node functions return partial state updates; hard failures record the audit
event + config status, then raise :class:`DebateStepFailure` (v2
``fail_step`` semantics), which aborts the graph run.
"""

from __future__ import annotations

import json
import os
import shutil

from ..agents.prompts import (
    build_claim_ledger_update_prompt,
    build_debate_turn_fix_prompt,
    build_debate_turn_prompt,
    build_final_synthesis_prompt,
    build_freshness_check_prompt,
    build_judge_audit_prompt,
    build_source_ingest_broad_prompt,
    build_source_ingest_broaden_prompt,
    build_source_ingest_focused_prompt,
)
from ..claims.consistency import verify_claim_ledger_consistency
from ..config import CONFIG_DEFAULTS, DEPTH_QUERY_COUNT
from ..evidence.merge import evidence_store_path, merge_new_evidence
from ..failures import fail_step, failed_result, require_step
from ..models.base import AgentRunner
from ..quality.assessor import assess_debate_quality
from ..synthesis.fallback import (
    debate_report_path,
    final_report_path,
    report_backup_path,
    run_renderer,
)
from ..validation import validate_debate_report_file, validate_json_file
from ..workspace import (
    append_audit,
    ensure_workspace_config_defaults,
    read_json,
    timestamp,
    update_config,
)
from .state import DebateState


def _turn_path(workspace: str, round_num: int, side: str) -> str:
    return os.path.join(workspace, "rounds", f"round_{round_num}", f"{side}_turn.json")


def _judge_path(workspace: str, round_num: int) -> str:
    return os.path.join(workspace, "rounds", f"round_{round_num}", "judge_ruling.json")


def _prev_round_context(round_num: int) -> str:
    if round_num <= 1:
        return ""
    return (
        f"Read round {round_num-1} data: "
        f"rounds/round_{round_num-1}/pro_turn.json, "
        f"rounds/round_{round_num-1}/con_turn.json, "
        f"rounds/round_{round_num-1}/judge_ruling.json"
    )


def make_nodes(runner: AgentRunner) -> dict:
    """Build the node functions bound to a specific agent runner."""

    def initialize_debate(state: DebateState) -> dict:
        workspace = state["workspace_path"]
        ensure_workspace_config_defaults(workspace, {
            "depth": state["depth"] or CONFIG_DEFAULTS["depth"],
            "mode": state["mode"] or CONFIG_DEFAULTS["mode"],
            "evidence_refresh": state["evidence_refresh"] or CONFIG_DEFAULTS["evidence_refresh"],
            "language": state["language"] or CONFIG_DEFAULTS["language"],
        })
        print(f"[{timestamp()}] Starting debate: {state['topic']}")
        print(f"[{timestamp()}] Rounds: {state['rounds']}, Depth: {state['depth']}, Mode: {state['mode']}")
        return {"status": "initializing"}

    def source_ingest_initial(state: DebateState) -> dict:
        workspace = state["workspace_path"]
        num_queries = DEPTH_QUERY_COUNT.get(state["depth"], 5)
        result = runner.run(
            "source_ingest_round_0",
            build_source_ingest_broad_prompt(state["topic"], state["depth"], num_queries, workspace),
            model_tier="balanced",
            timeout_sec=state["step_timeout_sec"],
            context={
                "workspace": workspace,
                "topic": state["topic"],
                "depth": state["depth"],
                "mode": "broad",
                "round": 0,
                "num_queries": num_queries,
            },
        )
        require_step(workspace, "failed_initialization", "phase1_source_ingest", result)
        return {}

    def freshness_check_initial(state: DebateState) -> dict:
        workspace = state["workspace_path"]
        result = runner.run(
            "freshness_check_0",
            build_freshness_check_prompt(workspace),
            model_tier="balanced",
            timeout_sec=state["step_timeout_sec"],
            context={"workspace": workspace},
        )
        require_step(workspace, "failed_initialization", "phase1_freshness", result)
        return {}

    def evidence_gate(state: DebateState) -> dict:
        """Minimum-evidence gate with retry loop (v2 phase 1 step 1c)."""
        workspace = state["workspace_path"]
        path = evidence_store_path(workspace)
        if not os.path.exists(path):
            # v2 parity: a workspace without an evidence store skips the gate.
            return {"evidence_gate_passed": True, "evidence_count": 0, "evidence_store": []}

        evidence = read_json(path)
        count = len(evidence)
        if count < state["min_evidence"]:
            if state["ingest_retries_used"] >= state["source_retries"]:
                print(f"[{timestamp()}] Warning: only {count} evidence items "
                      f"(minimum: {state['min_evidence']}); retries exhausted")
                fail_step(
                    workspace,
                    "failed_initialization",
                    "phase1_min_evidence",
                    failed_result(
                        "source_ingest_min_evidence_gate",
                        "insufficient_evidence",
                        f"evidence count {count} < minimum {state['min_evidence']}",
                    ),
                )
            print(f"[{timestamp()}] Warning: Only {count} evidence items "
                  f"(minimum: {state['min_evidence']}). Retrying ingest...")
            return {"evidence_gate_passed": False, "evidence_count": count, "evidence_store": evidence}
        return {"evidence_gate_passed": True, "evidence_count": count, "evidence_store": evidence}

    def source_ingest_retry(state: DebateState) -> dict:
        workspace = state["workspace_path"]
        retry_no = state["ingest_retries_used"] + 1
        result = runner.run(
            f"source_ingest_retry_{retry_no}",
            build_source_ingest_broaden_prompt(state["topic"], workspace),
            model_tier="balanced",
            timeout_sec=state["step_timeout_sec"],
            context={
                "workspace": workspace,
                "topic": state["topic"],
                "mode": "broad",
                "round": 0,
                "broaden_keywords": True,
            },
        )
        require_step(workspace, "failed_initialization", "phase1_source_ingest_retry", result)
        return {"ingest_retries_used": retry_no}

    def round_entry(state: DebateState) -> dict:
        round_num = state["current_round"]
        workspace = state["workspace_path"]
        print(f"\n{'='*60}")
        print(f"PHASE 2: ROUND {round_num}/{state['rounds']}")
        print(f"{'='*60}")
        append_audit(workspace, "round_started", {"round": round_num})
        update_config(workspace, {"current_round": round_num, "status": "in_progress"})
        return {"status": "in_progress"}

    def per_round_ingest(state: DebateState) -> dict:
        """Focused evidence refresh driven by the previous judge ruling (v2 step 2a)."""
        workspace = state["workspace_path"]
        round_num = state["current_round"]
        failed_status = f"failed_round_{round_num}"

        print(f"[{timestamp()}] Per-round evidence refresh for round {round_num}")
        prev_ruling_path = _judge_path(workspace, round_num - 1)
        search_focus = ""
        if os.path.exists(prev_ruling_path):
            ruling = read_json(prev_ruling_path)
            mrps = ruling.get("mandatory_response_points", [])
            flags = ruling.get("causal_validity_flags", [])
            search_focus = json.dumps({"mrps": mrps, "flags": flags})

        refresh = runner.run(
            f"source_ingest_round_{round_num}",
            build_source_ingest_focused_prompt(state["topic"], round_num, search_focus, workspace),
            model_tier="balanced",
            timeout_sec=state["step_timeout_sec"],
            context={
                "workspace": workspace,
                "topic": state["topic"],
                "mode": "focused",
                "round": round_num,
                "search_focus": search_focus,
            },
        )
        require_step(workspace, failed_status, "phase2_per_round_ingest", refresh)

        freshness = runner.run(
            f"freshness_check_round_{round_num}",
            build_freshness_check_prompt(workspace),
            model_tier="balanced",
            timeout_sec=state["step_timeout_sec"],
            context={"workspace": workspace, "round": round_num},
        )
        require_step(workspace, failed_status, "phase2_per_round_freshness", freshness)

        append_audit(workspace, "per_round_evidence_ingest", {"round": round_num})
        return {}

    def debate_prep(state: DebateState) -> dict:
        """Fan-out point before the parallel Pro/Con branches."""
        print(f"[{timestamp()}] Launching Pro and Con in parallel")
        return {}

    def make_debater(side: str):
        def debater_node(state: DebateState) -> dict:
            workspace = state["workspace_path"]
            round_num = state["current_round"]
            failed_status = f"failed_round_{round_num}"
            step_id = f"debate_turn_{side}_round_{round_num}"

            result = runner.run(
                step_id,
                build_debate_turn_prompt(
                    side=side,
                    round_num=round_num,
                    topic=state["topic"],
                    mode=state["mode"],
                    speculation=state["speculation"],
                    depth=state["depth"],
                    prev_round_context=_prev_round_context(round_num),
                    workspace=workspace,
                ),
                model_tier="balanced",
                timeout_sec=state["step_timeout_sec"],
                context={
                    "workspace": workspace,
                    "topic": state["topic"],
                    "side": side,
                    "round": round_num,
                    "mode": state["mode"],
                    "speculation": state["speculation"],
                    "depth": state["depth"],
                },
            )
            require_step(workspace, failed_status, "phase2_debate_turn", result)

            turn_path = _turn_path(workspace, round_num, side)
            if not os.path.exists(turn_path):
                fail_step(
                    workspace, failed_status, "phase2_validate_turn_output",
                    failed_result(
                        f"validate_{side}_turn_round_{round_num}",
                        "missing_output",
                        f"Missing turn file: {turn_path}",
                    ),
                )

            ok, _ = validate_json_file(turn_path, f"{side}_turn")
            if not ok:
                print(f"[{timestamp()}] Validation failed for {side}_turn, retrying...")
                validated = False
                for retry in range(2):
                    fix = runner.run(
                        f"debate_turn_{side}_round_{round_num}_retry_{retry + 1}",
                        build_debate_turn_fix_prompt(side, round_num, workspace),
                        model_tier="balanced",
                        timeout_sec=state["step_timeout_sec"],
                        context={
                            "workspace": workspace,
                            "topic": state["topic"],
                            "side": side,
                            "round": round_num,
                            "mode": state["mode"],
                            "speculation": state["speculation"],
                            "depth": state["depth"],
                            "fix_validation": True,
                        },
                    )
                    ok, _ = validate_json_file(turn_path, f"{side}_turn")
                    if fix.success and ok:
                        validated = True
                        break
                if not validated:
                    fail_step(
                        workspace, failed_status, "phase2_validate_turn_output",
                        failed_result(
                            f"validate_{side}_turn_round_{round_num}",
                            "json_validation_failed",
                            f"{side}_turn.json failed schema validation after retries",
                        ),
                    )

            turn = read_json(turn_path)
            summary = {
                "round": round_num,
                "side": side,
                "arguments_count": len(turn.get("arguments", [])),
                "rebuttals_count": len(turn.get("rebuttals", [])),
            }
            return {"pro_arguments" if side == "pro" else "con_arguments": [summary]}

        return debater_node

    def post_turns(state: DebateState) -> dict:
        round_num = state["current_round"]
        workspace = state["workspace_path"]
        append_audit(workspace, "pro_turn_complete", {"round": round_num})
        append_audit(workspace, "con_turn_complete", {"round": round_num})
        return {}

    def judge_audit(state: DebateState) -> dict:
        workspace = state["workspace_path"]
        round_num = state["current_round"]
        failed_status = f"failed_round_{round_num}"

        print(f"[{timestamp()}] Judge audit for round {round_num}")
        result = runner.run(
            f"judge_audit_round_{round_num}",
            build_judge_audit_prompt(round_num, workspace),
            model_tier="deep",
            timeout_sec=state["step_timeout_sec"],
            context={"workspace": workspace, "round": round_num},
        )
        require_step(workspace, failed_status, "phase2_judge_audit", result)

        judge_path = _judge_path(workspace, round_num)
        if not os.path.exists(judge_path):
            fail_step(
                workspace, failed_status, "phase2_validate_judge_output",
                failed_result(
                    f"validate_judge_ruling_round_{round_num}",
                    "missing_output",
                    f"Missing judge ruling file: {judge_path}",
                ),
            )
        ok, _ = validate_json_file(judge_path, "judge_ruling")
        if not ok:
            fail_step(
                workspace, failed_status, "phase2_validate_judge_output",
                failed_result(
                    f"validate_judge_ruling_round_{round_num}",
                    "json_validation_failed",
                    "judge_ruling.json failed schema validation",
                ),
            )

        append_audit(workspace, "judge_ruling_complete", {"round": round_num})
        ruling = read_json(judge_path)
        return {"judge_rulings": [{
            "round": round_num,
            "verifications": len(ruling.get("verification_results", [])),
            "mandatory_response_points": len(ruling.get("mandatory_response_points", [])),
            "causal_flags": len(ruling.get("causal_validity_flags", [])),
        }]}

    def post_round(state: DebateState) -> dict:
        """Claim ledger update, consistency gate, evidence merge (v2 step 2e)."""
        workspace = state["workspace_path"]
        round_num = state["current_round"]
        failed_status = f"failed_round_{round_num}"

        print(f"[{timestamp()}] Post-round processing")
        claim_update = runner.run(
            f"claim_ledger_update_round_{round_num}",
            build_claim_ledger_update_prompt(round_num, workspace),
            model_tier="balanced",
            timeout_sec=state["step_timeout_sec"],
            context={"workspace": workspace, "round": round_num},
        )
        require_step(workspace, failed_status, "phase2_claim_ledger_update", claim_update)

        claim_consistency = verify_claim_ledger_consistency(workspace, round_num)
        require_step(workspace, failed_status, "phase2_claim_consistency", claim_consistency)

        total_evidence = merge_new_evidence(workspace, round_num)

        update_config(workspace, {
            "current_round": round_num,
            "status": f"round_{round_num}_complete",
        })

        ledger_path = os.path.join(workspace, "claims", "claim_ledger.json")
        store_path = evidence_store_path(workspace)
        return {
            "status": f"round_{round_num}_complete",
            "claim_ledger": read_json(ledger_path) if os.path.exists(ledger_path) else [],
            "evidence_store": read_json(store_path) if os.path.exists(store_path) else [],
            "evidence_count": total_evidence,
        }

    def next_round(state: DebateState) -> dict:
        return {"current_round": state["current_round"] + 1}

    def final_synthesis(state: DebateState) -> dict:
        workspace = state["workspace_path"]
        report_path = debate_report_path(workspace)
        report_json = final_report_path(workspace)
        backup_path = report_backup_path(workspace)

        print(f"\n{'='*60}")
        print("PHASE 3: FINAL OUTPUT")
        print(f"{'='*60}")

        if os.path.exists(report_path):
            shutil.copyfile(report_path, backup_path)

        final_timeout = max(state["step_timeout_sec"], 900)
        result = runner.run(
            "final_synthesis",
            build_final_synthesis_prompt(workspace),
            model_tier="deep",
            timeout_sec=final_timeout,
            context={
                "workspace": workspace,
                "topic": state["topic"],
                "rounds": state["rounds"],
                "language": state["language"],
                "output_format": state.get("output_format", "full_report"),
            },
        )

        if not result.success:
            # Fallback path: deterministic markdown render only if final_report.json exists + valid.
            if os.path.exists(report_json) and validate_json_file(report_json, "final_report")[0]:
                append_audit(workspace, "final_synthesis_fallback", {
                    "reason": result.reason,
                    "error_type": result.error_type,
                })
                render_res = run_renderer(workspace)
                require_step(workspace, "failed_report_validation", "phase3_render_fallback", render_res)
            else:
                fail_step(workspace, "failed_final_synthesis", "phase3_final_synthesis", result)
        return {}

    def report_gate(state: DebateState) -> dict:
        workspace = state["workspace_path"]
        report_path = debate_report_path(workspace)
        report_json = final_report_path(workspace)
        backup_path = report_backup_path(workspace)

        if not os.path.exists(report_json):
            fail_step(
                workspace, "failed_report_validation", "phase3_validate_final_report",
                failed_result(
                    "validate_final_report",
                    "missing_output",
                    f"Missing final_report.json at {report_json}",
                ),
            )
        ok, _ = validate_json_file(report_json, "final_report")
        if not ok:
            fail_step(
                workspace, "failed_report_validation", "phase3_validate_final_report",
                failed_result(
                    "validate_final_report",
                    "json_validation_failed",
                    "final_report.json failed schema validation",
                ),
            )

        if not os.path.exists(report_path):
            if os.path.exists(backup_path):
                shutil.copyfile(backup_path, report_path)
            fail_step(
                workspace, "failed_report_validation", "phase3_validate_debate_report",
                failed_result(
                    "validate_debate_report",
                    "missing_output",
                    f"Missing debate_report.md at {report_path}",
                ),
            )

        ok, _ = validate_debate_report_file(report_path)
        if not ok:
            if os.path.exists(backup_path):
                shutil.copyfile(backup_path, report_path)
            fail_step(
                workspace, "failed_report_validation", "phase3_validate_debate_report",
                failed_result(
                    "validate_debate_report",
                    "report_validation_failed",
                    "debate_report.md failed Section 8 format validation",
                ),
            )

        if os.path.exists(backup_path):
            os.remove(backup_path)

        update_config(workspace, {"status": "complete"})
        append_audit(workspace, "report_generated", {"workspace": workspace})

        print(f"\n[{timestamp()}] Debate complete!")
        print(f"  Report: {report_path}")
        print(f"  JSON:   {report_json}")
        return {"status": "complete"}

    def quality_assessment(state: DebateState) -> dict:
        metrics = assess_debate_quality(state["workspace_path"], state["topic"], state["rounds"])
        return {"quality_metrics": metrics}

    return {
        "initialize_debate": initialize_debate,
        "source_ingest_initial": source_ingest_initial,
        "freshness_check_initial": freshness_check_initial,
        "evidence_gate": evidence_gate,
        "source_ingest_retry": source_ingest_retry,
        "round_entry": round_entry,
        "per_round_ingest": per_round_ingest,
        "debate_prep": debate_prep,
        "pro_debater": make_debater("pro"),
        "con_debater": make_debater("con"),
        "post_turns": post_turns,
        "judge_audit": judge_audit,
        "post_round": post_round,
        "next_round": next_round,
        "final_synthesis": final_synthesis,
        "report_gate": report_gate,
        "quality_assessment": quality_assessment,
    }
