"""Agent runner contract and step results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class StepResult:
    """Outcome of a single dispatched agent step (v2 ``StepResult`` port)."""

    step_id: str
    success: bool
    error_type: str = ""
    reason: str = ""
    exit_code: Optional[int] = None


class AgentRunner(Protocol):
    """Transport used to execute one agent capability step.

    Implementations: :class:`~critical_debater.models.cli.ClaudeCliRunner`,
    :class:`~critical_debater.models.cli.CodexCliRunner` (Phase 1), and
    API-backed providers planned for Phase 2.
    """

    runtime: str

    def run(
        self,
        step_id: str,
        prompt: str,
        model_tier: str = "balanced",
        timeout_sec: int = 300,
    ) -> StepResult:
        ...
