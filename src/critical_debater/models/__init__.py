"""Model / agent-runtime abstraction layer (Phase 2 groundwork).

Phase 1 keeps the v2 execution model: agent capabilities are dispatched as
CLI subprocesses (``claude -p`` / ``codex exec``). The :class:`AgentRunner`
protocol isolates the graph from that transport so Phase 2 can add direct
API-backed providers (OpenAI / Anthropic / local models) without touching the
graph.
"""

from .base import AgentRunner, StepResult
from .registry import MODEL_MAP, get_runner, resolve_model

__all__ = [
    "AgentRunner",
    "StepResult",
    "MODEL_MAP",
    "get_runner",
    "resolve_model",
]
