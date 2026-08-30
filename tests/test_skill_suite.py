"""Tests for the v3 skill suite: discovery, generation sync, assets, install check."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from critical_debater.paths import SUITE_DIR_NAMES, capability_path, find_suite_dir

SUITE_ROOT = Path(__file__).resolve().parents[1] / "critical-debater-v3-suite"
BUILD_SCRIPT = SUITE_ROOT / "scripts" / "build-suite.py"


def test_suite_assets_present():
    assert (SUITE_ROOT / "SKILL.md").exists()
    assert (SUITE_ROOT / "core" / "skill-core.md").exists()
    assert (SUITE_ROOT / "capabilities" / "debate-turn.md").exists()
    assert (SUITE_ROOT / "references" / "data-contracts.md").exists()
    assert (SUITE_ROOT / "scripts" / "render-debate-report-from-json.py").exists()
    assert (SUITE_ROOT / "scripts" / "check-install.sh").exists()
    for adapter in ("claude-code", "codex", "openclaw"):
        assert (SUITE_ROOT / "adapters" / adapter / "SKILL.md").exists()


def test_generated_files_match_core():
    result = subprocess.run(
        ["python3", str(BUILD_SCRIPT), "--check"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_skill_md_frontmatter():
    text = (SUITE_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "name: critical-debater-v3-suite" in text
    assert 'version: "3.1.0"' in text
    assert "langgraph" in text  # description mentions the orchestrator


def test_capabilities_copies_match_v2_suite():
    v2_caps = SUITE_ROOT.parent / "critical-debater-suite" / "capabilities"
    v3_caps = SUITE_ROOT / "capabilities"
    assert {p.name for p in v2_caps.glob("*.md")} == {p.name for p in v3_caps.glob("*.md")}
    for src in v2_caps.glob("*.md"):
        assert (v3_caps / src.name).read_bytes() == src.read_bytes(), src.name


def test_find_suite_dir_prefers_v3_suite(monkeypatch, tmp_path):
    from critical_debater import paths

    # Simulate a checkout root containing both suites; v3 must win.
    root = tmp_path / "repo"
    for name in SUITE_DIR_NAMES:
        (root / name / "capabilities").mkdir(parents=True)

    monkeypatch.setattr(paths, "_candidate_roots", lambda: [root])
    assert paths.find_suite_dir() == root / "critical-debater-v3-suite"

    # v2-only checkout falls back to the v2 suite.
    import shutil

    shutil.rmtree(root / "critical-debater-v3-suite")
    assert paths.find_suite_dir() == root / "critical-debater-suite"


def test_find_suite_dir_env_override(tmp_path, monkeypatch):
    fake = tmp_path / "custom-suite"
    (fake / "capabilities").mkdir(parents=True)
    monkeypatch.setenv("CRITICAL_DEBATER_SUITE_DIR", str(fake))
    assert find_suite_dir() == fake
    assert capability_path("x.md") == fake / "capabilities" / "x.md"


def test_find_suite_dir_env_missing_raises(monkeypatch):
    monkeypatch.setenv("CRITICAL_DEBATER_SUITE_DIR", "/nonexistent/suite")
    import pytest

    with pytest.raises(FileNotFoundError):
        find_suite_dir()


def test_renderer_found_via_suite_scripts():
    """The deterministic renderer must be locatable through the suite dir."""
    from critical_debater.synthesis.fallback import _renderer_path

    renderer = _renderer_path()
    assert renderer.name == "render-debate-report-from-json.py"
    assert renderer.exists()


def test_check_install_script_runs():
    result = subprocess.run(
        ["bash", str(SUITE_ROOT / "scripts" / "check-install.sh")],
        capture_output=True,
        text=True,
        cwd=str(SUITE_ROOT.parent),
        env={**os.environ, "PYTHONPATH": str(SUITE_ROOT.parent / "src")},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "INSTALL CHECK PASSED" in result.stdout
