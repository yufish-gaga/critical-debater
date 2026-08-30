"""Deterministic fallback rendering for the debate report.

Port of ``run_renderer`` / ``report_backup_path`` from the v2 orchestrator.
When the LLM ``final_synthesis`` step fails but a schema-valid
``final_report.json`` exists, the deterministic renderer rebuilds
``debate_report.md`` from JSON artifacts.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ..models.base import StepResult

_RENDERER_NAME = "render-debate-report-from-json.py"


def _renderer_path() -> Path:
    """Locate the v2 renderer script relative to this repo checkout."""
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidate = ancestor / "critical-debater-suite" / "scripts" / _RENDERER_NAME
        if candidate.exists():
            return candidate
    return here.parents[3] / "critical-debater-suite" / "scripts" / _RENDERER_NAME


def debate_report_path(workspace: str) -> str:
    return os.path.join(workspace, "reports", "debate_report.md")


def final_report_path(workspace: str) -> str:
    return os.path.join(workspace, "reports", "final_report.json")


def report_backup_path(workspace: str) -> str:
    return os.path.join(workspace, "reports", "debate_report.pre_final_synthesis.bak.md")


def run_renderer(workspace: str) -> StepResult:
    """Run the deterministic renderer; returns a StepResult (v2 semantics)."""
    step_id = "render_debate_report_from_json"
    script_path = _renderer_path()
    try:
        proc = subprocess.run(
            ["python3", str(script_path), workspace],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return StepResult(
            step_id=step_id,
            success=False,
            error_type="renderer_missing",
            reason=f"Renderer script not found: {script_path}",
        )
    if proc.returncode != 0:
        return StepResult(
            step_id=step_id,
            success=False,
            error_type="renderer_failed",
            reason=(proc.stderr or proc.stdout or "renderer failed")[:500],
            exit_code=proc.returncode,
        )
    return StepResult(step_id=step_id, success=True, exit_code=0)
