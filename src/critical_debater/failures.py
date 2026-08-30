"""Hard-failure handling (v2 ``fail_step`` / ``require_step`` ports)."""

from __future__ import annotations

from typing import Optional

from .errors import DebateStepFailure
from .models.base import StepResult
from .workspace import append_audit, update_config


def fail_step(workspace: str, status: str, stage: str, result: StepResult) -> None:
    """Record a hard failure in the audit trail + config, then raise."""
    details = {
        "step_id": result.step_id,
        "stage": stage,
        "error_type": result.error_type or "failed",
        "reason": result.reason,
        "exit_code": result.exit_code,
        "status": status,
    }
    append_audit(workspace, "step_failed", details)
    update_config(workspace, {"status": status})
    raise DebateStepFailure(
        step_id=result.step_id,
        stage=stage,
        error_type=result.error_type or "failed",
        reason=result.reason,
        status=status,
    )


def require_step(workspace: str, status: str, stage: str, result: StepResult) -> None:
    if result.success:
        return
    fail_step(workspace, status, stage, result)


def failed_result(step_id: str, error_type: str, reason: str,
                  exit_code: Optional[int] = None) -> StepResult:
    return StepResult(step_id=step_id, success=False, error_type=error_type,
                      reason=reason, exit_code=exit_code)
