"""Filesystem location helpers for the v2 skill-suite assets."""

from __future__ import annotations

import os
from pathlib import Path

ENV_SUITE_DIR = "CRITICAL_DEBATER_SUITE_DIR"


def find_suite_dir() -> Path:
    """Locate the ``critical-debater-suite`` directory (capability docs).

    Resolution order: env override → walk up from this package (source
    checkout) → cwd. Raises FileNotFoundError when absent.
    """
    override = os.environ.get(ENV_SUITE_DIR)
    if override:
        path = Path(override)
        if path.is_dir():
            return path
        raise FileNotFoundError(f"{ENV_SUITE_DIR} points to a missing directory: {override}")

    here = Path(__file__).resolve()
    for ancestor in [here, *here.parents]:
        candidate = ancestor / "critical-debater-suite"
        if candidate.is_dir():
            return candidate

    cwd_candidate = Path.cwd() / "critical-debater-suite"
    if cwd_candidate.is_dir():
        return cwd_candidate

    raise FileNotFoundError(
        "critical-debater-suite not found; set CRITICAL_DEBATER_SUITE_DIR"
    )


def capability_path(name: str) -> Path:
    """Path to a capability markdown, e.g. capability_path("source-ingest.md")."""
    return find_suite_dir() / "capabilities" / name
