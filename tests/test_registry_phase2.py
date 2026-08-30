"""Tests for provider registry, role routing, and runtime resolution (Phase 2)."""

from __future__ import annotations

import pytest

from critical_debater.models.provider import (
    AnthropicProvider,
    OpenAICompatProvider,
    ProviderConfigError,
)
from critical_debater.models.registry import (
    build_provider,
    build_registry,
    load_debate_config,
    resolve_runtime,
    role_for_step,
)


# --- role routing ------------------------------------------------------------


def test_role_for_step_mapping():
    assert role_for_step("debate_turn_pro_round_1") == "pro"
    assert role_for_step("debate_turn_con_round_2") == "con"
    assert role_for_step("judge_audit_round_1") == "judge"
    assert role_for_step("final_synthesis") == "synthesis"
    assert role_for_step("source_ingest_round_0") == "ingest"
    assert role_for_step("freshness_check_0") == "ingest"
    assert role_for_step("claim_ledger_update_round_1") == "ingest"
    assert role_for_step("mystery_step") == "ingest"


def test_default_registry_resolves_deepseek_models():
    registry = build_registry({})
    provider, model = registry.resolve("pro", "balanced")
    assert isinstance(provider, OpenAICompatProvider)
    assert provider.base_url == "https://api.deepseek.com/v1"
    assert model == "deepseek-chat"

    # Judge role overrides the tier: deep → deepseek-reasoner.
    _, judge_model = registry.resolve("judge", "balanced")
    assert judge_model == "deepseek-reasoner"


def test_registry_role_models_override():
    registry = build_registry({
        "role_models": {"judge": {"provider": "anthropic", "tier": "deep"}},
    })
    provider, model = registry.resolve("judge", "balanced")
    assert isinstance(provider, AnthropicProvider)
    assert model == "claude-opus-4-1"


def test_registry_unknown_provider_raises():
    registry = build_registry({"role_models": {"pro": {"provider": "nope"}}})
    with pytest.raises(KeyError):
        registry.resolve("pro", "balanced")


def test_build_provider_key_from_env(monkeypatch):
    monkeypatch.setenv("MY_KEY_ENV", "sk-xyz")
    provider = build_provider("custom", {
        "type": "openai_compatible",
        "base_url": "https://api.example.com/v1",
        "api_key_env": "MY_KEY_ENV",
    }, model="m")
    assert provider.api_key == "sk-xyz"


def test_build_provider_unknown_type():
    with pytest.raises(ProviderConfigError):
        build_provider("x", {"type": "carrier_pigeon"}, model="m")


# --- config loading ----------------------------------------------------------


def test_load_debate_config_from_yaml(tmp_path, monkeypatch):
    cfg_file = tmp_path / "models.yaml"
    cfg_file.write_text(
        "runtime: api\n"
        "role_models:\n"
        "  judge: {provider: kimi, tier: fast}\n"
        "providers:\n"
        "  kimi:\n"
        "    type: openai_compatible\n"
        "    base_url: https://api.moonshot.cn/v1\n"
        "    api_key_env: MOONSHOT_API_KEY\n"
        "    models: {fast: moonshot-v1-8k}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CRITICAL_DEBATER_MODELS_CONFIG", str(cfg_file))
    config = load_debate_config()
    assert config["runtime"] == "api"

    registry = build_registry(config)
    _, model = registry.resolve("judge", "balanced")
    assert model == "moonshot-v1-8k"


def test_custom_provider_merges_over_preset(tmp_path, monkeypatch):
    cfg_file = tmp_path / "models.yaml"
    cfg_file.write_text(
        "providers:\n"
        "  deepseek:\n"
        "    models: {balanced: deepseek-custom-model}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CRITICAL_DEBATER_MODELS_CONFIG", str(cfg_file))
    registry = build_registry(load_debate_config())
    _, model = registry.resolve("pro", "balanced")
    assert model == "deepseek-custom-model"


# --- runtime resolution ------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_runtime_env(monkeypatch):
    monkeypatch.delenv("CRITICAL_DEBATER_RUNTIME", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)


def test_resolve_runtime_env_override(monkeypatch):
    assert resolve_runtime({}) == "cli"  # no keys anywhere
    monkeypatch.setenv("CRITICAL_DEBATER_RUNTIME", "api")
    assert resolve_runtime({}) == "api"


def test_resolve_runtime_yaml_override(monkeypatch):
    assert resolve_runtime({"runtime": "api"}) == "api"


def test_resolve_runtime_auto_with_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-present")
    assert resolve_runtime({}) == "api"


def test_resolve_runtime_auto_without_key_prefers_cli():
    # No API keys → CLI transport (NoneRunner if no CLI installed).
    assert resolve_runtime({}) == "cli"
