"""
Report generation for HireSignal — terminal summary + HTML report.
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from typing import Dict

console = Console()


def print_full_report(company: str, results: Dict):
    """Print combined terminal report."""
    ghost = results.get("ghost")
    layoff = results.get("layoff")
    bias = results.get("bias")
    scam = results.get("scam")

    console.print()
    console.print(Panel(
        f"[bold cyan]HireSignal Report — {company}[/bold cyan]",
        border_style="cyan",
    ))

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("Module", width=20)
    table.add_column("Score", width=12)
    table.add_column("Verdict", width=20)
    table.add_column("Top Signal", width=45)

    if ghost:
        c = ghost["verdict_color"]
        top = ghost["red_flags"][0] if ghost["red_flags"] else (ghost["green_flags"][0] if ghost["green_flags"] else "—")
        table.add_row("Ghost Job", f"[{c}]{ghost['score']}/100[/{c}]", f"[{c}]{ghost['verdict']}[/{c}]", top[:44])

    if layoff:
        c = layoff["risk_color"]
        top = layoff["red_flags"][0] if layoff["red_flags"] else (layoff["green_flags"][0] if layoff["green_flags"] else "—")
        table.add_row("Layoff Risk", f"[{c}]{layoff['risk_score']}/100[/{c}]", f"[{c}]{layoff['risk_level']}[/{c}]", top[:44])

    if bias:
        c = bias["verdict_color"]
        top = bias["red_flags"][0] if bias["red_flags"] else (bias["green_flags"][0] if bias["green_flags"] else "—")
        table.add_row("Bias Risk", f"[{c}]{bias['bias_score']}/100[/{c}]", f"[{c}]{bias['verdict']}[/{c}]", top[:44])

    if scam:
        c = scam["verdict_color"]
        top = scam["red_flags"][0] if scam["red_flags"] else (scam["green_flags"][0] if scam["green_flags"] else "—")
        table.add_row("Scam Risk", f"[{c}]{scam['scam_score']}/100[/{c}]", f"[{c}]{scam['verdict']}[/{c}]", top[:44])

    console.print(table)

    # AI summaries
    for label, key, field in [("Ghost Job", "ghost", "ai_analysis"), ("Layoff", "layoff", "summary"), ("Bias", "bias", "ai_analysis"), ("Scam", "scam", "ai_analysis")]:
        r = results.get(key)
        if r and r.get(field):
            console.print(f"\n[bold]{label}:[/bold] {r[field]}")

    console.print()


def generate_html_report(company: str, results: Dict, output_path: str):
    """Generate self-contained HTML report."""
    ghost = results.get("ghost") or {}
    layoff = results.get("layoff") or {}
    bias = results.get("bias") or {}
    scam = results.get("scam") or {}

    def score_color(score, inverted=False):
        if inverted:
            return "#f87171" if score >= 70 else "#fbbf24" if score >= 45 else "#4ade80"
        return "#4ade80" if score >= 70 else "#fbbf24" if score >= 45 else "#f87171"

    def flags_html(flags, color):
        if not flags:
            return '<div style="color:#64748b;font-size:.85rem">None identified</div>'
        return "".join(f'<div style="margin:.3rem 0;font-size:.85rem;color:#94a3b8">'
                       f'<span style="color:{color};margin-right:.4rem">{"✗" if color == "#f87171" else "✓"}</span>{f}</div>'
                       for f in flags[:5])

    def card(title, score, verdict, color, ai_text, red_flags, green_flags, extra=""):
        pct = score
        return f"""
        <div class="card">
          <div class="card-title">{title}</div>
          <div class="score-row">
            <span class="score-num" style="color:{color}">{score}</span>
            <span class="score-denom">/100</span>
            <span class="verdict" style="color:{color}">{verdict}</span>
          </div>
          <div class="bar-bg"><div class="bar-fill" style="width:{pct}%;background:{color}"></div></div>
          {extra}
          <div class="flags-grid">
            <div>
              <div class="flags-label" style="color:#f87171">Red Flags</div>
              {flags_html(red_flags, "#f87171")}
            </div>
            <div>
              <div class="flags-label" style="color:#4ade80">Green Flags</div>
              {flags_html(green_flags, "#4ade80")}
            </div>
          </div>
          <div class="ai-note"><strong>AI Analysis:</strong> {ai_text}</div>
        </div>"""

    ghost_extra = ""
    if ghost:
        s = ghost.get("stats", {})
        ghost_extra = (f'<div class="stats-row">'
                       f'<span>Words: {s.get("word_count", "—")}</span>'
                       f'<span>Vague phrases: {s.get("vague_phrases", "—")}</span>'
                       f'<span>Template similarity: {s.get("template_similarity", 0):.0%}</span>'
                       f'</div>')

    layoff_extra = ""
    if layoff:
        d = layoff.get("data", {})
        rating = d.get("glassdoor_rating")
        trend = d.get("glassdoor_trend", "")
        layoff_extra = (f'<div class="stats-row">'
                        f'<span>Glassdoor: {f"{rating}/5" if rating else "N/A"}</span>'
                        f'<span>Trend: {trend}</span>'
                        f'<span>Layoff events: {len(d.get("layoff_events", []))}</span>'
                        f'</div>')

    bias_extra = ""
    if bias:
        jd = bias.get("jd_analysis", {})
        gender = jd.get("gender_balance", "unknown")
        gc = "#f87171" if gender == "male-skewed" else "#4ade80" if gender == "balanced" else "#fbbf24"
        bias_extra = (f'<div class="stats-row">'
                      f'<span>Gender language: <span style="color:{gc}">{gender}</span></span>'
                      f'<span>Age bias flags: {len(jd.get("age_bias_flags", []))}</span>'
                      f'</div>')


    scam_extra = ""
    if scam:
        cats = scam.get("categories", {})
        cat_colors = {"none": "#4ade80", "low": "#4ade80", "medium": "#fbbf24", "high": "#f87171", "critical": "#f87171"}
        cat_html = "".join(
            f'<span style="color:{cat_colors.get(v,"#94a3b8")};margin-right:.8rem;font-size:.78rem">'
            f'{k.replace("_", " ").title()}: {v.upper()}</span>'
            for k, v in cats.items()
        )
        scam_extra = f'<div class="stats-row" style="flex-wrap:wrap">{cat_html}</div>'

    cards_html = ""
    if ghost:
        cards_html += card(
            "🔍 Ghost Job Detection",
            ghost.get("score", 0),
            ghost.get("verdict", "—"),
            score_color(ghost.get("score", 0)),
            ghost.get("ai_analysis", ""),
            ghost.get("red_flags", []),
            ghost.get("green_flags", []),
            ghost_extra,
        )
    if layoff:
        cards_html += card(
            "📉 Layoff Risk",
            layoff.get("risk_score", 0),
            layoff.get("risk_level", "—"),
            score_color(layoff.get("risk_score", 0), inverted=True),
            layoff.get("summary", ""),
            layoff.get("red_flags", []),
            layoff.get("green_flags", []),
            layoff_extra,
        )
    if bias:
        cards_html += card(
            "⚖️ Hiring Bias",
            bias.get("bias_score", 0),
            bias.get("verdict", "—"),
            score_color(bias.get("bias_score", 0)),
            bias.get("ai_analysis", ""),
            bias.get("red_flags", []),
            bias.get("green_flags", []),
            bias_extra,
        )
    if scam:
        cards_html += card(
            "🚨 Scam Detection",
            scam.get("scam_score", 0),
            scam.get("verdict", "—"),
            score_color(scam.get("scam_score", 0)),
            scam.get("ai_analysis", ""),
            scam.get("red_flags", []),
            scam.get("green_flags", []),
            scam_extra,
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HireSignal — {company}</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=DM+Mono&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root {{
  --bg: #080b14; --surface: #0d1120; --border: #1e2840;
  --text: #e2e8f0; --muted: #64748b; --dim: #94a3b8;
  --accent: #6366f1;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: var(--bg); color: var(--text); font-family: 'DM Sans', sans-serif; padding: 2rem 1rem; }}
body::before {{
  content: ''; position: fixed; inset: 0;
  background-image: linear-gradient(rgba(99,102,241,.03) 1px,transparent 1px),
    linear-gradient(90deg,rgba(99,102,241,.03) 1px,transparent 1px);
  background-size: 40px 40px; pointer-events: none;
}}
.wrap {{ max-width: 960px; margin: 0 auto; position: relative; }}
h1 {{ font-family: 'Syne', sans-serif; font-size: 2rem; font-weight: 800;
  background: linear-gradient(135deg,#e2e8f0,#a78bfa,#38bdf8);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text; margin-bottom: .5rem; }}
.meta {{ color: var(--muted); font-family: 'DM Mono', monospace; font-size: .8rem; margin-bottom: 2rem; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; }}
.card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 1.25rem; }}
.card-title {{ font-family: 'Syne', sans-serif; font-size: 1rem; font-weight: 700; margin-bottom: .8rem; }}
.score-row {{ display: flex; align-items: baseline; gap: .4rem; margin-bottom: .6rem; }}
.score-num {{ font-family: 'Syne', sans-serif; font-size: 2.2rem; font-weight: 800; line-height: 1; }}
.score-denom {{ color: var(--muted); font-size: .85rem; }}
.verdict {{ font-size: .85rem; margin-left: auto; font-family: 'DM Mono', monospace; }}
.bar-bg {{ height: 4px; background: var(--border); border-radius: 2px; margin-bottom: .8rem; overflow: hidden; }}
.bar-fill {{ height: 100%; border-radius: 2px; }}
.stats-row {{ display: flex; gap: 1rem; flex-wrap: wrap; font-size: .78rem;
  color: var(--muted); font-family: 'DM Mono', monospace; margin-bottom: .8rem; }}
.flags-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; margin-bottom: .8rem; }}
.flags-label {{ font-size: .72rem; text-transform: uppercase; letter-spacing: .08em;
  font-family: 'DM Mono', monospace; margin-bottom: .3rem; }}
.ai-note {{ font-size: .82rem; color: var(--dim); line-height: 1.6;
  border-top: 1px solid var(--border); padding-top: .7rem; margin-top: .3rem; }}
footer {{ text-align: center; margin-top: 2rem; color: var(--muted);
  font-family: 'DM Mono', monospace; font-size: .75rem; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>HireSignal — {company}</h1>
  <div class="meta">Generated by HireSignal · github.com/ZishuLin/hiresignal</div>
  <div class="cards">{cards_html}</div>
  <footer>Results are based on publicly available data and AI analysis. Always do your own research.</footer>
</div>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
