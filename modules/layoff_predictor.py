"""
Layoff Predictor
Estimates a company's layoff risk based on:
- Historical layoffs.fyi data (via scrapers/layoffs_fyi.py)
- Recent news sentiment (via scrapers/news.py)
- Glassdoor rating trends (via scrapers/glassdoor.py)
- LinkedIn employee exodus signals (via scrapers/linkedin.py)
Risk levels: Low / Medium / High / Critical
"""

import os
import sys
import requests
from typing import Dict, List
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
except ImportError:
    pass

# Add parent to path so scrapers package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))
from scrapers.layoffs_fyi import search_company as layoffs_search
from scrapers.news import get_company_news
from scrapers.glassdoor import get_full_profile as glassdoor_profile
from scrapers.linkedin import get_employee_exodus_signals


def _fetch_layoffs_fyi(company: str) -> Dict:
    """Delegate to scrapers/layoffs_fyi.py."""
    data = layoffs_search(company)
    # Normalize to the shape the rest of this module expects
    events = []
    for e in data.get("events", []):
        events.append({
            "title": e.get("title", e.get("company", "")),
            "year": str(e.get("date", ""))[:4] or "unknown",
            "snippet": e.get("snippet", ""),
        })
    return {
        "layoff_events": events[:5],
        "total_laid_off_estimate": data.get("total_laid_off_estimate", 0),
        "has_history": data.get("has_layoff_history", False),
        "recency": data.get("recency", "none"),
    }


def _fetch_news_sentiment(company: str) -> Dict:
    """Delegate to scrapers/news.py and normalize output."""
    data = get_company_news(company)
    sigs = data.get("signals", {})

    high = [a["title"] for a in sigs.get("layoff", []) + sigs.get("financial_distress", [])]
    medium = [a["title"] for a in sigs.get("hiring_freeze", []) + sigs.get("restructuring", []) + sigs.get("leadership_change", [])]
    low = [a["title"] for a in sigs.get("positive_financial", []) + sigs.get("positive_hiring", [])]

    return {
        "high_risk_signals": list(dict.fromkeys(high))[:4],
        "medium_risk_signals": list(dict.fromkeys(medium))[:3],
        "low_risk_signals": list(dict.fromkeys(low))[:3],
    }


def _fetch_glassdoor_trend(company: str) -> Dict:
    """Delegate to scrapers/glassdoor.py."""
    data = glassdoor_profile(company)
    return {
        "avg_rating": data.get("overall_rating"),
        "sentiment_trend": data.get("sentiment_trend", "neutral"),
        "negative_signals": data.get("negative_count", 0),
        "positive_signals": data.get("positive_count", 0),
    }


def _fetch_linkedin_exodus(company: str) -> Dict:
    """Delegate to scrapers/linkedin.py."""
    return get_employee_exodus_signals(company)


def _calculate_risk(layoffs_data: Dict, news_data: Dict, glassdoor_data: Dict, linkedin_data: Dict = None) -> Dict:
    """Combine all signals into a risk score."""
    risk_points = 0
    max_points = 100

    # Layoff history (0-35 points)
    if layoffs_data["has_history"]:
        events = len(layoffs_data["layoff_events"])
        risk_points += min(35, events * 10)
        if layoffs_data["total_laid_off_estimate"] > 1000:
            risk_points += 5

    # News signals (0-40 points)
    risk_points += min(40, len(news_data["high_risk_signals"]) * 12)
    risk_points += min(15, len(news_data["medium_risk_signals"]) * 5)
    risk_points -= min(15, len(news_data["low_risk_signals"]) * 5)

    # Glassdoor (0-25 points)
    if glassdoor_data["avg_rating"] is not None:
        if glassdoor_data["avg_rating"] < 3.0:
            risk_points += 20
        elif glassdoor_data["avg_rating"] < 3.5:
            risk_points += 10
        elif glassdoor_data["avg_rating"] > 4.0:
            risk_points -= 5
    if glassdoor_data["sentiment_trend"] == "negative":
        risk_points += 10

    risk_score = max(0, min(100, risk_points))

    if risk_score >= 75:
        level, color = "Critical", "red"
    elif risk_score >= 55:
        level, color = "High", "red"
    elif risk_score >= 30:
        level, color = "Medium", "yellow"
    else:
        level, color = "Low", "green"

    return {"score": risk_score, "level": level, "color": color}


def _ai_summary(company: str, layoffs: Dict, news: Dict, glassdoor: Dict, risk: Dict) -> str:
    """Generate AI narrative summary."""
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()

    layoff_events = layoffs.get("layoff_events", [])
    event_titles = [e.get("title", e.get("company",""))[:60] for e in layoff_events[:3]]
    prompt = (
        f"You are writing a layoff risk summary for {company}.\n\n"
        f"VERIFIED DATA (only reference these — do not add facts not listed):\n"
        f"- Layoff events found: {len(layoff_events)} "
        f"({'most recent: ' + layoffs.get('most_recent_year','unknown') if layoff_events else 'none found'})\n"
        f"- Event headlines: {event_titles}\n"
        f"- High-risk news: {news['high_risk_signals'][:2]}\n"
        f"- Positive news: {news['low_risk_signals'][:2]}\n"
        f"- Glassdoor rating: {glassdoor['avg_rating']} out of 5 ({glassdoor['sentiment_trend']} trend)\n"
        f"- Calculated risk level: {risk['level']} ({risk['score']}/100)\n\n"
        f"RULES: Summarize only what the data shows. If layoff_events is 0, say no layoff history found. "
        f"Do not speculate about future layoffs unless news signals support it. "
        f"Do not mention bias, scams, or ghost jobs. 2-3 sentences max."
    )

    for key, url, payload_fn in [
        (groq_key, "https://api.groq.com/openai/v1/chat/completions",
         lambda p: {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": p}], "max_tokens": 150}),
        (gemini_key, f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}",
         lambda p: {"contents": [{"parts": [{"text": p}]}], "generationConfig": {"maxOutputTokens": 150}}),
    ]:
        if not key:
            continue
        try:
            headers = {"Content-Type": "application/json"}
            if "groq" in url:
                headers["Authorization"] = f"Bearer {key}"
            resp = requests.post(url, headers=headers, json=payload_fn(prompt), timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if "groq" in url:
                return data["choices"][0]["message"]["content"].strip()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            continue

    return "AI summary unavailable."


def predict_layoff_risk(company: str) -> Dict:
    """Main function: predict layoff risk for a company."""
    layoffs = _fetch_layoffs_fyi(company)
    news = _fetch_news_sentiment(company)
    glassdoor = _fetch_glassdoor_trend(company)
    linkedin = _fetch_linkedin_exodus(company)
    risk = _calculate_risk(layoffs, news, glassdoor, linkedin)
    summary = _ai_summary(company, layoffs, news, glassdoor, risk)

    # Build signals list
    red_flags = []
    green_flags = []

    if layoffs["has_history"]:
        recency = layoffs.get("recency", "")
        label = f" ({recency.replace('_', ' ')})" if recency != "none" else ""
        red_flags.append(f"Found {len(layoffs['layoff_events'])} layoff event(s){label}")
    company_lower = company.lower()
    for s in news["high_risk_signals"][:3]:
        if company_lower in s.lower():
            red_flags.append(s)
    for s in news["medium_risk_signals"][:2]:
        if company_lower in s.lower():
            red_flags.append(f"⚠ {s}")
    if glassdoor["avg_rating"] and glassdoor["avg_rating"] < 3.5:
        red_flags.append(f"Low Glassdoor rating: {glassdoor['avg_rating']}/5")
    if linkedin.get("exodus_risk") == "high" and layoffs.get("has_history"):
        red_flags.append("High employee exodus detected on LinkedIn")
    for dept in linkedin.get("executive_departures", [])[:2]:
        if len(dept.split()) <= 4 and "Post" not in dept and "List" not in dept and "Article" not in dept:
            red_flags.append(f"Executive departure: {dept[:60]}")

    company_lower = company.lower()
    for s in news["low_risk_signals"][:3]:
        if company_lower in s.lower():
            green_flags.append(s)
    if glassdoor["avg_rating"] and glassdoor["avg_rating"] >= 4.0:
        green_flags.append(f"Strong Glassdoor rating: {glassdoor['avg_rating']}/5")
    if not layoffs["has_history"]:
        green_flags.append("No layoff history found")
    if linkedin.get("exodus_risk") == "low":
        green_flags.append("Stable employee retention signals on LinkedIn")

    return {
        "company": company,
        "risk_score": risk["score"],
        "risk_level": risk["level"],
        "risk_color": risk["color"],
        "summary": summary,
        "red_flags": red_flags,
        "green_flags": green_flags,
        "data": {
            "layoff_events": layoffs["layoff_events"],
            "glassdoor_rating": glassdoor["avg_rating"],
            "glassdoor_trend": glassdoor["sentiment_trend"],
            "linkedin_exodus": linkedin.get("exodus_risk"),
        }
    }