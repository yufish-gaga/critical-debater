"""Debate quality assessment — Phase 1 deterministic baseline.

Phase 5 will replace this with the 8-dimension LLM-backed assessor from the
v3 plan (evidence quality, reasoning depth, argument diversity, rebuttal
effectiveness, judge rigor, cross-validation rate, balance, conclusion
reliability). For Phase 1 we compute the deterministic subset that requires
no model calls, so the graph node and ``quality_metrics`` state slot exist
and the report artifact is produced.
"""

from __future__ import annotations

import os
from collections import Counter

from ..workspace import read_json_or, timestamp, write_json


def assess_debate_quality(workspace: str, topic: str, rounds_planned: int) -> dict:
    """Compute baseline quality metrics from workspace artifacts (no LLM calls)."""
    evidence = read_json_or(os.path.join(workspace, "evidence", "evidence_store.json"), [])
    claims = read_json_or(os.path.join(workspace, "claims", "claim_ledger.json"), [])

    rounds_completed = 0
    rounds_dir = os.path.join(workspace, "rounds")
    if os.path.isdir(rounds_dir):
        for name in os.listdir(rounds_dir):
            if name.startswith("round_") and os.path.exists(
                os.path.join(rounds_dir, name, "judge_ruling.json")
            ):
                rounds_completed += 1

    status_counts = Counter(str(c.get("status")) for c in claims if isinstance(c, dict))
    verified = status_counts.get("verified", 0)
    cross_validation_rate = round(verified / len(claims), 4) if claims else 0.0

    metrics = {
        "generated_at": timestamp(),
        "assessment_version": "phase1_deterministic_baseline",
        "topic": topic,
        "rounds_planned": rounds_planned,
        "rounds_completed": rounds_completed,
        "evidence": {
            "total": len(evidence),
            "by_credibility_tier": dict(Counter(str(e.get("credibility_tier")) for e in evidence)),
            "by_source_type": dict(Counter(str(e.get("source_type")) for e in evidence)),
            "by_freshness_status": dict(Counter(str(e.get("freshness_status")) for e in evidence)),
            "corroborated": sum(1 for e in evidence if e.get("corroboration_status") == "corroborated"),
        },
        "claims": {
            "total": len(claims),
            "by_status": dict(status_counts),
            "cross_validation_rate": cross_validation_rate,
        },
    }

    write_json(os.path.join(workspace, "reports", "quality_metrics.json"), metrics)
    return metrics
