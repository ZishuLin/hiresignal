"""
News Scraper
Fetches recent company news: earnings reports, CEO changes, funding rounds,
restructuring announcements, and financial health signals.
Uses SerpAPI + direct page fetching for full article content.
"""

import os
import re
import time
import requests
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
except ImportError:
    pass

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Categorized signal keywords
SIGNALS = {
    "layoff": [
        "layoff", "laid off", "let go", "workforce reduction", "job cuts",
        "rif", "reduction in force", "severance", "eliminating positions",
        "cutting jobs", "headcount reduction",
    ],
    "hiring_freeze": [
        "hiring freeze", "pause hiring", "stop hiring", "slowdown hiring",
        "no new hires", "not hiring",
    ],
    "financial_distress": [
        "bankruptcy", "chapter 11", "insolvency", "debt restructuring",
        "cash crunch", "burn rate", "runway", "missed guidance", "revenue decline",
        "loss widens", "net loss", "operating loss",
    ],
    "restructuring": [
        "restructuring", "reorganization", "reorg", "strategic review",
        "pivot", "new direction", "spinoff", "divest",
    ],
    "leadership_change": [
        "ceo resign", "ceo fired", "ceo departure", "new ceo", "cto leaves",
        "executive exit", "leadership change", "stepping down",
    ],
    "positive_financial": [
        "record revenue", "beat expectations", "exceeded guidance", "profitable",
        "revenue growth", "ipo", "funding round", "series", "valuation",
        "strong earnings", "revenue up",
    ],
    "positive_hiring": [
        "hiring", "expanding team", "new positions", "growing workforce",
        "talent acquisition", "open roles",
    ],
}


def _serpapi_search(query: str, num: int = 8, news: bool = False) -> List[Dict]:
    """Search via SerpAPI. Set news=True for Google News results."""
    key = os.environ.get("SERPAPI_KEY", "").strip()
    if not key:
        return []
    params = {
        "q": query,
        "api_key": key,
        "num": num,
        "engine": "google",
    }
    if news:
        params["tbm"] = "nws"  # Google News tab
    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("news_results", data.get("organic_results", []))
    except Exception as e:
        print(f"[news] SerpAPI error: {e}")
        return []


def _classify_signal(text: str) -> List[str]:
    """Return list of signal categories found in text."""
    text_lower = text.lower()
    found = []
    for category, keywords in SIGNALS.items():
        if any(kw in text_lower for kw in keywords):
            found.append(category)
    return found


def _extract_date(text: str) -> Optional[str]:
    """Try to extract a publication date from text."""
    patterns = [
        r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+202\d',
        r'202\d-\d{2}-\d{2}',
        r'(202\d)',
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(0)
    return None


def get_company_news(company: str, months_back: int = 12) -> Dict:
    """
    Fetch and categorize recent news for a company.
    Returns categorized signals with titles and dates.
    """
    current_year = datetime.now().year
    queries = [
        f"{company} layoffs restructuring {current_year}",
        f"{company} earnings revenue financial results {current_year}",
        f"{company} CEO leadership hiring {current_year}",
    ]

    all_articles = []
    seen_titles = set()

    for query in queries:
        # Try news search first, fall back to regular
        results = _serpapi_search(query, num=6, news=True)
        if not results:
            results = _serpapi_search(query, num=6, news=False)

        for r in results:
            title = r.get("title", "")
            if title in seen_titles:
                continue
            seen_titles.add(title)

            snippet = r.get("snippet", r.get("description", ""))
            link = r.get("link", "")
            date = r.get("date", "") or _extract_date(title + " " + snippet) or ""
            text = title + " " + snippet
            signals = _classify_signal(text)

            if signals:  # only include articles with identifiable signals
                all_articles.append({
                    "title": title[:100],
                    "snippet": snippet[:200],
                    "date": date,
                    "link": link,
                    "signals": signals,
                })

        time.sleep(0.4)

    # Group by signal category
    categorized: Dict[str, List] = {cat: [] for cat in SIGNALS}
    for article in all_articles:
        for sig in article["signals"]:
            if sig in categorized:
                categorized[sig].append({
                    "title": article["title"],
                    "date": article["date"],
                    "link": article["link"],
                })

    # Deduplicate within each category
    for cat in categorized:
        seen = set()
        deduped = []
        for item in categorized[cat]:
            if item["title"] not in seen:
                seen.add(item["title"])
                deduped.append(item)
        categorized[cat] = deduped[:4]

    # Calculate sentiment score (-100 to +100)
    risk_score = 0
    risk_score -= len(categorized["layoff"]) * 20
    risk_score -= len(categorized["hiring_freeze"]) * 15
    risk_score -= len(categorized["financial_distress"]) * 18
    risk_score -= len(categorized["restructuring"]) * 12
    risk_score -= len(categorized["leadership_change"]) * 10
    risk_score += len(categorized["positive_financial"]) * 15
    risk_score += len(categorized["positive_hiring"]) * 10
    risk_score = max(-100, min(100, risk_score))

    return {
        "company": company,
        "news_sentiment_score": risk_score,
        "total_articles": len(all_articles),
        "signals": categorized,
        "has_layoff_news": len(categorized["layoff"]) > 0,
        "has_hiring_freeze": len(categorized["hiring_freeze"]) > 0,
        "has_positive_signals": len(categorized["positive_financial"]) > 0 or len(categorized["positive_hiring"]) > 0,
    }


def get_earnings_summary(company: str) -> Dict:
    """
    Fetch recent earnings/financial performance news.
    Returns whether company beat/missed expectations and key financial facts.
    """
    results = _serpapi_search(
        f"{company} quarterly earnings results revenue {datetime.now().year}", num=6
    )

    beat = False
    missed = False
    revenue_mentions = []
    key_facts = []

    for r in results:
        text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
        if any(w in text for w in ["beat", "exceeded", "topped", "above expectations", "record"]):
            beat = True
            key_facts.append(r.get("title", "")[:70])
        if any(w in text for w in ["missed", "below expectations", "disappointing", "fell short"]):
            missed = True
            key_facts.append(r.get("title", "")[:70])

        # Extract revenue numbers
        rev_m = re.findall(r'\$[\d.]+\s*(?:billion|million|B|M)\b', r.get("snippet", ""), re.IGNORECASE)
        revenue_mentions.extend(rev_m)

    return {
        "company": company,
        "beat_expectations": beat,
        "missed_expectations": missed,
        "revenue_mentions": list(set(revenue_mentions))[:4],
        "key_headlines": list(set(key_facts))[:3],
    }


def fetch_article_text(url: str, max_chars: int = 3000) -> Optional[str]:
    """
    Attempt to fetch and extract text from a news article URL.
    Returns cleaned text or None if unable to fetch.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        html = resp.text

        # Remove script/style blocks
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # Extract paragraph text
        paras = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
        text = " ".join(re.sub(r'<[^>]+>', '', p).strip() for p in paras)
        text = re.sub(r'\s+', ' ', text).strip()

        return text[:max_chars] if text else None
    except Exception:
        return None
