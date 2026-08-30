"""Tests for workspace checkpoint resume (v3.1 断点恢复)."""

from __future__ import annotations

import os

import pytest

from critical_debater.config import DebateOptions
from critical_debater.errors import DebateStepFailure
from critical_debater.graph.runner import map_resume_entry, run_debate
from critical_debater.workspace import config_path, read_json, update_config

from conftest import REPORT_MD_FIXTURE
from fake_agent import FakeScriptedRunner


def _stage_failure(workspace: str, opts: DebateOptions, runner) -> str:
    """Run until the staged failure; return the config status."""
    with pytest.raises(DebateStepFailure):
        run_debate(workspace, opts, runner=runner)
    return read_json(config_path(workspace))["status"]


def test_map_resume_entry_matrix():
    assert map_resume_entry({"status": "initialized"}, 3) == "fresh"
    assert map_resume_entry({}, 3) == "fresh"
    assert map_resume_entry({"status": "in_progress", "current_round": 2}, 3) == "rounds"
    assert map_resume_entry({"status": "failed_round_2"}, 3) == "rounds"
    assert map_resume_entry({"status": "round_1_complete"}, 3) == "rounds"
    assert map_resume_entry({"status": "round_3_complete"}, 3) == "final"
    assert map_resume_entry({"status": "failed_final_synthesis"}, 3) == "final"
    assert map_resume_entry({"status": "failed_report_validation"}, 3) == "final"
    assert map_resume_entry({"status": "complete"}, 3) == "final"


def test_resume_after_failed_round_skips_completed_work(workspace, opts):
    opts.rounds = 2
    # Round 1 completes; the staged judge failure aborts round 2.
    class Round1OnlyRunner(FakeScriptedRunner):
        def run(self, step_id, prompt, model_tier="balanced", timeout_sec=300, context=None):
            if step_id == "judge_audit_round_2":
                return __import__("critical_debater.models.base", fromlist=["StepResult"]).StepResult(
                    step_id=step_id, success=False, error_type="simulated", reason="crash")
            return super().run(step_id, prompt, model_tier=model_tier,
                               timeout_sec=timeout_sec, context=context)

    status = _stage_failure(workspace, opts, Round1OnlyRunner(initial_evidence=10))
    assert status == "failed_round_2"
    assert "step_failed" in [e["action"] for e in __import__("critical_debater.workspace", fromlist=["read_audit"]).read_audit(workspace)]

    # Resume: only round 2 + final phases should dispatch.
    run2 = FakeScriptedRunner(initial_evidence=10, report_md_fixture=REPORT_MD_FIXTURE)
    final_state = run_debate(workspace, opts, runner=run2, resume=True)

    assert final_state["status"] == "complete"
    step_ids = [sid for sid, _ in run2.calls]
    assert "source_ingest_round_0" not in step_ids      # phase 1 skipped
    assert "debate_turn_pro_round_1" not in step_ids    # round 1 skipped
    assert "judge_audit_round_1" not in step_ids
    assert "source_ingest_round_2" in step_ids          # round 2 re-ran
    assert "judge_audit_round_2" in step_ids
    assert "final_synthesis" in step_ids
    assert read_json(config_path(workspace))["status"] == "complete"


def test_resume_after_final_failure_renders_report(workspace, opts):
    opts.rounds = 1
    _stage_failure(workspace, opts, FakeScriptedRunner(
        initial_evidence=10, final_synthesis_ok=False, final_synthesis_writes_json=False))

    run2 = FakeScriptedRunner(initial_evidence=10, report_md_fixture=REPORT_MD_FIXTURE)
    final_state = run_debate(workspace, opts, runner=run2, resume=True)

    assert final_state["status"] == "complete"
    step_ids = [sid for sid, _ in run2.calls]
    assert "final_synthesis" in step_ids
    assert not any(sid.startswith("debate_turn_") for sid in step_ids)  # rounds skipped
    assert not any(sid.startswith("source_ingest") for sid in step_ids)


def test_resume_in_progress_restarts_current_round(workspace, opts):
    opts.rounds = 1
    update_config(workspace, {"status": "in_progress", "current_round": 1})
    runner = FakeScriptedRunner(initial_evidence=10, report_md_fixture=REPORT_MD_FIXTURE)
    final_state = run_debate(workspace, opts, runner=runner, resume=True)

    assert final_state["status"] == "complete"
    step_ids = [sid for sid, _ in runner.calls]
    assert "source_ingest_round_0" not in step_ids       # phase 1 skipped
    assert "debate_turn_pro_round_1" in step_ids          # round 1 re-ran


def test_no_resume_restarts_fresh(workspace, opts):
    """Default behavior unchanged: a failed workspace restarts from scratch."""
    opts.rounds = 1
    _stage_failure(workspace, opts, FakeScriptedRunner(
        initial_evidence=10, final_synthesis_ok=False, final_synthesis_writes_json=False))
    runner = FakeScriptedRunner(initial_evidence=10, report_md_fixture=REPORT_MD_FIXTURE)
    final_state = run_debate(workspace, opts, runner=runner)  # resume defaults to False

    assert final_state["status"] == "complete"
    step_ids = [sid for sid, _ in runner.calls]
    assert "source_ingest_round_0" in step_ids
    assert "debate_turn_pro_round_1" in step_ids


def test_cli_resume_flag(workspace):
    """`--resume` reaches run_debate through main()."""
    from critical_debater import __main__ as cli

    captured = {}

    def fake_run_debate(ws, opts, runner=None, resume=False):
        captured["workspace"] = ws
        captured["resume"] = resume

    original = cli.run_debate
    cli.run_debate = fake_run_debate
    try:
        cli.main(["prog", workspace, "Test topic", "2", "--resume"])
    finally:
        cli.run_debate = original

    assert captured["resume"] is True
    assert captured["workspace"] == os.path.abspath(workspace)
    # Existing checkpoint untouched by a resume start with a topic arg.
    assert os.path.exists(config_path(workspace))
