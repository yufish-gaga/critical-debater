"""Agent runner contract and step results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol

# Structured parameters a node attaches to a dispatch (workspace, topic, side,
# round, ...). CLI runners ignore it; API-backed runners use it instead of
# parsing the prompt text.
Context = dict[str, Any]


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
    :class:`~critical_debater.models.cli.CodexCliRunner` (Phase 1 CLI
    transport), and :class:`~critical_debater.models.api_runner.LLMAgentRunner`
    (Phase 2 API providers: DeepSeek / OpenAI-compatible / Anthropic / local).
    """

    runtime: str

    def run(
        self,
        step_id: str,
        prompt: str,
        model_tier: str = "balanced",
        timeout_sec: int = 300,
        context: Optional[Context] = None,
    ) -> StepResult:
        ...
