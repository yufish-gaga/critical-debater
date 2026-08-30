"""Failure-path tests: hard stops record audit + config status, then raise (v2 parity)."""

from __future__ import annotations

import os

import pytest

from critical_debater.config import DebateOptions
from critical_debater.errors import DebateStepFailure
from critical_debater.graph.runner import run_debate
from critical_debater.workspace import config_path, read_audit, read_json

from conftest import REPORT_MD_FIXTURE
from fake_agent import FakeScriptedRunner


def _config_status(workspace: str) -> str:
    return read_json(config_path(workspace))["status"]


def _failed_steps(workspace: str) -> list[dict]:
    return [e for e in read_audit(workspace) if e["action"] == "step_failed"]


def test_insufficient_evidence_after_retries(workspace):
    opts = DebateOptions(topic="Test topic", rounds=1, min_evidence=5, source_retries=2)
    runner = FakeScriptedRunner(initial_evidence=1, retry_evidence=1)
    with pytest.raises(DebateStepFailure) as excinfo:
        run_debate(workspace, opts, runner=runner)
    failure = excinfo.value
    assert failure.status == "failed_initialization"
    assert failure.error_type == "insufficient_evidence"
    assert failure.stage == "phase1_min_evidence"
    assert _config_status(workspace) == "failed_initialization"
    failed = _failed_steps(workspace)
    assert failed and failed[-1]["details"]["step_id"] == "source_ingest_min_evidence_gate"
    # Exactly source_retries broaden attempts were made.
    retry_ids = [sid for sid, _ in runner.calls if sid.startswith("source_ingest_retry_")]
    assert retry_ids == ["source_ingest_retry_1", "source_ingest_retry_2"]


def test_debater_missing_output_fails_round(workspace, opts):
    runner = FakeScriptedRunner(initial_evidence=10, valid_turns=False)
    with pytest.raises(DebateStepFailure) as excinfo:
        run_debate(workspace, opts, runner=runner)
    assert excinfo.value.status == "failed_round_1"
    assert excinfo.value.error_type == "missing_output"
    assert excinfo.value.stage == "phase2_validate_turn_output"
    assert _config_status(workspace) == "failed_round_1"


def test_judge_missing_ruling_fails_round(workspace, opts):
    runner = FakeScriptedRunner(initial_evidence=10, judge_writes_ruling=False)
    with pytest.raises(DebateStepFailure) as excinfo:
        run_debate(workspace, opts, runner=runner)
    assert excinfo.value.status == "failed_round_1"
    assert excinfo.value.error_type == "missing_output"
    assert excinfo.value.stage == "phase2_validate_judge_output"


def test_final_synthesis_failure_without_json(workspace, opts):
    runner = FakeScriptedRunner(
        initial_evidence=10,
        report_md_fixture=REPORT_MD_FIXTURE,
        final_synthesis_ok=False,
        final_synthesis_writes_json=False,
    )
    with pytest.raises(DebateStepFailure) as excinfo:
        run_debate(workspace, opts, runner=runner)
    assert excinfo.value.status == "failed_final_synthesis"
    assert excinfo.value.stage == "phase3_final_synthesis"
    assert _config_status(workspace) == "failed_final_synthesis"


def test_final_synthesis_fallback_renders_report(workspace, opts):
    """LLM synthesis fails but valid final_report.json exists → deterministic renderer runs."""
    runner = FakeScriptedRunner(
        initial_evidence=10,
        final_synthesis_ok=False,
        final_synthesis_writes_json=True,
    )
    # The renderer needs round artifacts; the fake runner already produced them.
    final_state = run_debate(workspace, opts, runner=runner)
    assert final_state["status"] == "complete"
    actions = [e["action"] for e in read_audit(workspace)]
    assert "final_synthesis_fallback" in actions
    assert os.path.exists(os.path.join(workspace, "reports", "debate_report.md"))
