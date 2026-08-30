"""Tests for file-based API key input (config/secrets.yaml)."""

from __future__ import annotations

import pytest

from critical_debater.models.provider import OpenAICompatProvider
from critical_debater.models.registry import (
    apply_secrets,
    build_registry,
    load_debate_config,
    load_secrets,
    resolve_runtime,
)


def _write(tmp_path, name: str, text: str):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


MODELS_YAML = """\
providers:
  deepseek:
    type: openai_compatible
    base_url: https://api.deepseek.com/v1
    api_key_env: DEEPSEEK_API_KEY
    models: {balanced: deepseek-chat}
search:
  provider: tavily
  api_key_env: TAVILY_API_KEY
"""

SECRETS_YAML = """\
providers:
  deepseek:
    api_key: "sk-from-secrets-file"
search:
  tavily:
    api_key: "tvly-from-secrets-file"
"""


@pytest.fixture()
def config_env(tmp_path, monkeypatch):
    models = _write(tmp_path, "models.yaml", MODELS_YAML)
    monkeypatch.setenv("CRITICAL_DEBATER_MODELS_CONFIG", models)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    return tmp_path, monkeypatch


def test_secrets_file_feeds_provider_keys(config_env):
    tmp_path, monkeypatch = config_env
    secrets = _write(tmp_path, "secrets.yaml", SECRETS_YAML)
    monkeypatch.setenv("CRITICAL_DEBATER_SECRETS_CONFIG", secrets)

    config = load_debate_config()
    assert config["providers"]["deepseek"]["api_key"] == "sk-from-secrets-file"
    assert config["search"]["api_key"] == "tvly-from-secrets-file"

    registry = build_registry(config)
    provider, _ = registry.resolve("pro", "balanced")
    assert isinstance(provider, OpenAICompatProvider)
    assert provider.api_key == "sk-from-secrets-file"


def test_models_yaml_explicit_key_wins_over_secrets(config_env):
    tmp_path, monkeypatch = config_env
    models = _write(tmp_path, "models.yaml", MODELS_YAML.replace(
        "    api_key_env: DEEPSEEK_API_KEY",
        '    api_key: "sk-explicit-in-models"\n    api_key_env: DEEPSEEK_API_KEY'))
    monkeypatch.setenv("CRITICAL_DEBATER_MODELS_CONFIG", models)
    monkeypatch.setenv("CRITICAL_DEBATER_SECRETS_CONFIG",
                       _write(tmp_path, "secrets.yaml", SECRETS_YAML))

    registry = build_registry(load_debate_config())
    provider, _ = registry.resolve("pro", "balanced")
    assert provider.api_key == "sk-explicit-in-models"


def test_env_var_still_works_without_secrets(config_env):
    tmp_path, monkeypatch = config_env
    monkeypatch.setenv("CRITICAL_DEBATER_SECRETS_CONFIG",
                       str(tmp_path / "does-not-exist.yaml"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")

    registry = build_registry(load_debate_config())
    provider, _ = registry.resolve("pro", "balanced")
    assert provider.api_key == "sk-from-env"


def test_secrets_key_activates_auto_runtime(config_env):
    tmp_path, monkeypatch = config_env
    monkeypatch.setenv("CRITICAL_DEBATER_SECRETS_CONFIG",
                       _write(tmp_path, "secrets.yaml", SECRETS_YAML))
    # A key pasted into the secrets file is enough for auto → api.
    assert resolve_runtime(load_debate_config()) == "api"


def test_apply_secrets_does_not_mutate_input():
    config = {"providers": {"deepseek": {"api_key": ""}}, "search": {"provider": "tavily"}}
    secrets = {"providers": {"deepseek": {"api_key": "sk-x"}},
               "search": {"tavily": {"api_key": "tvly-x"}}}
    merged = apply_secrets(config, secrets)
    assert config["providers"]["deepseek"]["api_key"] == ""          # input untouched
    assert merged["providers"]["deepseek"]["api_key"] == "sk-x"
    assert merged["search"]["api_key"] == "tvly-x"


def test_load_secrets_missing_file_returns_empty(tmp_path):
    assert load_secrets(str(tmp_path / "nope.yaml")) == {}


def test_repo_secrets_yaml_is_gitignored():
    from pathlib import Path

    gitignore = Path(__file__).resolve().parents[1] / ".gitignore"
    assert "config/secrets.yaml" in gitignore.read_text(encoding="utf-8")
    example = Path(__file__).resolve().parents[1] / "config" / "secrets.example.yaml"
    assert example.exists()  # template is committed
