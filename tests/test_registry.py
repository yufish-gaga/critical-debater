"""Tests for the model registry and CLI runner configuration."""

from __future__ import annotations

from critical_debater.models.base import StepResult
from critical_debater.models.cli import effective_timeout
from critical_debater.models.registry import MODEL_MAP, NoneRunner, get_runner, load_model_map, resolve_model


def test_default_model_map_matches_v2():
    assert MODEL_MAP["claude"] == {"fast": "sonnet", "balanced": "sonnet", "deep": "opus"}
    assert MODEL_MAP["codex"]["fast"] == "gpt-5.2-codex"


def test_resolve_model_tier_and_fallback():
    assert resolve_model("deep", "claude") == "opus"
    assert resolve_model("balanced", "codex") == "gpt-5.3-codex"
    # Unknown tier passes through unchanged (v2 tier_to_model parity).
    assert resolve_model("gpt-x", "claude") == "gpt-x"


def test_load_model_map_yaml_override(tmp_path, monkeypatch):
    cfg = tmp_path / "models.yaml"
    cfg.write_text("tiers:\n  claude:\n    deep: opus-4-custom\n", encoding="utf-8")
    monkeypatch.setenv("CRITICAL_DEBATER_MODELS_CONFIG", str(cfg))
    model_map = load_model_map()
    assert model_map["claude"]["deep"] == "opus-4-custom"
    assert model_map["claude"]["fast"] == "sonnet"  # built-in fallback preserved


def test_codex_timeout_floors():
    assert effective_timeout("source_ingest_round_0", "codex", 300) == 1200
    assert effective_timeout("judge_audit_round_1", "codex", 300) == 900
    assert effective_timeout("final_synthesis", "codex", 300) == 1800
    assert effective_timeout("freshness_check_0", "codex", 300) == 600
    assert effective_timeout("debate_turn_pro_round_1", "codex", 300) == 900
    # Claude runtime keeps the caller timeout.
    assert effective_timeout("source_ingest_round_0", "claude", 300) == 300


def test_get_runner_none(monkeypatch):
    monkeypatch.delenv("DEBATER_RUNTIME", raising=False)
    runner = get_runner("none")
    assert isinstance(runner, NoneRunner)
    result = runner.run("some_step", "prompt")
    assert isinstance(result, StepResult)
    assert not result.success
    assert result.error_type == "runtime_missing"
