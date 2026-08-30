"""Self-contained visualization for the quality report (v3 Phase 5).

Radar chart of the eight dimensions plus distribution bars, rendered as
inline SVG wrapped in a standalone HTML dashboard — no external assets,
no chart libraries, fully deterministic.
"""

from __future__ import annotations

import html
import math
import os

_SIZE = 460
_CENTER = _SIZE / 2
_RADIUS = 155
_AXES = 8


def _polar(angle_deg: float, radius: float) -> tuple[float, float]:
    # Start at the top (−90°), clockwise.
    angle = math.radians(angle_deg - 90)
    return _CENTER + radius * math.cos(angle), _CENTER + radius * math.sin(angle)


def _short_label(full: str) -> str:
    """'证据质量 / Evidence quality' → '证据质量' (chart axis keeps it compact)."""
    return full.split(" / ")[0]


def radar_svg(dimensions: list[dict], overall: float) -> str:
    """8-axis radar chart; ``dimensions`` = [{label, score}, ...] in axis order."""
    points: list[str] = []
    axis_lines: list[str] = []
    labels: list[str] = []

    for idx, dim in enumerate(dimensions):
        angle = idx * (360 / max(len(dimensions), _AXES))
        x, y = _polar(angle, _RADIUS * max(0.0, min(1.0, dim["score"])))
        points.append(f"{x:.1f},{y:.1f}")
        lx, ly = _polar(angle, _RADIUS + 26)
        anchor = "middle"
        if lx > _CENTER + 8:
            anchor = "start"
        elif lx < _CENTER - 8:
            anchor = "end"
        labels.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
            f'class="axis-label">{html.escape(_short_label(dim["label"]))} '
            f'{dim["score"]:.2f}</text>'
        )
        ax, ay = _polar(angle, _RADIUS)
        axis_lines.append(f'<line x1="{_CENTER}" y1="{_CENTER}" x2="{ax:.1f}" y2="{ay:.1f}"/>')

    rings = []
    for ring in (0.25, 0.5, 0.75, 1.0):
        ring_points = " ".join(
            f"{_polar(i * (360 / max(len(dimensions), _AXES)), _RADIUS * ring)[0]:.1f},"
            f"{_polar(i * (360 / max(len(dimensions), _AXES)), _RADIUS * ring)[1]:.1f}"
            for i in range(len(dimensions))
        )
        rings.append(f'<polygon points="{ring_points}" class="ring"/>')

    vertex_dots = "".join(
        f'<circle cx="{p.split(",")[0]}" cy="{p.split(",")[1]}" r="3.5" class="vertex"/>'
        for p in points
    )
    return (
        f'<svg viewBox="0 0 {_SIZE} {_SIZE}" class="radar" role="img" '
        f'aria-label="quality radar overall {overall:.2f}">'
        + "".join(rings)
        + "".join(axis_lines)
        + f'<polygon points="{" ".join(points)}" class="radar-area"/>'
        + vertex_dots
        + "".join(labels)
        + f'<text x="{_CENTER}" y="{_SIZE - 8}" text-anchor="middle" class="overall">'
        f'综合 / overall {overall:.2f}</text></svg>'
    )


def bar_svg(title: str, counts: dict[str, int], color: str = "#2563eb") -> str:
    """Horizontal distribution bars for a categorical counter."""
    total = sum(counts.values()) or 1
    width = 460
    rows = []
    top = 24
    for label, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        share = count / total
        rows.append(
            f'<text x="0" y="{top + 11}" class="bar-label">{html.escape(label)}</text>'
            f'<rect x="150" y="{top}" width="{max(2.0, (width - 210) * share):.1f}" '
            f'height="14" rx="3" fill="{color}"/>'
            f'<text x="{width - 50}" y="{top + 11}" class="bar-label">{count} · {share:.0%}</text>'
        )
        top += 26
    return (f'<svg viewBox="0 0 {width} {max(top, 40)}" class="bars">'
            f'<text x="0" y="12" class="bar-title">{html.escape(title)}</text>'
            + "".join(rows) + "</svg>")


def build_dashboard(workspace: str, report: dict) -> None:
    """Write ``reports/quality_dashboard.html`` (self-contained)."""
    radar = radar_svg(
        [{"label": d["label"], "score": d["score"]} for d in report["dimensions"]],
        report["overall_score"],
    )
    baseline = report.get("baseline", {})
    tier_bars = bar_svg("证据可信度分级 / Evidence tiers", baseline.get("evidence", {}).get("by_credibility_tier", {}))
    status_bars = bar_svg("论点状态 / Claim status", baseline.get("claims", {}).get("by_status", {}),
                          color="#059669")

    rows = "".join(
        f"<tr><td>{html.escape(d['label'])}</td>"
        f"<td class='num'>{d['score']:.2f}</td>"
        f"<td class='num'>{report['dimension_weights'][d['dimension']]:.0%}</td>"
        f"<td>{html.escape('；'.join(d['notes']))}</td></tr>"
        for d in report["dimensions"]
    )
    document = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>Debate Quality Dashboard — {html.escape(report['topic'])}</title>
<style>
  body {{ font-family: "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
         margin: 0 auto; max-width: 980px; padding: 24px; color: #111827; }}
  h1 {{ font-size: 22px; }} h2 {{ font-size: 17px; margin-top: 32px; }}
  .header {{ display: flex; gap: 18px; align-items: baseline; flex-wrap: wrap; }}
  .overall-badge {{ font-size: 30px; font-weight: 700; color: #2563eb; }}
  .meta {{ color: #6b7280; font-size: 13px; }}
  .grid {{ display: flex; gap: 32px; flex-wrap: wrap; align-items: flex-start; }}
  .radar {{ width: 460px; max-width: 100%; }}
  .radar-area {{ fill: rgba(37, 99, 235, 0.18); stroke: #2563eb; stroke-width: 2; }}
  .ring {{ fill: none; stroke: #e5e7eb; }}
  line {{ stroke: #e5e7eb; }}
  .vertex {{ fill: #2563eb; }}
  .axis-label {{ font-size: 12px; fill: #374151; }}
  .overall {{ font-size: 14px; font-weight: 600; fill: #111827; }}
  .bars {{ width: 460px; max-width: 100%; margin-bottom: 8px; }}
  .bar-title {{ font-size: 13px; font-weight: 600; fill: #111827; }}
  .bar-label {{ font-size: 11px; fill: #374151; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ border-bottom: 1px solid #e5e7eb; padding: 7px 9px; text-align: left; vertical-align: top; }}
  th {{ background: #f9fafb; }}
  td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  footer {{ margin-top: 36px; color: #9ca3af; font-size: 12px; }}
</style>
</head>
<body>
  <div class="header">
    <h1>辩论质量仪表盘 / Debate Quality Dashboard</h1>
    <span class="overall-badge">{report['overall_score']:.2f}</span>
  </div>
  <p class="meta">
    辩题 / topic: {html.escape(report['topic'])} ·
    模式 / mode: {html.escape(report['mode'])} ·
    轮次 / rounds: {report['rounds_completed']}/{report['rounds_planned']} ·
    生成于 / generated: {html.escape(report['generated_at'])}
  </p>
  <div class="grid">
    <div>{radar}</div>
    <div>{tier_bars}{status_bars}</div>
  </div>
  <h2>八维评分 / Eight dimensions</h2>
  <table>
    <tr><th>维度 / dimension</th><th class="num">得分 / score</th><th class="num">权重 / weight</th><th>要点 / notes</th></tr>
    {rows}
  </table>
  <footer>Critical Debater v3 Phase 5 · deterministic assessment · reports/quality_metrics.json</footer>
</body>
</html>
"""
    path = os.path.join(workspace, "reports", "quality_dashboard.html")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(document)
