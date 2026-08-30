"""Shared pytest fixtures."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from critical_debater.config import DebateOptions
from critical_debater.workspace import init_workspace  # noqa: E402

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
REPORT_MD_FIXTURE = os.path.join(FIXTURES_DIR, "debate_report.md")


@pytest.fixture()
def workspace(tmp_path):
    ws = str(tmp_path / "workspace")
    init_workspace(ws, "Test topic", rounds=2)
    return ws


@pytest.fixture()
def opts() -> DebateOptions:
    return DebateOptions(topic="Test topic", rounds=2, min_evidence=5)
