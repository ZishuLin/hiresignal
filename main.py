"""
HireSignal — AI-powered job risk intelligence
Commands:
  ghost   <company> <jd_text>   Ghost job detection
  layoff  <company>             Layoff risk prediction
  bias    <company> [jd_text]   Hiring bias analysis
  scam    <company> [jd_text]   Recruitment scam detection
  analyze <company> <jd_text>   Full four-in-one report
"""

import sys
import click
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich import box
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)
console = Console()



def _resolve_jd(company: str, jd_input: str) -> tuple:
    """
    If jd_input looks like a URL, fetch the job posting automatically.
    Returns (company, jd_text, fetched_url).
    company may be updated from the URL if not manually provided.
    """
    from scrapers.job_fetcher import fetch_job_posting, _is_url
    if not jd_input or not _is_url(jd_input):
        return company, jd_input, None

    console.print(f"[dim]Fetching job posting from URL...[/dim]")
    result = fetch_job_posting(jd_input)

    if result["success"]:
        fetched_company = result["company"]
        # Use URL-extracted company only if user didn't provide one explicitly
        final_company = company if company.lower() not in ("unknown", "", "none") else fetched_company
        console.print(f"[dim]✓ Fetched {result['char_count']} chars via {result['method']}[/dim]\n")
        return final_company, result["text"], jd_input
    else:
        console.print(f"[yellow]⚠ {result['error']}[/yellow]")
        console.print("[yellow]Tip: paste the job description text directly instead.[/yellow]\n")
        return company, "", jd_input


def _score_bar(score: int, width: int = 20) -> str:
    filled = round(score / 100 * width)
    bar = "█" * filled + "░" * (width - filled)
    if score >= 70:
        return f"[green]{bar}[/green]"
    elif score >= 45:
        return f"[yellow]{bar}[/yellow]"
    return f"[red]{bar}[/red]"


def _risk_bar(score: int, width: int = 20) -> str:
    """Inverted — high score = high risk = red."""
    filled = round(score / 100 * width)
    bar = "█" * filled + "░" * (width - filled)
    if score >= 70:
        return f"[red]{bar}[/red]"
    elif score >= 45:
        return f"[yellow]{bar}[/yellow]"
    return f"[green]{bar}[/green]"


def _print_flags(red_flags: list, green_flags: list):
    if red_flags:
        console.print("\n[bold red]Red Flags[/bold red]")
        for f in red_flags[:5]:
            console.print(f"  [red]✗[/red] {f}")
    if green_flags:
        console.print("\n[bold green]Green Flags[/bold green]")
        for f in green_flags[:5]:
            console.print(f"  [green]✓[/green] {f}")


def _print_ghost_report(result: dict):
    score = result["score"]
    verdict = result["verdict"]
    color = result["verdict_color"]

    console.print()
    console.print(Panel(
        f"[bold]Ghost Job Score: [{color}]{score}/100[/{color}][/bold]  {_score_bar(score)}\n"
        f"Verdict: [{color}]{verdict}[/{color}]",
        title=f"[cyan]Ghost Job Detection — {result['company']}[/cyan]",
        border_style="cyan",
    ))

    # Breakdown table
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold magenta")
    table.add_column("Factor", style="dim", width=22)
    table.add_column("Score", width=10)
    table.add_column("Bar", width=22)
    bd = result["breakdown"]
    for label, val, max_val in [
        ("Specificity", bd["specificity"], 40),
        ("Originality", bd["originality"], 30),
        ("Company Signals", bd["company_signals"], 30),
        ("JD Length", bd["jd_length"], 10),
    ]:
        pct = round(val / max_val * 100)
        table.add_row(label, f"{val}/{max_val}", _score_bar(pct, 15))
    console.print(table)

    stats = result["stats"]
    console.print(f"  [dim]Word count: {stats['word_count']} · Vague phrases: {stats['vague_phrases']} · "
                  f"Specific requirements: {stats['specific_requirements']} · "
                  f"Template similarity: {stats['template_similarity']:.0%}[/dim]")

    _print_flags(result["red_flags"], result["green_flags"])

    console.print(f"\n[bold]AI Analysis:[/bold]\n  {result['ai_analysis']}")
    console.print()


def _print_layoff_report(result: dict):
    score = result["risk_score"]
    level = result["risk_level"]
    color = result["risk_color"]

    console.print()
    console.print(Panel(
        f"[bold]Layoff Risk: [{color}]{level}[/{color}]  (Score: {score}/100)[/bold]  {_risk_bar(score)}\n",
        title=f"[cyan]Layoff Risk Prediction — {result['company']}[/cyan]",
        border_style="cyan",
    ))

    data = result["data"]
    if data["layoff_events"]:
        console.print("[bold]Historical Layoff Events:[/bold]")
        for e in data["layoff_events"][:3]:
            console.print(f"  [red]•[/red] [{e['year']}] {e['title']}")

    if data["glassdoor_rating"]:
        rating_color = "green" if data["glassdoor_rating"] >= 4.0 else "yellow" if data["glassdoor_rating"] >= 3.5 else "red"
        console.print(f"\n  Glassdoor: [{rating_color}]{data['glassdoor_rating']}/5[/{rating_color}] "
                      f"({data['glassdoor_trend']} trend)")

    _print_flags(result["red_flags"], result["green_flags"])
    console.print(f"\n[bold]AI Summary:[/bold]\n  {result['summary']}")
    console.print()


def _print_bias_report(result: dict):
    score = result["bias_score"]
    verdict = result["verdict"]
    color = result["verdict_color"]

    console.print()
    console.print(Panel(
        f"[bold]Bias Score: [{color}]{score}/100[/{color}][/bold]  {_score_bar(score)}\n"
        f"Verdict: [{color}]{verdict}[/{color}]",
        title=f"[cyan]Hiring Bias Analysis — {result['company']}[/cyan]",
        border_style="cyan",
    ))

    jd = result["jd_analysis"]
    if jd["gender_balance"] != "unknown":
        gb_color = "green" if jd["gender_balance"] == "balanced" else "yellow" if jd["gender_balance"] == "female-skewed" else "red"
        console.print(f"\n  Gender language: [{gb_color}]{jd['gender_balance']}[/{gb_color}]")
        if jd["masculine_words"]:
            console.print(f"  [dim]Masculine-coded: {', '.join(jd['masculine_words'][:5])}[/dim]")
        if jd["age_bias_flags"]:
            console.print(f"  [yellow]Age bias flags: {', '.join(jd['age_bias_flags'][:3])}[/yellow]")

    _print_flags(result["red_flags"], result["green_flags"])
    console.print(f"\n[bold]AI Analysis:[/bold]\n  {result['ai_analysis']}")
    console.print()



def _print_scam_report(result: dict):
    score = result["scam_score"]
    verdict = result["verdict"]
    color = result["verdict_color"]

    console.print()
    console.print(Panel(
        f"[bold]Scam Safety Score: [{color}]{score}/100[/{color}][/bold]  {_score_bar(score)}\n"
        f"Verdict: [{color}]{verdict}[/{color}]",
        title=f"[cyan]Scam Detection — {result['company']}[/cyan]",
        border_style="cyan",
    ))

    cats = result["categories"]
    cat_colors = {
        "none": "green", "low": "green", "medium": "yellow",
        "high": "red", "critical": "red bold",
    }
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold magenta")
    table.add_column("Category", width=24)
    table.add_column("Risk", width=16)
    for label, key in [
        ("Identity Phishing", "identity_phishing"),
        ("Payment Demands", "payment_demands"),
        ("Salary Bait", "salary_bait"),
        ("Fake Company / HR", "fake_company"),
    ]:
        risk = cats.get(key, "none")
        c = cat_colors.get(risk, "white")
        table.add_row(label, f"[{c}]{risk.upper()}[/{c}]")
    console.print(table)

    _print_flags(result["red_flags"], result["green_flags"])
    console.print(f"\n[bold]AI Analysis:[/bold]\n  {result['ai_analysis']}")
    console.print()

@click.group()
def cli():
    """HireSignal — Know the real risks before you apply."""
    pass


@cli.command()
@click.argument("company")
@click.argument("jd_text")
def ghost(company, jd_text):
    """Detect if a job posting is a ghost job.\n\nExample: python main.py ghost Shopify https://linkedin.com/jobs/view/123 """
    from modules.ghost_detector import analyze_ghost_job
    company, jd_text, _ = _resolve_jd(company, jd_text)
    console.print(f"\n[bold cyan]HireSignal[/bold cyan] — Ghost Job Detection")
    console.print(f"Analyzing: [yellow]{company}[/yellow]\n")
    with console.status("Analyzing job posting..."):
        result = analyze_ghost_job(company, jd_text)
    _print_ghost_report(result)


@cli.command()
@click.argument("company")
def layoff(company):
    """Predict layoff risk for a company.\n\nExample: hiresignal layoff Shopify"""
    from modules.layoff_predictor import predict_layoff_risk
    console.print(f"\n[bold cyan]HireSignal[/bold cyan] — Layoff Risk Prediction")
    console.print(f"Analyzing: [yellow]{company}[/yellow]\n")
    with console.status("Gathering signals..."):
        result = predict_layoff_risk(company)
    _print_layoff_report(result)


@cli.command()
@click.argument("company")
@click.argument("jd_text", default="")
def bias(company, jd_text):
    """Analyze hiring bias for a company and/or job description.\n\nExample: python main.py bias Shopify https://linkedin.com/jobs/view/123 """
    from modules.bias_detector import analyze_bias
    company, jd_text, _ = _resolve_jd(company, jd_text)
    console.print(f"\n[bold cyan]HireSignal[/bold cyan] — Hiring Bias Analysis")
    console.print(f"Analyzing: [yellow]{company}[/yellow]\n")
    with console.status("Analyzing bias signals..."):
        result = analyze_bias(company, jd_text)
    _print_bias_report(result)



@cli.command()
@click.argument("company")
@click.argument("jd_text", default="")
def scam(company, jd_text):
    """Detect recruitment scams.\n\nExample: python main.py scam Shopify https://linkedin.com/jobs/view/123 """
    from modules.scam_detector import analyze_scam
    company, jd_text, _ = _resolve_jd(company, jd_text)
    console.print(f"\n[bold cyan]HireSignal[/bold cyan] — Scam Detection")
    console.print(f"Analyzing: [yellow]{company}[/yellow]\n")
    with console.status("Scanning for scam signals..."):
        result = analyze_scam(company, jd_text)
    _print_scam_report(result)


@cli.command()
@click.argument("company")
@click.argument("jd_text", default="")
@click.option("--output", "-o", default=None, help="Save HTML report to file")
def analyze(company, jd_text, output):
    """Full three-in-one risk report for a company + job posting.\n\nExample: hiresignal analyze Shopify "job description here..." """
    from modules.ghost_detector import analyze_ghost_job
    from modules.layoff_predictor import predict_layoff_risk
    from modules.bias_detector import analyze_bias
    from report import print_full_report, generate_html_report

    company, jd_text, fetched_url = _resolve_jd(company, jd_text)
    console.print(f"\n[bold cyan]HireSignal[/bold cyan] — Full Risk Analysis")
    console.print(f"Target: [yellow]{company}[/yellow]\n")

    results = {}
    from modules.scam_detector import analyze_scam
    steps = [
        ("ghost", "Analyzing job posting...", lambda: analyze_ghost_job(company, jd_text) if jd_text else None),
        ("layoff", "Predicting layoff risk...", lambda: predict_layoff_risk(company)),
        ("bias", "Detecting hiring bias...", lambda: analyze_bias(company, jd_text)),
        ("scam", "Scanning for scams...", lambda: analyze_scam(company, jd_text)),
    ]

    from rich.progress import Progress, SpinnerColumn, TextColumn
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        for key, desc, fn in steps:
            task = progress.add_task(desc, total=None)
            try:
                results[key] = fn()
                progress.update(task, description=f"[green]✓ {desc.replace('...', '')}[/green]")
            except Exception as e:
                progress.update(task, description=f"[red]✗ {key}: {e}[/red]")
                results[key] = None
            progress.stop_task(task)

    print_full_report(company, results)

    if output or jd_text:
        out_path = output or f"{company.lower().replace(' ', '_')}_hiresignal.html"
        generate_html_report(company, results, out_path)
        console.print(f"\n[green]HTML Report:[/green] {out_path}")


if __name__ == "__main__":
    cli()

# ── PATCHED: scam command + updated analyze ────────────────────────────────────
# (appended by patch)
