"""Evidence credibility scoring (v3 Phase 4).

Multi-dimension weighted score per the refactoring plan::

    综合可信度 (0-1) = Σ dimension × weight
      来源权威性 authority        30%   tier base + source_type adjust + 中文注册表
      时效性     freshness        15%   age bands; reasoning/timeless never decays
      交叉验证   cross_validation 25%   corroboration status + claim verdicts
      内容质量   content_quality  20%   snippet informativeness + metadata
      透明度     transparency     10%   url / publisher / date disclosure

Weights are dynamically adjusted for the debate context (red-team mode,
social-heavy or stale-heavy stores, late-round scrutiny) and renormalized to
1.0. Rules live in ``config/credibility_rules.yaml`` with built-in fallbacks.

All scoring is deterministic — no LLM calls.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .chinese import ChineseSourceRegistry, domain_of
from .merge import evidence_store_path
from ..workspace import read_json_or, timestamp, write_json

ENV_RULES_CONFIG = "CRITICAL_CREDIBILITY_RULES_CONFIG"
DEFAULT_RULES_REL_PATH = os.path.join("config", "credibility_rules.yaml")

DIMENSIONS = ("authority", "freshness", "cross_validation", "content_quality", "transparency")

DEFAULT_RULES: dict = {
    "weights": {
        "authority": 0.30,
        "freshness": 0.15,
        "cross_validation": 0.25,
        "content_quality": 0.20,
        "transparency": 0.10,
    },
    "tier_base": {
        "tier1_authoritative": 1.0,
        "tier2_reputable": 0.75,
        "tier3_general": 0.45,
        "tier4_social": 0.15,
    },
    "source_type_adjust": {"government": 0.10, "academic": 0.10, "twitter": -0.10},
    "freshness": {
        "reasoning_track": 1.0,
        "stale": 0.1,
        "no_date": 0.5,
        "age_bands_days": [[7, 1.0], [30, 0.9], [180, 0.7], [365, 0.5], [730, 0.3]],
        "fallback_older": 0.15,
    },
    "cross_validation": {
        "corroborated": 1.0,
        "uncorroborated_or_null": 0.4,
        "contradicted": 0.0,
        "verified_claim_boost": 0.15,
        "contested_claim_penalty": 0.15,
        "duplicate_domain_dilution": 0.9,
    },
    "content_quality": {
        "short_snippet_chars": 80,
        "medium_snippet_chars": 200,
        "short_score": 0.3,
        "medium_score": 0.6,
        "long_score": 0.9,
        "has_date_bonus": 0.05,
        "has_publisher_bonus": 0.05,
        "social_flag_adjust": {
            "likely_reliable": 0.10,
            "needs_verification": 0.0,
            "likely_unreliable": -0.30,
        },
    },
    "adjustments": {
        "red_team_mode": {"when_mode": "red_team", "deltas": {"cross_validation": 0.10, "authority": -0.05}},
        "social_heavy": {"when_social_share_above": 0.4, "deltas": {"cross_validation": 0.05, "authority": 0.05}},
        "stale_heavy": {"when_stale_share_above": 0.3, "deltas": {"freshness": 0.05}},
        "late_round_scrutiny": {"when_round_from": 3, "deltas": {"cross_validation": 0.05}},
    },
}


def load_rules(config_path: Optional[str] = None) -> dict:
    path = config_path or os.environ.get(ENV_RULES_CONFIG) or DEFAULT_RULES_REL_PATH
    rules = json.loads(json.dumps(DEFAULT_RULES))  # deep copy of defaults
    if os.path.exists(path):
        try:
            import yaml

            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            return rules
        for key, value in data.items():
            if key == "adjustments" and isinstance(value, dict):
                rules["adjustments"].update(value)
            elif isinstance(value, dict) and isinstance(rules.get(key), dict):
                rules[key].update(value)
            else:
                rules[key] = value
    return rules


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _parse_date(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@dataclass
class ScoringContext:
    """Debate context driving dynamic weight adjustment."""

    mode: str = "balanced"
    round_num: int = 1
    store: list = field(default_factory=list)
    claims: list = field(default_factory=list)


class EvidenceCredibilityScorer:
    """Deterministic multi-dimension credibility scorer."""

    def __init__(self, rules: Optional[dict] = None,
                 zh_registry: Optional[ChineseSourceRegistry] = None):
        self.rules = rules or load_rules()
        self.zh_registry = zh_registry

    # -- dynamic weights ---------------------------------------------------

    def adjust_weights(self, context: ScoringContext) -> tuple[dict[str, float], list[str]]:
        weights = {dim: float(self.rules["weights"].get(dim, 0.0)) for dim in DIMENSIONS}
        applied: list[str] = []

        store = context.store or []
        total = len(store)
        social_share = 0.0
        stale_share = 0.0
        if total:
            social_share = sum(1 for e in store if e.get("credibility_tier") == "tier4_social") / total
            stale_share = sum(1 for e in store if e.get("freshness_status") == "stale") / total

        for name, rule in (self.rules.get("adjustments") or {}).items():
            if "when_mode" in rule:
                triggered = context.mode == rule["when_mode"]
            elif "when_social_share_above" in rule:
                triggered = social_share > rule["when_social_share_above"]
            elif "when_stale_share_above" in rule:
                triggered = stale_share > rule["when_stale_share_above"]
            elif "when_round_from" in rule:
                triggered = context.round_num >= rule["when_round_from"]
            else:
                continue
            if not triggered:
                continue
            for dim, delta in (rule.get("deltas") or {}).items():
                if dim in weights:
                    weights[dim] += float(delta)
            applied.append(name)

        norm = sum(weights.values()) or 1.0
        return {dim: round(w / norm, 4) for dim, w in weights.items()}, applied

    # -- dimensions ----------------------------------------------------------

    def _authority(self, evidence: dict) -> float:
        tier_base = self.rules["tier_base"]
        tier = evidence.get("credibility_tier")
        score = float(tier_base.get(tier, 0.45))

        source_type = evidence.get("source_type")
        adjust = self.rules["source_type_adjust"].get(source_type, 0.0)
        score += float(adjust)

        # Known authoritative Chinese domains anchor at the top of the scale.
        if self.zh_registry is not None and source_type != "twitter":
            tier_override = self.zh_registry.classify(evidence.get("url") or "")
            if tier_override == "tier1_authoritative":
                score = max(score, 0.95)
            elif tier_override == "tier4_social":
                score = min(score, 0.15)
        return _clamp01(score)

    def _freshness(self, evidence: dict, now: datetime) -> float:
        cfg = self.rules["freshness"]
        if evidence.get("evidence_track") == "reasoning" or evidence.get("freshness_status") == "timeless":
            # Contract-critical rule: reasoning-track evidence never decays.
            return float(cfg["reasoning_track"])
        if evidence.get("freshness_status") == "stale":
            return float(cfg["stale"])

        parsed = _parse_date(evidence.get("published_at")) or _parse_date(evidence.get("retrieved_at"))
        if parsed is None:
            return float(cfg["no_date"])
        age_days = max(0.0, (now - parsed).total_seconds() / 86400.0)
        for max_days, score in cfg["age_bands_days"]:
            if age_days <= max_days:
                return float(score)
        return float(cfg["fallback_older"])

    def _cross_validation(self, evidence: dict, context: ScoringContext) -> float:
        cfg = self.rules["cross_validation"]
        status = evidence.get("corroboration_status")
        if status == "corroborated":
            score = float(cfg["corroborated"])
        elif status == "contradicted":
            score = float(cfg["contradicted"])
        else:
            score = float(cfg["uncorroborated_or_null"])

        # Claim verdicts citing this evidence are deterministic corroboration
        # signals (judge-verified claims strengthen; contested ones weaken).
        evidence_id = evidence.get("evidence_id")
        if evidence_id:
            citing = [c for c in context.claims if isinstance(c, dict)
                      and evidence_id in (c.get("evidence_ids") or [])]
            statuses = {c.get("status") for c in citing}
            if "verified" in statuses:
                score += float(cfg["verified_claim_boost"])
            if "contested" in statuses:
                score -= float(cfg["contested_claim_penalty"])

        # Duplicate copies on the same domain add no independence.
        host = domain_of(evidence.get("url") or "")
        if host:
            same_domain = sum(
                1 for e in context.store
                if domain_of(e.get("url") or "") == host
                and e.get("evidence_id") != evidence_id
            )
            if same_domain > 0:
                score *= float(cfg["duplicate_domain_dilution"])
        return _clamp01(score)

    def _content_quality(self, evidence: dict) -> float:
        cfg = self.rules["content_quality"]
        snippet = str(evidence.get("snippet") or "")
        length = len(snippet.strip())
        if length < cfg["short_snippet_chars"]:
            score = float(cfg["short_score"])
        elif length < cfg["medium_snippet_chars"]:
            score = float(cfg["medium_score"])
        else:
            score = float(cfg["long_score"])

        if evidence.get("published_at"):
            score += float(cfg["has_date_bonus"])
        if evidence.get("publisher"):
            score += float(cfg["has_publisher_bonus"])

        flag_adjust = cfg["social_flag_adjust"].get(evidence.get("social_credibility_flag"))
        if flag_adjust is not None:
            score += float(flag_adjust)
        return _clamp01(score)

    def _transparency(self, evidence: dict) -> float:
        score = 0.0
        if evidence.get("url"):
            score += 0.4
        if evidence.get("publisher"):
            score += 0.3
        if evidence.get("published_at"):
            score += 0.3
        if evidence.get("source_type") == "twitter" and evidence.get("social_credibility_flag") != "likely_reliable":
            score = min(score, 0.4)  # anonymous social posts disclose little
        return _clamp01(score)

    # -- public API ----------------------------------------------------------

    def score_item(self, evidence: dict, context: ScoringContext,
                   weights: dict[str, float], now: Optional[datetime] = None) -> dict:
        now = now or datetime.now(timezone.utc)
        dimensions = {
            "authority": self._authority(evidence),
            "freshness": self._freshness(evidence, now),
            "cross_validation": self._cross_validation(evidence, context),
            "content_quality": self._content_quality(evidence),
            "transparency": self._transparency(evidence),
        }
        total = sum(dimensions[dim] * weights[dim] for dim in DIMENSIONS)
        return {
            "evidence_id": evidence.get("evidence_id"),
            "total": round(_clamp01(total), 4),
            "dimensions": dimensions,
        }

    def score_store(self, context: ScoringContext) -> dict:
        """Score a whole store: weights, adjustments, per-item breakdown."""
        weights, applied = self.adjust_weights(context)
        now = datetime.now(timezone.utc)
        items = [self.score_item(e, context, weights, now) for e in context.store if isinstance(e, dict)]
        items = [i for i in items if i["evidence_id"]]
        average = round(sum(i["total"] for i in items) / len(items), 4) if items else 0.0
        return {
            "scored_at": timestamp(),
            "scorer_version": "phase4_multi_dimension",
            "mode": context.mode,
            "round": context.round_num,
            "weights_used": weights,
            "adjustments_applied": applied,
            "average": average,
            "items": items,
        }


def score_evidence_store(workspace: str, round_num: int, mode: str = "balanced",
                         rules: Optional[dict] = None,
                         zh_registry: Optional[ChineseSourceRegistry] = None,
                         write_artifact: bool = True) -> dict:
    """Score the workspace evidence store and persist ``evidence_credibility.json``."""
    store = read_json_or(evidence_store_path(workspace), [])
    claims = read_json_or(os.path.join(workspace, "claims", "claim_ledger.json"), [])
    scorer = EvidenceCredibilityScorer(rules, zh_registry)
    report = scorer.score_store(ScoringContext(mode=mode, round_num=round_num, store=store, claims=claims))
    if write_artifact:
        write_json(os.path.join(workspace, "evidence", "evidence_credibility.json"), report)
    return report


def load_credibility_scores(workspace: str) -> dict[str, float]:
    """evidence_id → total score map from the persisted artifact."""
    report = read_json_or(os.path.join(workspace, "evidence", "evidence_credibility.json"), {})
    return {item.get("evidence_id"): item.get("total", 0.0)
            for item in report.get("items", []) if isinstance(item, dict) and item.get("evidence_id")}
