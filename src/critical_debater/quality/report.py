"""Bilingual quality report rendering (v3 Phase 5, 质量报告生成).

Renders ``reports/quality_report.md`` from the eight-dimension assessment:
score band verdict, dimension table with subscores, and notes — Chinese and
English side by side per the project's bilingual rule.
"""

from __future__ import annotations

import os

from ..workspace import timestamp

_SCORE_BANDS = (
    (0.8, "优秀 / Strong", "辩论过程与结论有坚实基础 / The debate and its conclusions rest on solid ground."),
    (0.6, "良好 / Sound", "整体可靠，个别维度有提升空间 / Reliable overall, with room to improve in places."),
    (0.4, "中等 / Moderate", "存在明显短板，结论需谨慎采信 / Notable weaknesses; treat conclusions with care."),
    (0.0, "薄弱 / Weak", "证据或裁决链路不足，结论可靠性存疑 / Evidence or adjudication is thin; reliability is in doubt."),
)


def _band(score: float) -> tuple[str, str]:
    for threshold, label, verdict in _SCORE_BANDS:
        if score >= threshold:
            return label, verdict
    return _SCORE_BANDS[-1][1], _SCORE_BANDS[-1][2]


def render_quality_report(workspace: str, report: dict) -> None:
    """Write ``reports/quality_report.md`` (bilingual)."""
    label, verdict = _band(report["overall_score"])
    lines = [
        "# Quality Report / 质量评估报告",
        "",
        f"**辩题 / Topic**: {report['topic']}",
        f"**模式 / Mode**: {report['mode']} · **深度 / Depth**: {report['depth']} · "
        f"**轮次 / Rounds**: {report['rounds_completed']}/{report['rounds_planned']}",
        f"**生成时间 / Generated**: {report['generated_at']}",
        "",
        f"## Overall Score / 综合得分: {report['overall_score']:.2f} — {label}",
        "",
        f"{verdict}",
        "",
        "## Dimension Scores / 八维评分",
        "",
        "| 维度 / Dimension | 得分 / Score | 权重 / Weight |",
        "|---|---|---|",
    ]
    for dim in report["dimensions"]:
        lines.append(
            f"| {dim['label']} | {dim['score']:.2f} | "
            f"{report['dimension_weights'][dim['dimension']]:.0%} |"
        )

    lines += ["", "## Dimension Notes / 各维度要点", ""]
    for dim in report["dimensions"]:
        lines.append(f"### {dim['label']} — {dim['score']:.2f}")
        lines.append("")
        if dim["notes"]:
            lines.extend(f"- {note}" for note in dim["notes"])
        else:
            lines.append("- (no notes / 无)")
        lines.append("")

    baseline = report.get("baseline", {})
    evidence = baseline.get("evidence", {})
    claims = baseline.get("claims", {})
    lines += [
        "## Baseline Statistics / 基础统计",
        "",
        f"- 证据总数 / evidence total: {evidence.get('total', 0)}"
        f"（corroborated: {evidence.get('corroborated', 0)}）",
        f"- 可信度分级分布 / tier distribution: "
        f"{', '.join(f'{k}={v}' for k, v in sorted(evidence.get('by_credibility_tier', {}).items())) or '-'}",
        f"- 信源语言分布 / source languages: "
        f"{', '.join(f'{k}={v}' for k, v in sorted(evidence.get('by_source_language', {}).items())) or '-'}",
        f"- 论点状态分布 / claim statuses: "
        f"{', '.join(f'{k}={v}' for k, v in sorted(claims.get('by_status', {}).items())) or '-'}",
        f"- 可信度均分 / average credibility: {baseline.get('credibility', {}).get('average', 0)}",
        "",
        "---",
        "*Machine-readable detail: reports/quality_metrics.json · "
        f"Dashboard: reports/quality_dashboard.html · Rendered {timestamp()}*",
        "",
    ]

    path = os.path.join(workspace, "reports", "quality_report.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
