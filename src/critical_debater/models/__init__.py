"""Model / provider abstraction layer (v3 Phase 2).

Two transports implement :class:`AgentRunner`:

- CLI (Phase 1): capabilities dispatched as ``claude -p`` / ``codex exec``
  subprocesses.
- API (Phase 2): :class:`~critical_debater.models.api_runner.LLMAgentRunner`
  runs capabilities in-process through configured LLM providers —
  ``OpenAICompatProvider`` covers DeepSeek / Kimi / GLM / Qwen / OpenAI and
  local Ollama/vLLM endpoints, ``AnthropicProvider`` covers Claude.
"""

from .base import AgentRunner, Context, StepResult
from .provider import (
    AnthropicProvider,
    BaseLLMProvider,
    OpenAICompatProvider,
    ProviderConfigError,
    ProviderError,
    extract_json_object,
)
from .registry import MODEL_MAP, build_registry, get_runner, load_debate_config, resolve_model, resolve_runtime
from .search import SearchProvider, TavilySearchProvider, build_search_provider

__all__ = [
    "AgentRunner",
    "Context",
    "StepResult",
    "MODEL_MAP",
    "get_runner",
    "resolve_model",
    "resolve_runtime",
    "load_debate_config",
    "build_registry",
    "BaseLLMProvider",
    "OpenAICompatProvider",
    "AnthropicProvider",
    "ProviderError",
    "ProviderConfigError",
    "extract_json_object",
    "SearchProvider",
    "TavilySearchProvider",
    "build_search_provider",
]
