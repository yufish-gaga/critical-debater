"""Orchestration errors."""


class DebateStepFailure(RuntimeError):
    """A graph step failed hard; orchestration stops (v2 ``fail_step`` semantics).

    Raised *after* the failure has been recorded to the audit trail and the
    workspace config status has been updated, matching v2 behavior.
    """

    def __init__(self, step_id: str, stage: str, error_type: str, reason: str, status: str):
        self.step_id = step_id
        self.stage = stage
        self.error_type = error_type
        self.reason = reason
        self.status = status
        super().__init__(f"{step_id} failed at {stage}: {error_type} {reason}")
