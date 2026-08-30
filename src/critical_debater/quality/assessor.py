"""Eight-dimension debate quality assessment (v3 Phase 5).

Implements the assessor from the refactoring plan::

    1. 证据质量   evidence quality        — Phase-4 credibility + tier mix
    2. 推理深度   reasoning depth         — reasoning-chain completeness, scenarios
    3. 论点多样性 argument diversity      — claim types, domain spread, overlap
    4. 反驳有效性 rebuttal effectiveness  — targeted rebuttals, MRP fulfilment
    5. 裁判严谨性 judge rigor             — verification coverage + reasoning
    6. 交叉验证率 cross-validation rate   — verified claims + corroborated evidence
    7. 辩论平衡性 debate balance          — argument/evidence parity across sides
    8. 结论可靠性 conclusion reliability  — grounded verified facts, profiles filled

Every dimension is a deterministic 0-1 score with subscores and notes. The
overall score is a weighted average (equal by default; overridable via
``config/quality_rules.yaml`` / ``CRITICAL_QUALITY_RULES_CONFIG``).

Artifacts written: ``reports/quality_metrics.json`` (machine-readable),
``reports/quality_report.md`` (bilingual), ``reports/quality_dashboard.html``
(self-contained inline-SVG dashboard, zero external assets).
"""

from __future__ import annotations

import os
from collections import Counter
from typing import Any, Optional

from ..evidence.chinese import domain_of
from ..workspace import read_json_or, timestamp, write_json
from .charts import build_dashboard
from .report import render_quality_report

ENV_RULES_CONFIG = "CRITICAL_QUALITY_RULES_CONFIG"
DEFAULT_RULES_REL_PATH = os.path.join("config", "quality_rules.yaml")

DIMENSIONS = (
    "evidence_quality",        # 证据质量
    "reasoning_depth",         # 推理深度
    "argument_diversity",      # 论点多样性
    "rebuttal_effectiveness",  # 反驳有效性
    "judge_rigor",             # 裁判严谨性
    "cross_validation_rate",   # 交叉验证率
    "debate_balance",          # 辩论平衡性
    "conclusion_reliability",  # 结论可靠性
)

DIMENSION_LABELS = {
    "evidence_quality": "证据质量 / Evidence quality",
    "reasoning_depth": "推理深度 / Reasoning depth",
    "argument_diversity": "论点多样性 / Argument diversity",
    "rebuttal_effectiveness": "反驳有效性 / Rebuttal effectiveness",
    "judge_rigor": "裁判严谨性 / Judge rigor",
    "cross_validation_rate": "交叉验证率 / Cross-validation rate",
    "debate_balance": "辩论平衡性 / Debate balance",
    "conclusion_reliability": "结论可靠性 / Conclusion reliability",
}

DEFAULT_WEIGHTS: dict[str, float] = {dim: 0.125 for dim in DIMENSIONS}

REASONING_CHAIN_ELEMENTS = (
    "observed_facts", "mechanism", "scenario_implication",
    "trigger_conditions", "falsification_conditions",
)

DEPTH_MIN_ARGS = {"quick": 2, "standard": 2, "deep": 3}


def load_quality_weights(config_path: Optional[str] = None) -> dict[str, float]:
    path = config_path or os.environ.get(ENV_RULES_CONFIG) or DEFAULT_RULES_REL_PATH
    weights = dict(DEFAULT_WEIGHTS)
    if os.path.exists(path):
        try:
            import yaml

            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            for dim, value in (data.get("dimension_weights") or {}).items():
                if dim in weights and isinstance(value, (int, float)):
                    weights[dim] = float(value)
        except (OSError, yaml.YAMLError):
            pass
    norm = sum(weights.values()) or 1.0
    return {dim: w / norm for dim, w in weights.items()}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _ratio(numerator: float, denominator: float) -> float:
    return _clamp01(numerator / denominator) if denominator else 0.0


def _load_round_artifacts(workspace: str, rounds: int) -> dict[int, dict]:
    artifacts: dict[int, dict] = {}
    for round_num in range(1, rounds + 1):
        rdir = os.path.join(workspace, "rounds", f"round_{round_num}")
        artifacts[round_num] = {
            "pro": read_json_or(os.path.join(rdir, "pro_turn.json"), {}),
            "con": read_json_or(os.path.join(rdir, "con_turn.json"), {}),
            "judge": read_json_or(os.path.join(rdir, "judge_ruling.json"), {}),
        }
    return artifacts


def _dimension(dim: str, score: float, subscores: dict[str, Any], notes: list[str]) -> dict:
    return {"dimension": dim, "label": DIMENSION_LABELS[dim],
            "score": round(_clamp01(score), 4), "subscores": subscores,
            "notes": notes}


class DebateQualityAssessor:
    """Deterministic eight-dimension debate quality assessor."""

    def __init__(self, workspace: str, topic: str, rounds_planned: int,
                 mode: str = "balanced", depth: str = "standard",
                 weights: Optional[dict[str, float]] = None):
        self.workspace = workspace
        self.topic = topic
        self.rounds_planned = rounds_planned
        self.mode = mode
        self.depth = depth
        self.weights = weights or load_quality_weights()

        self.store = read_json_or(os.path.join(workspace, "evidence", "evidence_store.json"), [])
        self.claims = read_json_or(os.path.join(workspace, "claims", "claim_ledger.json"), [])
        self.scoring = read_json_or(os.path.join(workspace, "evidence", "evidence_credibility.json"), {})
        self.final_report = read_json_or(os.path.join(workspace, "reports", "final_report.json"), {})
        self.rounds = _load_round_artifacts(workspace, rounds_planned)

    # -- helpers -------------------------------------------------------------

    def _turn_claims(self) -> list[dict]:
        """Claim-level entries declared in turn arguments (per side/round)."""
        entries = []
        for round_num, art in self.rounds.items():
            for side in ("pro", "con"):
                for idx, argument in enumerate((art[side] or {}).get("arguments") or []):
                    if isinstance(argument, dict):
                        entries.append({
                            "claim_id": f"clm_{round_num}_{side}_{idx + 1}",
                            "round": round_num,
                            "speaker": side,
                            "claim_type": argument.get("claim_type"),
                            "argument": argument,
                        })
        return entries

    # -- dimension implementations --------------------------------------------

    def _evidence_quality(self) -> dict:
        avg_credibility = float(self.scoring.get("average") or 0.0)
        tiers = Counter(str(e.get("credibility_tier")) for e in self.store if isinstance(e, dict))
        total = sum(tiers.values())
        reputable_share = _ratio(tiers.get("tier1_authoritative", 0) + tiers.get("tier2_reputable", 0), total)
        type_diversity = _ratio(len({str(e.get("source_type")) for e in self.store if isinstance(e, dict)}), 5)
        score = 0.6 * avg_credibility + 0.25 * reputable_share + 0.15 * type_diversity
        return _dimension("evidence_quality", score, {
            "average_credibility": avg_credibility,
            "reputable_share": round(reputable_share, 4),
            "source_type_diversity": round(type_diversity, 4),
            "tier_distribution": dict(tiers),
        }, [f"平均可信度 / average credibility: {avg_credibility}",
            f"权威+可靠信源占比 / reputable share: {reputable_share:.0%}"])

    def _reasoning_depth(self) -> dict:
        min_args = DEPTH_MIN_ARGS.get(self.depth, 2)
        arguments: list[dict] = []
        for art in self.rounds.values():
            for side in ("pro", "con"):
                arguments.extend((art[side] or {}).get("arguments") or [])
        arg_count = len(arguments)
        args_per_turn = _ratio(arg_count, max(1, 2 * len(self.rounds)) * min_args)

        complete = sum(
            1 for a in arguments
            if isinstance(a.get("reasoning_chain"), dict)
            and all(k in a["reasoning_chain"] for k in REASONING_CHAIN_ELEMENTS)
        )
        chain_completeness = _ratio(complete, arg_count)

        scenarios = sum(len(((art[side] or {}).get("speculative_scenarios") or {}).get("scenarios") or [])
                        for art in self.rounds.values() for side in ("pro", "con"))
        historical = sum(len(((art[side] or {}).get("historical_wisdom") or {}).get("references") or [])
                         for art in self.rounds.values() for side in ("pro", "con"))
        exploration = _ratio(min(scenarios + historical, 2 * len(self.rounds)), 2 * len(self.rounds))

        score = 0.45 * args_per_turn + 0.35 * chain_completeness + 0.20 * exploration
        return _dimension("reasoning_depth", score, {
            "arguments_total": arg_count,
            "args_per_turn_vs_min": round(args_per_turn, 4),
            "reasoning_chain_completeness": round(chain_completeness, 4),
            "scenario_or_historical_refs": scenarios + historical,
        }, [f"推理链五要素完整率 / chain completeness: {chain_completeness:.0%}",
            f"情景/历史引用数 / scenario+historical refs: {scenarios + historical}"])

    def _argument_diversity(self) -> dict:
        entries = self._turn_claims()
        type_spread = _ratio(len({e.get("claim_type") for e in entries} - {None}), 3)

        cited_ids = {eid for e in entries for eid in (e["argument"].get("evidence_ids") or [])}
        cited_domains = {domain_of(e.get("url") or "") for e in self.store
                         if isinstance(e, dict) and e.get("evidence_id") in cited_ids} - {""}
        available_domains = {domain_of(e.get("url") or "") for e in self.store if isinstance(e, dict)} - {""}
        domain_spread = _ratio(len(cited_domains), len(available_domains)) if available_domains else 0.0

        def side_ids(side: str) -> set:
            return {eid for e in entries if e["speaker"] == side
                    for eid in (e["argument"].get("evidence_ids") or [])}

        pro_ids, con_ids = side_ids("pro"), side_ids("con")
        union = pro_ids | con_ids
        overlap = len(pro_ids & con_ids) / len(union) if union else 0.0
        independence = 1.0 - overlap if union else 0.0

        score = 0.35 * type_spread + 0.35 * domain_spread + 0.30 * independence
        return _dimension("argument_diversity", score, {
            "claim_type_spread": round(type_spread, 4),
            "cited_domain_spread": round(domain_spread, 4),
            "pro_con_citation_overlap": round(overlap, 4),
        }, [f"论点类型覆盖 / claim types used: {sorted({e.get('claim_type') for e in entries} - {None})}",
            f"双方引用重叠率 / citation overlap: {overlap:.0%}"])

    def _rebuttal_effectiveness(self) -> dict:
        total_rebuttals = 0
        targeted = 0
        for art in self.rounds.values():
            for side in ("pro", "con"):
                for rebuttal in (art[side] or {}).get("rebuttals") or []:
                    total_rebuttals += 1
                    if rebuttal.get("target_claim_id"):
                        targeted += 1
        targeting = _ratio(targeted, total_rebuttals)

        # MRP fulfilment: round N MRPs must be answered in round N+1 turns.
        mrp_total = 0
        mrp_answered = 0
        for round_num, art in self.rounds.items():
            mrps = (art["judge"] or {}).get("mandatory_response_points") or []
            if round_num + 1 not in self.rounds or not mrps:
                continue
            next_art = self.rounds[round_num + 1]
            answered_ids = set()
            for side in ("pro", "con"):
                for resp in (next_art[side] or {}).get("mandatory_responses") or []:
                    answered_ids.add(resp.get("point_id"))
            for mrp in mrps:
                if mrp.get("point_id"):
                    mrp_total += 1
                    if mrp["point_id"] in answered_ids:
                        mrp_answered += 1
        fulfilment = _ratio(mrp_answered, mrp_total) if mrp_total else 1.0

        presence = 1.0 if total_rebuttals >= 2 * len(self.rounds) else _ratio(total_rebuttals, 2 * len(self.rounds))
        score = 0.4 * presence + 0.3 * targeting + 0.3 * fulfilment
        return _dimension("rebuttal_effectiveness", score, {
            "rebuttals_total": total_rebuttals,
            "targeted_share": round(targeting, 4),
            "mrp_fulfilment": round(fulfilment, 4),
        }, [f"指定目标反驳占比 / targeted rebuttals: {targeting:.0%}",
            f"必答点履行率 / MRP fulfilment: {fulfilment:.0%}"])

    def _judge_rigor(self) -> dict:
        turn_claim_ids = {e["claim_id"] for e in self._turn_claims()}
        verified_ids = set()
        reasoned = 0
        total_verdicts = 0
        flagged_rounds = 0
        for round_num, art in self.rounds.items():
            ruling = art["judge"] or {}
            verdicts = ruling.get("verification_results") or []
            total_verdicts += len(verdicts)
            for vr in verdicts:
                if isinstance(vr, dict):
                    verified_ids.add(vr.get("claim_id"))
                    if str(vr.get("reasoning") or "").strip():
                        reasoned += 1
            if ruling.get("causal_validity_flags"):
                flagged_rounds += 1

        coverage = _ratio(len(turn_claim_ids & verified_ids), len(turn_claim_ids)) if turn_claim_ids else 0.0
        reasoning_share = _ratio(reasoned, total_verdicts)
        scrutiny = _ratio(flagged_rounds, len(self.rounds))
        score = 0.45 * coverage + 0.35 * reasoning_share + 0.20 * scrutiny
        return _dimension("judge_rigor", score, {
            "verification_coverage": round(coverage, 4),
            "reasoned_verdicts_share": round(reasoning_share, 4),
            "rounds_with_causal_flags": flagged_rounds,
        }, [f"论点裁定覆盖率 / verification coverage: {coverage:.0%}",
            f"裁定均附理由 / reasoned verdicts: {reasoning_share:.0%}"])

    def _cross_validation_rate(self) -> dict:
        verified = sum(1 for c in self.claims if isinstance(c, dict) and c.get("status") == "verified")
        claim_rate = _ratio(verified, len(self.claims))
        corroborated = sum(1 for e in self.store if isinstance(e, dict)
                           and e.get("corroboration_status") == "corroborated")
        evidence_rate = _ratio(corroborated, len(self.store))
        score = 0.6 * claim_rate + 0.4 * evidence_rate
        return _dimension("cross_validation_rate", score, {
            "verified_claims": verified,
            "claims_total": len(self.claims),
            "corroborated_evidence": corroborated,
        }, [f"verified 论点占比 / verified claims: {claim_rate:.0%}",
            f"corroborated 证据占比 / corroborated evidence: {evidence_rate:.0%}"])

    def _debate_balance(self) -> dict:
        arg_counts: dict[str, int] = {}
        discovered: Counter = Counter()
        for art in self.rounds.values():
            for side in ("pro", "con"):
                arg_counts[side] = arg_counts.get(side, 0) + len((art[side] or {}).get("arguments") or [])
        for e in self.store:
            if isinstance(e, dict):
                discovered[str(e.get("discovered_by"))] += 1
        pro, con = arg_counts.get("pro", 0), arg_counts.get("con", 0)
        argument_parity = 1.0 - (abs(pro - con) / (pro + con)) if (pro + con) else 0.0
        pro_e, con_e = discovered.get("pro", 0), discovered.get("con", 0)
        discovery_parity = 1.0 - (abs(pro_e - con_e) / (pro_e + con_e)) if (pro_e + con_e) else 1.0
        score = 0.6 * argument_parity + 0.4 * discovery_parity
        return _dimension("debate_balance", score, {
            "pro_arguments": pro,
            "con_arguments": con,
            "argument_parity": round(argument_parity, 4),
            "evidence_discovery_parity": round(discovery_parity, 4),
        }, [f"论点数 正/反 / pro/con arguments: {pro}/{con}",
            f"双方发现证据 正/反 / evidence discovered: {pro_e}/{con_e}"])

    def _conclusion_reliability(self) -> dict:
        verified_claims = sum(1 for c in self.claims if isinstance(c, dict) and c.get("status") == "verified")
        profiles = (self.final_report.get("conclusion_profiles") or [])
        profile_depth = _ratio(
            sum(1 for p in profiles
                if (p.get("profile", {}).get("falsifiability") or {}).get("test_method")
                and (p.get("profile", {}).get("validity_window") or {}).get("value")),
            len(profiles),
        ) if profiles else 0.0
        contested = self.final_report.get("contested_points") or []
        honest_contested = _ratio(
            sum(1 for c in contested if c.get("resolution_status") not in (None, "")),
            len(contested),
        ) if contested else 1.0
        grounded = 1.0 if (verified_claims and self.final_report.get("verified_facts")) else (0.0 if verified_claims else 0.5)
        outlook = 1.0 if self.final_report.get("scenario_outlook") and self.final_report.get("watchlist_24h") is not None else 0.4
        score = 0.3 * grounded + 0.25 * profile_depth + 0.25 * honest_contested + 0.2 * outlook
        return _dimension("conclusion_reliability", score, {
            "grounded_verified_facts": bool(verified_claims and self.final_report.get("verified_facts")),
            "conclusion_profiles": len(profiles),
            "profile_depth_share": round(profile_depth, 4),
            "contested_resolution_labelled": round(honest_contested, 4),
        }, [f"结论画像数 / conclusion profiles: {len(profiles)}",
            f"画像可证伪+有效窗口完整率 / profile depth: {profile_depth:.0%}"])

    # -- public API ------------------------------------------------------------

    def assess(self) -> dict:
        dims = [
            self._evidence_quality(),
            self._reasoning_depth(),
            self._argument_diversity(),
            self._rebuttal_effectiveness(),
            self._judge_rigor(),
            self._cross_validation_rate(),
            self._debate_balance(),
            self._conclusion_reliability(),
        ]
        overall = round(sum(d["score"] * self.weights[d["dimension"]] for d in dims), 4)
        rounds_completed = sum(1 for art in self.rounds.values()
                               if (art["judge"] or {}).get("round_summary"))
        tiers = Counter(str(e.get("credibility_tier")) for e in self.store if isinstance(e, dict))
        status_counts = Counter(str(c.get("status")) for c in self.claims if isinstance(c, dict))
        return {
            "generated_at": timestamp(),
            "assessment_version": "phase5_eight_dimensions",
            "topic": self.topic,
            "mode": self.mode,
            "depth": self.depth,
            "rounds_planned": self.rounds_planned,
            "rounds_completed": rounds_completed,
            "overall_score": overall,
            "dimension_weights": self.weights,
            "dimensions": dims,
            "baseline": {
                "evidence": {
                    "total": len(self.store),
                    "by_credibility_tier": dict(tiers),
                    "by_source_language": dict(Counter(str(e.get("source_language")) for e in self.store if isinstance(e, dict))),
                    "corroborated": sum(1 for e in self.store if isinstance(e, dict) and e.get("corroboration_status") == "corroborated"),
                },
                "claims": {
                    "total": len(self.claims),
                    "by_status": dict(status_counts),
                },
                "credibility": {
                    "average": self.scoring.get("average", 0.0),
                    "adjustments_applied": self.scoring.get("adjustments_applied", []),
                },
            },
        }


def assess_debate_quality(workspace: str, topic: str, rounds_planned: int,
                          mode: str = "balanced", depth: str = "standard") -> dict:
    """Assess quality, persist all three artifacts, return the report dict."""
    report = DebateQualityAssessor(workspace, topic, rounds_planned, mode=mode, depth=depth).assess()
    write_json(os.path.join(workspace, "reports", "quality_metrics.json"), report)
    render_quality_report(workspace, report)
    build_dashboard(workspace, report)
    return report
