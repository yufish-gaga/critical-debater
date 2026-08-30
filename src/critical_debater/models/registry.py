"""Provider registry, role routing, and runner selection (v3 Phase 2).

Configuration lives in ``config/models.yaml`` (path overridable via
``CRITICAL_DEBATER_MODELS_CONFIG``)::

    runtime: auto            # api | cli | auto
    providers:
      deepseek:
        type: openai_compatible
        base_url: https://api.deepseek.com/v1
        api_key_env: DEEPSEEK_API_KEY
        models: {fast: deepseek-chat, balanced: deepseek-chat, deep: deepseek-reasoner}
      anthropic:
        type: anthropic
        api_key_env: ANTHROPIC_API_KEY
        models: {fast: ..., balanced: ..., deep: ...}
    role_models:             # which provider each debate role uses
      pro:    {provider: deepseek, tier: balanced}
      judge:  {provider: anthropic, tier: deep}
    search:
      provider: tavily
      api_key_env: TAVILY_API_KEY

API keys are never stored in config files — only the *name* of the
environment variable is. When no config exists, sensible built-in presets
(DeepSeek / Kimi / GLM / Qwen / OpenAI / Anthropic / Ollama) apply.
"""

from __future__ import annotations

import os
from typing import Optional

from .base import AgentRunner, StepResult

# v2 MODEL_MAP: generic tier → CLI-runtime model name (Phase 1 transport).
MODEL_MAP: dict[str, dict[str, str]] = {
    "claude": {"fast": "sonnet", "balanced": "sonnet", "deep": "opus"},
    # Keep balanced/deep on Codex default model; use a lighter model for fast tier.
    "codex": {"fast": "gpt-5.2-codex", "balanced": "gpt-5.3-codex", "deep": "gpt-5.3-codex"},
}

CONFIG_ENV_VAR = "CRITICAL_DEBATER_MODELS_CONFIG"
RUNTIME_ENV_VAR = "CRITICAL_DEBATER_RUNTIME"
CONFIG_REL_PATH = os.path.join("config", "models.yaml")

# Built-in provider presets used when models.yaml has no ``providers`` section.
# All OpenAI-compatible entries differ only in base_url / key env / models.
DEFAULT_PROVIDERS: dict[str, dict] = {
    "deepseek": {
        "type": "openai_compatible",
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "models": {"fast": "deepseek-chat", "balanced": "deepseek-chat", "deep": "deepseek-reasoner"},
    },
    "moonshot": {
        "type": "openai_compatible",
        "base_url": "https://api.moonshot.cn/v1",
        "api_key_env": "MOONSHOT_API_KEY",
        "models": {"fast": "kimi-k2-0905-preview", "balanced": "kimi-k2-0905-preview", "deep": "kimi-k2-0905-preview"},
    },
    "zhipu": {
        "type": "openai_compatible",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_env": "ZHIPU_API_KEY",
        "models": {"fast": "glm-4.5-air", "balanced": "glm-4.5", "deep": "glm-4.5"},
    },
    "openai": {
        "type": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "models": {"fast": "gpt-4o-mini", "balanced": "gpt-4o", "deep": "gpt-4o"},
    },
    "anthropic": {
        "type": "anthropic",
        "api_key_env": "ANTHROPIC_API_KEY",
        "models": {"fast": "claude-sonnet-4-5", "balanced": "claude-sonnet-4-5", "deep": "claude-opus-4-1"},
    },
    "ollama": {
        "type": "openai_compatible",
        "base_url": "http://localhost:11434/v1",
        "api_key_env": None,
        "api_key_required": False,
        "models": {"fast": "qwen2.5:7b", "balanced": "qwen2.5:14b", "deep": "qwen2.5:32b"},
    },
}

DEFAULT_ROLE_MODELS: dict[str, dict] = {
    "ingest": {"provider": "deepseek", "tier": "balanced"},
    "pro": {"provider": "deepseek", "tier": "balanced"},
    "con": {"provider": "deepseek", "tier": "balanced"},
    "judge": {"provider": "deepseek", "tier": "deep"},
    "synthesis": {"provider": "deepseek", "tier": "deep"},
}

# step_id prefix → role
STEP_ROLES: tuple[tuple[str, str], ...] = (
    ("debate_turn_pro", "pro"),
    ("debate_turn_con", "con"),
    ("judge_audit", "judge"),
    ("final_synthesis", "synthesis"),
    ("claim_ledger_update", "ingest"),
    ("freshness_check", "ingest"),
    ("source_ingest", "ingest"),
)


def role_for_step(step_id: str) -> str:
    for prefix, role in STEP_ROLES:
        if step_id.startswith(prefix):
            return role
    return "ingest"


# --- config loading ----------------------------------------------------------


def _config_path() -> Optional[str]:
    path = os.environ.get(CONFIG_ENV_VAR)
    if path:
        return path
    return CONFIG_REL_PATH if os.path.exists(CONFIG_REL_PATH) else None


def load_debate_config() -> dict:
    """Load the full models.yaml configuration (empty dict when absent)."""
    path = _config_path()
    if not path or not os.path.exists(path):
        return {}
    try:
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def load_model_map() -> dict[str, dict[str, str]]:
    """Tier mapping for CLI runners: yaml ``tiers:`` over built-in defaults."""
    config = load_debate_config()
    tiers = config.get("tiers") or {}
    if not isinstance(tiers, dict) or not tiers:
        return MODEL_MAP
    merged = {runtime: dict(models) for runtime, models in MODEL_MAP.items()}
    for runtime, models in tiers.items():
        if isinstance(models, dict):
            merged.setdefault(runtime, {}).update(models)
    return merged


def resolve_model(tier: str, runtime: str) -> str:
    """Map generic tier name to provider-specific model name (CLI runners)."""
    return load_model_map().get(runtime, {}).get(tier, tier)


# --- provider construction ---------------------------------------------------


class ProviderRegistry:
    """Resolves a debate role + tier to a concrete provider instance."""

    def __init__(self, provider_specs: dict[str, dict], role_models: dict[str, dict],
                 default_provider: str):
        self.provider_specs = provider_specs
        self.role_models = role_models
        self.default_provider = default_provider
        self._cache: dict[tuple[str, str, str], tuple] = {}

    def resolve(self, role: str, tier: str = "balanced") -> tuple:
        """Return (provider_instance, model_name) for a role/tier pair."""
        role_cfg = self.role_models.get(role) or {}
        pname = role_cfg.get("provider") or self.default_provider
        effective_tier = role_cfg.get("tier") or tier
        spec = self.provider_specs.get(pname)
        if spec is None:
            raise KeyError(f"unknown provider '{pname}' (roles may reference it in role_models)")
        model = (spec.get("models") or {}).get(effective_tier) or role_cfg.get("model") or effective_tier

        key = (pname, model, str(role_cfg.get("tier", "")))
        if key not in self._cache:
            self._cache[key] = (build_provider(pname, spec, model=model), model)
        provider, resolved_model = self._cache[key]
        return provider, resolved_model


def build_provider(name: str, spec: dict, model: str):
    from .provider import AnthropicProvider, OpenAICompatProvider, ProviderConfigError

    ptype = (spec.get("type") or "").lower()
    api_key = spec.get("api_key") or ""
    api_key_env = spec.get("api_key_env")
    if not api_key and api_key_env:
        api_key = os.environ.get(api_key_env, "")
    common = {
        "timeout_sec": int(spec.get("timeout_sec", 300)),
        "max_tokens": spec.get("max_tokens"),
        "temperature": float(spec.get("temperature", 0.2)),
    }
    if ptype in ("openai_compatible", "openai", "openai-compatible"):
        return OpenAICompatProvider(
            model=model,
            base_url=spec.get("base_url") or "",
            api_key=api_key,
            api_key_required=bool(spec.get("api_key_required", True)),
            **common,
        )
    if ptype == "anthropic":
        return AnthropicProvider(model=model, api_key=api_key,
                                 base_url=spec.get("base_url") or "", **common)
    raise ProviderConfigError(f"unknown provider type '{ptype}' for provider '{name}'")


def build_registry(config: dict) -> ProviderRegistry:
    """Build the registry from config, falling back to built-in presets."""
    providers_cfg = config.get("providers") or {}
    specs: dict[str, dict] = {}
    for name, spec in DEFAULT_PROVIDERS.items():
        specs[name] = dict(spec)
    for name, spec in providers_cfg.items():
        if isinstance(spec, dict):
            base = dict(specs.get(name, {}))
            base.update(spec)
            specs[name] = base

    role_models = {role: dict(cfg) for role, cfg in DEFAULT_ROLE_MODELS.items()}
    for role, cfg in (config.get("role_models") or {}).items():
        if isinstance(cfg, dict):
            role_models.setdefault(role, {}).update(cfg)

    default_provider = config.get("default_provider") or role_models.get("ingest", {}).get("provider") or "deepseek"
    return ProviderRegistry(specs, role_models, default_provider)


# --- runner selection --------------------------------------------------------


def _provider_usable(spec: dict) -> bool:
    """A provider is usable when it needs no key or its key is resolvable."""
    if spec.get("api_key_required") is False or not spec.get("api_key_env"):
        return True
    return bool(spec.get("api_key") or os.environ.get(spec["api_key_env"], ""))


def resolve_runtime(config: Optional[dict] = None) -> str:
    """Decide api vs cli transport: env > yaml ``runtime:`` > auto-detect."""
    config = config if config is not None else load_debate_config()
    forced = os.environ.get(RUNTIME_ENV_VAR, "").strip().lower()
    if forced in {"api", "cli"}:
        return forced
    configured = (config.get("runtime") or "auto").strip().lower()
    if configured in {"api", "cli"}:
        return configured
    # auto: prefer the API layer when any key-backed provider has a resolvable
    # key; otherwise fall back to the claude/codex CLI (NoneRunner when neither
    # exists, matching v2's runtime_missing failure mode).
    registry = build_registry(config)
    has_api_key = any(
        spec.get("api_key_env") and _provider_usable(spec)
        for spec in registry.provider_specs.values()
    )
    return "api" if has_api_key else "cli"


def get_runner(runtime: Optional[str] = None) -> AgentRunner:
    """Return the runner for the requested (or resolved) transport."""
    if runtime is not None:
        lowered = runtime.lower()
        if lowered == "none":
            return NoneRunner()
        if lowered == "api":
            from .api_runner import LLMAgentRunner

            return LLMAgentRunner.from_config()
        if lowered in {"claude", "codex"}:
            from .cli import ClaudeCliRunner, CodexCliRunner

            return ClaudeCliRunner() if lowered == "claude" else CodexCliRunner()

    mode = resolve_runtime()
    if mode == "api":
        from .api_runner import LLMAgentRunner

        return LLMAgentRunner.from_config()
    from .cli import ClaudeCliRunner, CodexCliRunner, detect_runtime

    detected = detect_runtime()
    if detected == "claude":
        return ClaudeCliRunner()
    if detected == "codex":
        return CodexCliRunner()
    return NoneRunner()


class NoneRunner:
    """Runner used when no transport is available; every step fails (v2 parity)."""

    runtime = "none"

    def run(self, step_id: str, prompt: str, model_tier: str = "balanced",
            timeout_sec: int = 300, context=None) -> StepResult:
        msg = "No agent runtime found (configure a provider API key, or install 'claude'/'codex' CLI)"
        return StepResult(step_id=step_id, success=False, error_type="runtime_missing", reason=msg)
