"""Runtime selection and model-tier resolution.

Model tier → concrete model mapping lives in ``config/models.yaml`` (v3) with
a built-in fallback identical to v2's ``MODEL_MAP``. Phase 2 will extend this
registry with provider-level configuration (OpenAI / Anthropic / local).
"""

from __future__ import annotations

import os
from typing import Optional

from .base import AgentRunner, StepResult

# v2 MODEL_MAP: generic tier → provider-specific model name.
MODEL_MAP: dict[str, dict[str, str]] = {
    "claude": {"fast": "sonnet", "balanced": "sonnet", "deep": "opus"},
    # Keep balanced/deep on Codex default model; use a lighter model for fast tier.
    "codex": {"fast": "gpt-5.2-codex", "balanced": "gpt-5.3-codex", "deep": "gpt-5.3-codex"},
}

CONFIG_ENV_VAR = "CRITICAL_DEBATER_MODELS_CONFIG"
CONFIG_REL_PATH = os.path.join("config", "models.yaml")


def load_model_map() -> dict[str, dict[str, str]]:
    """Load tier mapping from config/models.yaml when present, else built-in defaults."""
    path = os.environ.get(CONFIG_ENV_VAR) or (
        CONFIG_REL_PATH if os.path.exists(CONFIG_REL_PATH) else None
    )
    if not path or not os.path.exists(path):
        return MODEL_MAP
    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return MODEL_MAP
    tiers = data.get("tiers") or {}
    if not isinstance(tiers, dict) or not tiers:
        return MODEL_MAP
    merged = {runtime: dict(models) for runtime, models in MODEL_MAP.items()}
    for runtime, models in tiers.items():
        if isinstance(models, dict):
            merged.setdefault(runtime, {}).update(models)
    return merged


def resolve_model(tier: str, runtime: str) -> str:
    """Map generic tier name to provider-specific model name."""
    return load_model_map().get(runtime, {}).get(tier, tier)


class NoneRunner:
    """Runner used when no agent CLI is available; every step fails (v2 parity)."""

    runtime = "none"

    def run(self, step_id: str, prompt: str, model_tier: str = "balanced",
            timeout_sec: int = 300) -> StepResult:
        msg = "No agent runtime found (need 'claude' or 'codex' in PATH)"
        return StepResult(step_id=step_id, success=False, error_type="runtime_missing", reason=msg)


def get_runner(runtime: Optional[str] = None) -> AgentRunner:
    """Return the runner for the detected (or forced) runtime."""
    from .cli import ClaudeCliRunner, CodexCliRunner, detect_runtime

    detected = (runtime or detect_runtime()).lower()
    if detected == "claude":
        return ClaudeCliRunner()
    if detected == "codex":
        return CodexCliRunner()
    return NoneRunner()
