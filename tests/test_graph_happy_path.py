"""End-to-end happy-path graph run with the scripted fake runner (2 rounds, hybrid refresh)."""

from __future__ import annotations

import os

from critical_debater.config import DebateOptions
from critical_debater.graph.runner import run_debate
from critical_debater.validation import validate_debate_report_file
from critical_debater.workspace import config_path, read_audit, read_json

from conftest import REPORT_MD_FIXTURE
from fake_agent import FakeScriptedRunner


def test_happy_path_two_rounds(workspace, opts):
    runner = FakeScriptedRunner(initial_evidence=10, retry_evidence=0, report_md_fixture=REPORT_MD_FIXTURE)
    final_state = run_debate(workspace, opts, runner=runner)

    # Final state mirrors.
    assert final_state["status"] == "complete"
    assert final_state["current_round"] == 2
    assert len(final_state["judge_rulings"]) == 2
    assert len(final_state["pro_arguments"]) == 2
    assert len(final_state["con_arguments"]) == 2
    assert final_state["quality_metrics"]["rounds_completed"] == 2

    # Config file status.
    cfg = read_json(config_path(workspace))
    assert cfg["status"] == "complete"
    assert cfg["current_round"] == 2

    # Artifacts exist.
    assert os.path.exists(os.path.join(workspace, "reports", "final_report.json"))
    assert os.path.exists(os.path.join(workspace, "reports", "debate_report.md"))
    assert os.path.exists(os.path.join(workspace, "reports", "quality_metrics.json"))
    # Backup removed on success.
    assert not os.path.exists(os.path.join(workspace, "reports", "debate_report.pre_final_synthesis.bak.md"))

    # Evidence: initial 10 + 1 new per turn per round (4 turns) = 14.
    store = read_json(os.path.join(workspace, "evidence", "evidence_store.json"))
    assert len(store) == 14
    round2_new = [e for e in store if e.get("discovered_at_round") == 2]
    assert len(round2_new) == 2
    assert all(e["discovered_by"] in {"pro", "con"} for e in round2_new)

    # Audit trail lifecycle.
    actions = [e["action"] for e in read_audit(workspace)]
    for expected in [
        "workspace_initialized",
        "round_started",
        "pro_turn_complete",
        "con_turn_complete",
        "judge_ruling_complete",
        "per_round_evidence_ingest",
        "evidence_merged_from_turn",
        "claim_verification_applied",
        "report_generated",
    ]:
        assert expected in actions, f"missing audit action {expected}"
    assert "step_failed" not in actions

    # Dispatch log: model tiers and per-round step ids.
    tiers = {step_id: tier for step_id, tier in runner.calls}
    assert tiers["judge_audit_round_1"] == "deep"
    assert tiers["judge_audit_round_2"] == "deep"
    assert tiers["final_synthesis"] == "deep"
    assert tiers["source_ingest_round_0"] == "balanced"
    assert "source_ingest_round_2" in tiers      # hybrid refresh on round 2
    assert "freshness_check_round_2" in tiers
    assert "source_ingest_round_1" not in tiers  # hybrid: no refresh on round 1
    assert "source_ingest_retry_1" not in tiers  # evidence gate passed first try

    # Report fixture passes the Section 8 validator.
    ok, msg = validate_debate_report_file(os.path.join(workspace, "reports", "debate_report.md"))
    assert ok, msg


def test_happy_path_upfront_only_skips_refresh(workspace):
    opts = DebateOptions(topic="Test topic", rounds=1, min_evidence=5, evidence_refresh="upfront_only")
    runner = FakeScriptedRunner(initial_evidence=10, report_md_fixture=REPORT_MD_FIXTURE)
    run_debate(workspace, opts, runner=runner)
    step_ids = {step_id for step_id, _ in runner.calls}
    assert "source_ingest_round_1" not in step_ids
    assert "per_round_evidence_ingest" not in [e["action"] for e in read_audit(workspace)]


def test_evidence_gate_retry_loop_then_success(workspace):
    """Initial ingest below minimum → broaden retry → gate passes."""
    opts = DebateOptions(topic="Test topic", rounds=1, min_evidence=5)
    runner = FakeScriptedRunner(initial_evidence=3, retry_evidence=4, report_md_fixture=REPORT_MD_FIXTURE)
    final_state = run_debate(workspace, opts, runner=runner)

    assert final_state["status"] == "complete"
    step_ids = [step_id for step_id, _ in runner.calls]
    assert "source_ingest_retry_1" in step_ids
    store = read_json(os.path.join(workspace, "evidence", "evidence_store.json"))
    assert len(store) == 3 + 4 + 2  # initial + retry + 1 new evidence per turn (2 turns)
