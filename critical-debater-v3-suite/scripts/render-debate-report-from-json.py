#!/usr/bin/env python3
"""Deterministically render debate_report.md from workspace JSON artifacts."""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


STATUS_ZH = {
    "unresolved": "未解决",
    "leaning_pro": "倾向正方",
    "leaning_con": "倾向反方",
    "partially_resolved": "部分解决",
    "verified": "已验证",
    "contested": "有争议",
    "unverified": "未验证",
    "stale": "过期",
}

CONFIDENCE_EN = {
    "strong": "High",
    "moderate": "Medium",
    "weak": "Low",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}

CONFIDENCE_ZH = {
    "High": "高",
    "Medium": "中",
    "Low": "低",
}

STRENGTH_ZH = {
    "Strong": "强",
    "Moderate": "中",
    "Weak": "弱",
}

SIDE_ZH = {
    "pro": "正方",
    "con": "反方",
}


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def esc(value) -> str:
    text = "" if value is None else str(value)
    return " ".join(text.replace("|", "\\|").split())


def short(text: str, limit: int = 180) -> str:
    t = esc(text)
    if len(t) <= limit:
        return t
    return t[: limit - 3] + "..."


def as_list(value) -> list:
    if isinstance(value, list):
        return value
    return []


def load_round_dirs(rounds_dir: Path) -> list[int]:
    nums = []
    for item in rounds_dir.glob("round_*"):
        if item.is_dir():
            try:
                nums.append(int(item.name.split("_")[-1]))
            except ValueError:
                continue
    return sorted(nums)


def status_to_strength(status_counts: Counter) -> str:
    verified = status_counts.get("verified", 0)
    contested = status_counts.get("contested", 0)
    if verified >= 2 and contested == 0:
        return "Strong"
    if verified >= 1:
        return "Moderate"
    return "Weak"


def turn_snapshot(workspace: Path, round_num: int, side: str) -> tuple[str, str]:
    turn_path = workspace / "rounds" / f"round_{round_num}" / f"{side}_turn.json"
    if not turn_path.exists():
        return "N/A", "N/A"
    turn = read_json(turn_path)
    args = as_list(turn.get("arguments"))
    if not args:
        return "N/A", "N/A"
    first = args[0]
    claim_text = short(first.get("claim_text", "N/A"), 120)
    evidence_ids = esc(", ".join(as_list(first.get("evidence_ids"))) or "N/A")
    return claim_text, evidence_ids


def render_contested_points(lines: list[str], contested_points: list[dict], zh: bool = False):
    if not contested_points:
        title = "### No major contested point identified" if not zh else "### 未识别出主要争议点"
        lines.append(title)
        lines.append("- **Status / 状态**: unresolved" if not zh else "- **状态 / Status**: 未解决")
        lines.append("- **Pro Position / 正方立场**: N/A" if not zh else "- **正方立场 / Pro Position**: 无")
        lines.append("- **Con Position / 反方立场**: N/A" if not zh else "- **反方立场 / Con Position**: 无")
        lines.append("- **Key Rebuttals / 关键反驳**: None" if not zh else "- **关键反驳 / Key Rebuttals**: 无")
        lines.append("- **Judge Assessment / 裁判评估**: N/A" if not zh else "- **裁判评估 / Judge Assessment**: 无")
        lines.append("")
        return

    for cp in contested_points:
        point_title = esc(cp.get("point", "Contested Point"))
        status = esc(cp.get("resolution_status", "unresolved"))
        status_zh = STATUS_ZH.get(status, status)
        pro = esc(cp.get("pro_position", "N/A"))
        con = esc(cp.get("con_position", "N/A"))
        judge = esc(cp.get("judge_assessment", "N/A"))
        rebuttals = as_list(cp.get("key_rebuttals"))

        lines.append(f"### {point_title}")
        if zh:
            lines.append(f"- **状态 / Status**: {status_zh} ({status})")
            lines.append(f"- **正方立场 / Pro Position**: {pro}")
            lines.append(f"- **反方立场 / Con Position**: {con}")
            lines.append("- **关键反驳 / Key Rebuttals**:")
        else:
            lines.append(f"- **Status / 状态**: {status}")
            lines.append(f"- **Pro Position / 正方立场**: {pro}")
            lines.append(f"- **Con Position / 反方立场**: {con}")
            lines.append("- **Key Rebuttals / 关键反驳**:")

        if rebuttals:
            for rb in rebuttals:
                frm = esc(rb.get("from", "side"))
                tgt = esc(rb.get("target", "claim"))
                arg = esc(rb.get("argument", ""))
                ev = esc(", ".join(as_list(rb.get("evidence_ids"))))
                if zh:
                    lines.append(f"  - **[{frm}] -> {tgt}** {arg} (证据: {ev or 'N/A'})")
                else:
                    lines.append(f"  - **[{frm}] -> {tgt}** {arg} (Evidence: {ev or 'N/A'})")
        else:
            lines.append("  - None" if not zh else "  - 无")

        if zh:
            lines.append(f"- **裁判评估 / Judge Assessment**: {judge}")
        else:
            lines.append(f"- **Judge Assessment / 裁判评估**: {judge}")
        lines.append("")


def render_conclusion_profiles(lines: list[str], profiles: list[dict], zh: bool = False):
    mapping = [
        ("Probability", "概率", "probability", "rationale"),
        ("Confidence", "置信度", "confidence", "rationale"),
        ("Consensus", "共识度", "consensus", "rationale"),
        ("Evidence Coverage", "证据覆盖", "evidence_coverage", "gaps"),
        ("Reversibility", "可逆性", "reversibility", "reversal_trigger"),
        ("Validity Window", "有效期", "validity_window", "expiry_condition"),
        ("Impact Magnitude", "影响幅度", "impact_magnitude", "scope"),
        ("Causal Clarity", "因果清晰度", "causal_clarity", "weakest_link"),
        ("Actionability", "可执行性", "actionability", "suggested_action"),
        ("Falsifiability", "可证伪性", "falsifiability", "test_method"),
    ]

    if not profiles:
        profiles = [{"conclusion_text": "N/A", "profile": {}}]

    for item in profiles:
        conclusion = esc(item.get("conclusion_text", "N/A"))
        if zh:
            lines.append(f"### 结论画像: {conclusion}")
        else:
            lines.append(f"### Conclusion: {conclusion}")
        lines.append("| Dimension / 维度 | Value / 值 | Rationale / 依据 |")
        lines.append("|---|---|---|")
        profile = item.get("profile", {})
        for en_label, zh_label, key, reason_field in mapping:
            block = profile.get(key, {})
            label = f"{zh_label} ({en_label})" if zh else en_label
            val = esc(block.get("value", "N/A"))
            why = esc(block.get(reason_field, block.get("rationale", "N/A")))
            lines.append(f"| {label} | {val} | {why} |")
        lines.append("")


def render(workspace: Path) -> str:
    config = read_json(workspace / "config.json")
    final_report = read_json(workspace / "reports" / "final_report.json")
    evidence = as_list(read_json(workspace / "evidence" / "evidence_store.json"))
    claim_ledger = as_list(read_json(workspace / "claims" / "claim_ledger.json"))
    round_nums = load_round_dirs(workspace / "rounds")

    topic = final_report.get("topic") or config.get("topic") or "Unknown Topic"
    summary = (
        final_report.get("executive_summary", {}).get("summary_paragraph")
        or final_report.get("verdict_summary", "")
        or "No summary available."
    )

    tier_counter = Counter(item.get("credibility_tier", "unknown") for item in evidence)
    claim_status_by_round_side: dict[tuple[int, str], Counter] = {}
    for claim in claim_ledger:
        key = (claim.get("round", 0), claim.get("speaker", ""))
        claim_status_by_round_side.setdefault(key, Counter())
        claim_status_by_round_side[key][claim.get("status", "unknown")] += 1

    lines: list[str] = []
    lines.append(f"# Debate Report: {topic}")
    lines.append("")

    lines.append("## Executive Summary")
    lines.append(summary)
    lines.append("")

    lines.append("## Decision Matrix")
    lines.append("| Factor / 因素 | Assessment / 评估 | Confidence / 置信度 | Key Evidence / 关键证据 |")
    lines.append("|---|---|---|---|")
    dimensions = as_list(final_report.get("decision_matrix", {}).get("dimensions"))
    if dimensions:
        for item in dimensions:
            factor = short(item.get("factor", "N/A"), 80)
            assessment = short(item.get("judge_note") or item.get("pro_position") or "N/A", 130)
            confidence = CONFIDENCE_EN.get(str(item.get("evidence_strength", "")).lower(), "Medium")
            key_evidence = short(item.get("con_position") or "See contested points", 130)
            lines.append(f"| {factor} | {assessment} | {confidence} | {key_evidence} |")
    else:
        lines.append("| N/A | No decision matrix dimensions found | Low | N/A |")
    lines.append("")

    lines.append("## Verified Facts")
    lines.append("| # | Fact / 事实 | Sources / 来源 | Confidence / 置信度 |")
    lines.append("|---|---|---|---|")
    verified_facts = as_list(final_report.get("verified_facts"))
    if verified_facts:
        for i, fact in enumerate(verified_facts, 1):
            lines.append(f"| {i} | {short(fact, 220)} | Evidence Inventory | High |")
    else:
        lines.append("| 1 | No verified facts available | N/A | Low |")
    lines.append("")

    lines.append("## Contested Points")
    render_contested_points(lines, as_list(final_report.get("contested_points")), zh=False)

    lines.append("## Key Arguments by Round")
    if not round_nums:
        lines.append("### Round N/A")
        lines.append("| Side | Core Argument | Strength | Key Evidence |")
        lines.append("|---|---|---|---|")
        lines.append("| Pro | N/A | Weak | N/A |")
        lines.append("| Con | N/A | Weak | N/A |")
        lines.append("")
    else:
        for round_num in round_nums:
            lines.append(f"### Round {round_num}")
            lines.append("| Side | Core Argument | Strength | Key Evidence |")
            lines.append("|---|---|---|---|")
            for side in ["pro", "con"]:
                core_arg, key_evidence = turn_snapshot(workspace, round_num, side)
                strength = status_to_strength(claim_status_by_round_side.get((round_num, side), Counter()))
                lines.append(f"| {side.capitalize()} | {core_arg} | {strength} | {key_evidence} |")
            lines.append("")

    lines.append("## Scenario Outlook")
    lines.append("| Scenario / 情景 | Probability / 概率 | Impact / 影响 | Key Trigger / 关键触发 |")
    lines.append("|---|---|---|---|")
    scenario_outlook = final_report.get("scenario_outlook", {})
    base_case = short(scenario_outlook.get("base_case", "N/A"), 130)
    falsifiers = short(" / ".join(as_list(scenario_outlook.get("falsification_conditions"))) or "N/A", 130)
    upside = short(" / ".join(as_list(scenario_outlook.get("upside_triggers"))) or "N/A", 130)
    downside = short(" / ".join(as_list(scenario_outlook.get("downside_triggers"))) or "N/A", 130)
    lines.append(f"| Base case | High | {base_case} | {falsifiers} |")
    lines.append(f"| Upside | Medium | {upside} | {upside} |")
    lines.append(f"| Downside | Medium | {downside} | {downside} |")
    lines.append("")

    lines.append("## Watchlist")
    lines.append("| Item / 监控项 | Reversal Trigger / 反转触发 | Source / 监控来源 | Timeframe / 时间 |")
    lines.append("|---|---|---|---|")
    watchlist = as_list(final_report.get("watchlist_24h"))
    if watchlist:
        for item in watchlist:
            lines.append(
                f"| {short(item.get('item', 'N/A'), 80)} | {short(item.get('reversal_trigger', 'N/A'), 130)} | "
                f"{short(item.get('monitoring_source', 'N/A'), 80)} | {esc(item.get('timeframe', '24h'))} |"
            )
    else:
        lines.append("| N/A | N/A | N/A | 24h |")
    lines.append("")

    lines.append("## Evidence Inventory")
    lines.append("| ID | Source | Type | Credibility | Track | Freshness | Discovered By | Round |")
    lines.append("|---|---|---|---|---|---|---|---|")
    sorted_evidence = sorted(
        evidence,
        key=lambda item: (item.get("discovered_at_round", 0), item.get("evidence_id", "")),
    )
    if not sorted_evidence:
        lines.append("| N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |")
    else:
        for item in sorted_evidence:
            source = short(item.get("publisher") or item.get("url", "N/A"), 50)
            lines.append(
                f"| {esc(item.get('evidence_id', 'N/A'))} | {source} | {esc(item.get('source_type', 'N/A'))} | "
                f"{esc(item.get('credibility_tier', 'N/A'))} | {esc(item.get('evidence_track', 'N/A'))} | "
                f"{esc(item.get('freshness_status', 'N/A'))} | {esc(item.get('discovered_by', 'N/A'))} | "
                f"{esc(item.get('discovered_at_round', 'N/A'))} |"
            )
    lines.append("")

    lines.append("## Methodology")
    lines.append(f"- Rounds: {esc(config.get('round_count', len(round_nums)))}")
    lines.append(f"- Mode: {esc(config.get('mode', 'balanced'))}")
    lines.append(f"- Depth: {esc(config.get('depth', 'standard'))}")
    lines.append(f"- Evidence items: {len(sorted_evidence)}")
    lines.append(f"- Credibility distribution: {esc(', '.join(f'{k}={v}' for k, v in sorted(tier_counter.items())))}")
    lines.append(f"- Evidence refresh: {esc(config.get('evidence_refresh', 'hybrid'))}")
    lines.append(f"- Language: {esc(config.get('language', 'bilingual'))}")
    lines.append(f"- Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines.append("")

    render_conclusion_profiles(lines, as_list(final_report.get("conclusion_profiles")), zh=False)

    lines.append("---")
    lines.append("")
    lines.append("# Chinese Translation / 中文翻译")
    lines.append("")

    lines.append("## Executive Summary / 执行摘要")
    lines.append(summary)
    lines.append("")

    lines.append("## Decision Matrix / 决策矩阵")
    lines.append("| 因素 | 评估 | 置信度 | 关键证据 |")
    lines.append("|---|---|---|---|")
    if dimensions:
        for item in dimensions:
            factor = short(item.get("factor", "N/A"), 80)
            assessment = short(item.get("judge_note") or item.get("pro_position") or "N/A", 130)
            conf = CONFIDENCE_EN.get(str(item.get("evidence_strength", "")).lower(), "Medium")
            lines.append(
                f"| {factor} | {assessment} | {CONFIDENCE_ZH.get(conf, conf)} | "
                f"{short(item.get('con_position') or '见争议焦点', 130)} |"
            )
    else:
        lines.append("| 无 | 未发现决策维度 | 低 | 无 |")
    lines.append("")

    lines.append("## Verified Facts / 已验证事实")
    lines.append("| # | 事实 | 来源 | 置信度 |")
    lines.append("|---|---|---|---|")
    if verified_facts:
        for i, fact in enumerate(verified_facts, 1):
            lines.append(f"| {i} | {short(fact, 220)} | 证据清单 | 高 |")
    else:
        lines.append("| 1 | 暂无已验证事实 | 无 | 低 |")
    lines.append("")

    lines.append("## Contested Points / 争议焦点")
    render_contested_points(lines, as_list(final_report.get("contested_points")), zh=True)

    lines.append("## Key Arguments by Round / 分轮关键论点")
    if not round_nums:
        lines.append("### 第 N/A 轮")
        lines.append("| 立场 | 核心论点 | 强度 | 关键证据 |")
        lines.append("|---|---|---|---|")
        lines.append("| 正方 | 无 | 弱 | 无 |")
        lines.append("| 反方 | 无 | 弱 | 无 |")
        lines.append("")
    else:
        for round_num in round_nums:
            lines.append(f"### 第 {round_num} 轮")
            lines.append("| 立场 | 核心论点 | 强度 | 关键证据 |")
            lines.append("|---|---|---|---|")
            for side in ["pro", "con"]:
                core_arg, key_evidence = turn_snapshot(workspace, round_num, side)
                strength = status_to_strength(claim_status_by_round_side.get((round_num, side), Counter()))
                lines.append(
                    f"| {SIDE_ZH.get(side, side)} | {core_arg} | {STRENGTH_ZH.get(strength, strength)} | "
                    f"{key_evidence} |"
                )
            lines.append("")

    lines.append("## Scenario Outlook / 情景展望")
    lines.append("| 情景 | 概率 | 影响 | 关键触发 |")
    lines.append("|---|---|---|---|")
    lines.append(f"| 基准情景 | 高 | {base_case} | {falsifiers} |")
    lines.append(f"| 上行情景 | 中 | {upside} | {upside} |")
    lines.append(f"| 下行情景 | 中 | {downside} | {downside} |")
    lines.append("")

    lines.append("## Watchlist / 观察清单")
    lines.append("| 监控项 | 反转触发 | 监控来源 | 时间 |")
    lines.append("|---|---|---|---|")
    if watchlist:
        for item in watchlist:
            lines.append(
                f"| {short(item.get('item', 'N/A'), 80)} | {short(item.get('reversal_trigger', 'N/A'), 130)} | "
                f"{short(item.get('monitoring_source', 'N/A'), 80)} | {esc(item.get('timeframe', '24h'))} |"
            )
    else:
        lines.append("| 无 | 无 | 无 | 24h |")
    lines.append("")

    lines.append("## Evidence Inventory / 证据清单")
    lines.append("| ID | 来源 | 类型 | 可信度 | 轨道 | 新鲜度 | 发现者 | 轮次 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    if not sorted_evidence:
        lines.append("| 无 | 无 | 无 | 无 | 无 | 无 | 无 | 无 |")
    else:
        for item in sorted_evidence:
            source = short(item.get("publisher") or item.get("url", "N/A"), 50)
            lines.append(
                f"| {esc(item.get('evidence_id', 'N/A'))} | {source} | {esc(item.get('source_type', 'N/A'))} | "
                f"{esc(item.get('credibility_tier', 'N/A'))} | {esc(item.get('evidence_track', 'N/A'))} | "
                f"{esc(item.get('freshness_status', 'N/A'))} | {esc(item.get('discovered_by', 'N/A'))} | "
                f"{esc(item.get('discovered_at_round', 'N/A'))} |"
            )
    lines.append("")

    lines.append("## Methodology / 方法论")
    lines.append(f"- 轮次: {esc(config.get('round_count', len(round_nums)))}")
    lines.append(f"- 模式: {esc(config.get('mode', 'balanced'))}")
    lines.append(f"- 深度: {esc(config.get('depth', 'standard'))}")
    lines.append(f"- 证据条目: {len(sorted_evidence)}")
    lines.append(f"- 可信度分布: {esc(', '.join(f'{k}={v}' for k, v in sorted(tier_counter.items())))}")
    lines.append(f"- 证据刷新策略: {esc(config.get('evidence_refresh', 'hybrid'))}")
    lines.append(f"- 语言: {esc(config.get('language', 'bilingual'))}")
    lines.append(f"- 生成时间: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines.append("")

    render_conclusion_profiles(lines, as_list(final_report.get("conclusion_profiles")), zh=True)

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <workspace_dir>")
        return 2

    workspace = Path(sys.argv[1]).resolve()
    report_dir = workspace / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    content = render(workspace)
    tmp_path = report_dir / "debate_report.tmp.md"
    out_path = report_dir / "debate_report.md"

    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, out_path)
    print(f"Rendered: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
