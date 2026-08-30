"""Filesystem location helpers for the skill-suite assets.

The v3 skill suite (``critical-debater-v3-suite/``) is the preferred source
of capability instructions; the v2 suite (``critical-debater-suite/``) is the
fallback. Both bundle ``capabilities/*.md`` which the API-backed agent runner
injects into prompts, and both may carry the deterministic report renderer
under ``scripts/``.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_SUITE_DIR = "CRITICAL_DEBATER_SUITE_DIR"

# Preferred-first candidates for a bundled skill suite directory.
SUITE_DIR_NAMES = ("critical-debater-v3-suite", "critical-debater-suite")


def _candidate_roots() -> list[Path]:
    """Directory roots scanned for a bundled suite (module ancestors, then cwd)."""
    here = Path(__file__).resolve()
    roots = list(here.parents)
    roots.append(Path.cwd())
    return roots


def find_suite_dir() -> Path:
    """Locate a skill-suite directory containing capability instructions.

    Resolution order: env override → walk up from this package (source
    checkout) → cwd. Raises FileNotFoundError when absent.
    """
    override = os.environ.get(ENV_SUITE_DIR)
    if override:
        path = Path(override)
        if path.is_dir():
            return path
        raise FileNotFoundError(f"{ENV_SUITE_DIR} points to a missing directory: {override}")

    for root in _candidate_roots():
        for name in SUITE_DIR_NAMES:
            candidate = root / name
            if (candidate / "capabilities").is_dir():
                return candidate

    raise FileNotFoundError(
        f"no skill suite found (looked for {', '.join(SUITE_DIR_NAMES)} with a capabilities/ "
        f"directory); set {ENV_SUITE_DIR}"
    )


def capability_path(name: str) -> Path:
    """Path to a capability markdown, e.g. capability_path("source-ingest.md")."""
    return find_suite_dir() / "capabilities" / name
