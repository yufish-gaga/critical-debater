"""Debate run options (v2 ``Options`` dataclass port)."""

from __future__ import annotations

from dataclasses import dataclass, field
import json

CONFIG_DEFAULTS = {
    "depth": "standard",
    "mode": "balanced",
    "evidence_refresh": "hybrid",
    "language": "bilingual",
}

DEPTH_MIN_EVIDENCE = {"quick": 5, "standard": 10, "deep": 15}
DEPTH_MIN_ARGS = {"quick": 2, "standard": 2, "deep": 3}
DEPTH_QUERY_COUNT = {"quick": 3, "standard": 5, "deep": 8}


@dataclass
class DebateOptions:
    topic: str
    rounds: int = 3
    output_format: str = "full_report"
    language: str = "bilingual"
    domain: str = "general"
    depth: str = "standard"
    mode: str = "balanced"
    speculation: str = "moderate"
    evidence_refresh: str = "hybrid"
    focus: list[str] = field(default_factory=list)
    allow_fallback: bool = True
    min_evidence: int = 10
    source_retries: int = 2
    min_args: int = 2
    min_rebuttals: int = 1
    step_timeout_sec: int = 300

    @classmethod
    def from_config(cls, config_path: str) -> "DebateOptions":
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
        depth = cfg.get("depth", "standard")
        return cls(
            topic=cfg["topic"],
            rounds=cfg.get("round_count", cfg.get("rounds", 3)),
            output_format=cfg.get("output_format", "full_report"),
            language=cfg.get("language", "bilingual"),
            domain=cfg.get("domain", "general"),
            depth=depth,
            mode=cfg.get("mode", "balanced"),
            speculation=cfg.get("speculation_level", "moderate"),
            evidence_refresh=cfg.get("evidence_refresh", "hybrid"),
            focus=cfg.get("focus_areas", []),
            min_evidence=DEPTH_MIN_EVIDENCE.get(depth, 10),
            min_args=DEPTH_MIN_ARGS.get(depth, 2),
        )
